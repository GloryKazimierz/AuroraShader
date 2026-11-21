"""Native compute verification plus independent DFT truth; no Iris runtime claim."""
import argparse,hashlib,json,math,os,shutil,struct,subprocess,tempfile
from pathlib import Path
from compile_glsl import ROOT,SHADERS,expand,configure
from validate_gpu import Runner,require,write_text
from validate_water_fft import N,seeds,evolved,inverse_dft2,cpu_tests
OPTIONS=dict(WATER_FFT=1,IRIS_FEATURE_COMPUTE_SHADERS=True,IRIS_FEATURE_CUSTOM_IMAGES=True)


def read_image(path):
    values=struct.unpack('<{}f'.format(128*64*4),path.read_bytes())
    return [[tuple(values[(y*128+x)*4:(y*128+x+1)*4]) for x in range(128)] for y in range(64)]


def fft_tests(runner,cxx,plate=None):
    exe=runner.scratch/'aurora-compute.exe'
    command=[cxx,'-std=c++17','-O2','-Wall','-Wextra','-Wpedantic','-static',str(ROOT/'tools/gpu_fft_harness.cpp'),
             '-lopengl32','-lgdi32','-luser32','-o',str(exe)]
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=120,env=runner.environment)
    require(result.returncode==0 and not result.stdout.strip(),'Compute harness build failed or warned: '+result.stdout)
    def call(*args,allow_failure=False):
        result=subprocess.run([str(exe)]+list(map(str,args)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              encoding='utf-8',timeout=90,env=runner.environment)
        text=result.stdout.strip() if result.returncode==0 else result.stderr.strip()
        payload=json.loads(text)
        if not allow_failure:require(result.returncode==0 and payload.get('ok'),text)
        return payload
    capability=call('--probe',allow_failure=True)
    report=dict(cpu=cpu_tests(),capability=capability)
    if not capability.get('ok'):
        report['compute_executed']=False
        report['scope']='Requested native4.3 context unavailable; compute path untested, production optional fallback remains'
        return report
    paths=[]
    for program in ('setup','begin','begin1'):
        path=runner.scratch/(program+'.comp');write_text(path,configure(expand(SHADERS/(program+'.csh')),OPTIONS));paths.append(path)
    images={};rows=[]
    for index,seconds in enumerate((0.,17.5,617.5,3617.5)):
        seed_path=runner.scratch/('seed-{}.raw'.format(index));field_path=runner.scratch/('field-{}.raw'.format(index))
        driver=call('--run',*paths,seconds,seed_path,field_path)
        require(driver.get('dispatch_verified') is True,'Compute dispatch not verified')
        seed_image,field=read_image(seed_path),read_image(field_path);images[seconds]=field
        max_seed=0.;max_field=0.;max_relative_seed=0.
        for cascade in (0,1):
            expected_seed=seeds(cascade)
            actual_seed=[[complex(seed_image[y][x+64*cascade][0],seed_image[y][x+64*cascade][1]) for x in range(N)] for y in range(N)]
            for actual_row,expected_row in zip(actual_seed,expected_seed):
                for a,b in zip(actual_row,expected_row):
                    error=abs(a-b);max_seed=max(max_seed,error)
                    if abs(b)>1e-3:max_relative_seed=max(max_relative_seed,error/abs(b))
                    require(error<=.0002+abs(b)*.00002,'GPU setup spectrum differs from independent seed formula')
            # Use the actual stored seed to isolate evolution/IFFT correctness
            # from the separately checked seed generator's FP32 transcendental error.
            height,slopes=evolved(actual_seed,cascade,seconds)
            spatial_h,spatial_s=inverse_dft2(height),inverse_dft2(slopes)
            for y in range(N):
                for x in range(N):
                    expected=(spatial_h[y][x].real,spatial_s[y][x].real,spatial_s[y][x].imag)
                    actual=field[y][x+64*cascade]
                    require(actual[3]==1.,'FFT field validity marker missing')
                    error=max(abs(a-b) for a,b in zip(actual[:3],expected));max_field=max(max_field,error)
                    require(error<.00002,'Native IFFT differs from independent full DFT: '+str((seconds,cascade,x,y,error)))
        rows.append(dict(seconds=seconds,samples=128*64,max_seed_error=max_seed,max_seed_relative_error=max_relative_seed,
                         max_height_slope_error=max_field))
        print('PASS native FFT t={} max field error={}'.format(seconds,max_field),flush=True)
    require(images[17.5]==images[617.5]==images[3617.5],'GPU600/3600-second periodic snapshots differ')
    require(any(a!=b for ar,br in zip(images[0.],images[17.5]) for a,b in zip(ar,br)),'FFT field did not animate')
    # Isolated Fourier-mode input: the two cascades must stay distinct and the
    # analytic derivatives must follow the independently evaluated frequency.
    supplied=[[(0.,0.,0.,1.) for _ in range(128)] for _ in range(64)]
    supplied[5][3]=(16.,8.,0.,1.);supplied[2][64+1]=(64.,-32.,0.,1.)
    source=runner.scratch/'single-mode-seed.raw'
    source.write_bytes(struct.pack('<{}f'.format(128*64*4),*[v for row in supplied for pixel in row for v in pixel]))
    seed_path,field_path=runner.scratch/'mode-seed.raw',runner.scratch/'mode-field.raw'
    call('--run',*paths,.125,seed_path,field_path,source);field=read_image(field_path)
    mode_error=0.
    for cascade in (0,1):
        actual_seed=[[complex(supplied[y][x+64*cascade][0],supplied[y][x+64*cascade][1]) for x in range(N)] for y in range(N)]
        h,s=evolved(actual_seed,cascade,.125);h,s=inverse_dft2(h),inverse_dft2(s)
        for y in range(N):
            for x in range(N):
                error=max(abs(a-b) for a,b in zip(field[y][x+64*cascade][:3],(h[y][x].real,s[y][x].real,s[y][x].imag)))
                mode_error=max(mode_error,error);require(error<2e-6,'Single-mode derivative/cascade mapping failed')
    speed_checks=[]
    for speed in (0,2):
        speed_paths=[]
        for program in ('setup','begin','begin1'):
            path=runner.scratch/('speed-{}-{}.comp'.format(speed,program))
            write_text(path,configure(expand(SHADERS/(program+'.csh')),dict(OPTIONS,WATER_WAVE_SPEED=speed)));speed_paths.append(path)
        speed_images=[]
        for seconds in (17.5,617.5,3617.5):
            seed_path=runner.scratch/('speed-{}-{}-seed.raw'.format(speed,seconds))
            field_path=runner.scratch/('speed-{}-{}-field.raw'.format(speed,seconds))
            call('--run',*speed_paths,seconds,seed_path,field_path);speed_images.append(read_image(field_path))
        require(speed_images[0]==speed_images[1]==speed_images[2],'UI speed reset is not bit-exact')
        maximum=0.
        if speed==0:
            require(speed_images[0]==images[0.],'Zero speed is not the static t0 pattern')
        else:
            for cascade in (0,1):
                seed=[[complex(seed_image[y][x+64*cascade][0],seed_image[y][x+64*cascade][1]) for x in range(N)] for y in range(N)]
                h,slopes=evolved(seed,cascade,17.5,speed);h,slopes=inverse_dft2(h),inverse_dft2(slopes)
                for y in range(N):
                    for x in range(N):
                        expected=(h[y][x].real,slopes[y][x].real,slopes[y][x].imag)
                        error=max(abs(a-b) for a,b in zip(speed_images[0][y][x+64*cascade][:3],expected))
                        maximum=max(maximum,error);require(error<.00002,'UI speed native field differs from DFT')
        speed_checks.append(dict(speed=speed,periodic600_and3600_bit_exact=True,max_dft_error=maximum))
    report['ui_speed_checks']=speed_checks
    from validate_gpu_water_fft_production import production_tests
    report['production']=production_tests(runner,images[17.5])
    if plate is not None:
        from validate_gpu_water_fft_production import spectral_views
        report['views']=spectral_views(runner,images,plate)
    report.update(compute_executed=True,frames=rows,single_mode_max_error=mode_error,
                  periodic600_and3600_bit_exact=True,field_at_17_5=images[17.5],
                  scope='Actual native4.3 compute/images and independent CPU DFT; Iris patcher/program dispatch unobserved')
    return report
