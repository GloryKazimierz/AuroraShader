"""Exercise the full spectral graph at fixed speeds and with known Fourier modes."""
import struct
import subprocess
from compile_glsl import SHADERS, configure, expand
from validate_gpu import require, write_text
from validate_water_fft import evolved, inverse_dft2
from validate_gpu_water_fft import OPTIONS

def spectral_controls(runner,executable,base_zero):
    """Check frozen/fast UI speeds and two hand-authored impulses using the full image graph."""
    from validate_gpu_water_fft_dynamics import read
    from validate_water_fft_choppy import spectral_fields
    summaries=[]
    for kind,speed,times in [('freeze',0,(17.5,617.5,3617.5)),('fast',2,(17.5,617.5,3617.5)),('isolated_modes',1,(.125,))]:
        out=runner.scratch/('control-'+kind);out.mkdir()
        paths=[]
        for name in ('setup','begin','begin1','begin2'):
            path=out/(name+'.comp')
            write_text(path,configure(expand(SHADERS/(name+'.csh')),dict(OPTIONS,WATER_WAVE_SPEED=speed)))
            paths.append(str(path))
        command=[str(executable),'--run',*paths,str(out)]
        if kind=='isolated_modes':
            seed=[(0.,0.,0.,1.)]*(128*64)
            seed[5*128+3]=(16.,8.,0.,1.);seed[2*128+65]=(64.,-32.,0.,1.)
            path=out/'modes.raw'
            path.write_bytes(struct.pack('<{}f'.format(len(seed)*4),*(v for pixel in seed for v in pixel)))
            command[1]='--seed';command.append(str(path))
        result=subprocess.run(command+list(map(str,times)),capture_output=True,encoding='utf-8',timeout=90,env=runner.environment)
        require(result.returncode==0 and not result.stderr.strip(),'FFT controls: '+result.stderr+result.stdout)
        field=read(out/'field-0.raw',128,64);displaced=read(out/'displacement-0.raw',128,64)
        for index in range(1,len(times)):
            for key in ('field','displacement'):
                require((out/(key+'-0.raw')).read_bytes()==(out/(key+'-'+str(index)+'.raw')).read_bytes(),
                        'Control frame/time wrap failed: '+kind+' '+key)
        if speed==0:
            require(field==base_zero['field'] and displaced==base_zero['displacement'],'Frozen waves changed with UI speed0')
        seed=read(out/'seed-0.raw',128,64);maximum=0.
        for cascade in (0,1):
            initial=[[complex(seed[y][x+cascade*64][0],seed[y][x+cascade*64][1]) for x in range(64)] for y in range(64)]
            height,_=evolved(initial,cascade,times[0],speed)
            spectra=spectral_fields(height,cascade)
            truth=[inverse_dft2(spectra[name]) for name in ('height','sx','sz','dx','dz')]
            for y in range(64):
                for x in range(64):
                    observed=field[y][x+64*cascade][:3]+displaced[y][x+64*cascade][:2]
                    maximum=max(maximum,max(abs(v-expected[y][x].real) for v,expected in zip(observed,truth)))
        require(maximum<(2e-6 if kind=='isolated_modes' else .00002),'Independent control DFT mismatch '+kind+' '+str(maximum))
        summaries.append(dict(case=kind,speed=speed,frames=len(times),grid_samples=8192,max_dft_error=maximum))
    return summaries
