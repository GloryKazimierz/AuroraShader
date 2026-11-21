"""Independent CPU exploration of spectral horizontal mapping and filtered moments.
No shader, mesh displacement, native GPU or Minecraft visual claim.
"""
import cmath,json,math
from validate_water_fft import N,seeds,evolved,wavevector,ifft2,inverse_dft2,PERIODS

CHOPPINESS=.5

def spectral_fields(height,cascade):
 result={key:[] for key in ('height','sx','sz','dx','dz','jxx','jxz','jzz')}
 for y in range(N):
  rows={key:[] for key in result}
  for x in range(N):
   h=height[y][x];kx,kz=wavevector(x,y,cascade);k=math.hypot(kx,kz)
   values=(h,1j*kx*h,1j*kz*h,1j*kx/k*h if k else 0j,1j*kz/k*h if k else 0j,
           -kx*kx/k*h if k else 0j,-kx*kz/k*h if k else 0j,-kz*kz/k*h if k else 0j)
   for key,value in zip(result,values):rows[key].append(value)
  for key in result:result[key].append(rows[key])
 return result

def packed_spatial(fields):
 pairs=(('height','jxz'),('sx','sz'),('dx','dz'),('jxx','jzz'));result={}
 for real,imag in pairs:
  source=[[a+1j*b for a,b in zip(ar,br)] for ar,br in zip(fields[real],fields[imag])]
  spatial=ifft2(source)
  result[real]=[[v.real for v in row] for row in spatial]
  result[imag]=[[v.imag for v in row] for row in spatial]
 return result

def spectral_moments(height,cascade):
 moments=[0.]*4
 for y in range(N):
  for x in range(N):
   kx,kz=wavevector(x,y,cascade)
   energy=(kx*kx+kz*kz)*abs(height[y][x])**2/(N**4)
   ax=1-math.cos(2*math.pi*x/N);az=1-math.cos(2*math.pi*y/N)
   for i,factor in enumerate((1.,ax,az,ax*az)):moments[i]+=energy*factor
 return moments

def retained_energy(moments,fx,fz,weight=1.):
 tx=2*fx*(1-fx);tz=2*fz*(1-fz)
 return weight*weight*(moments[0]-tx*moments[1]-tz*moments[2]+tx*tz*moments[3])

def sample(field,x,z,period):
 x=(x%period)*N/period;z=(z%period)*N/period
 ix=int(math.floor(x));iz=int(math.floor(z));fx=x-ix;fz=z-iz
 return sum(field[(iz+dy)%N][(ix+dx)%N]*(fx if dx else 1-fx)*(fz if dy else 1-fz) for dz in (0,1) for dx,dy in ((0,dz),(1,dz)))

def sample_derivative(field,x,z,period):
 u=(x%period)*N/period;v=(z%period)*N/period;ix=int(math.floor(u));iz=int(math.floor(v));fx=u-ix;fz=v-iz
 a=field[iz%N][ix%N];b=field[iz%N][(ix+1)%N];c=field[(iz+1)%N][ix%N];d=field[(iz+1)%N][(ix+1)%N]
 return ((a*(1-fx)+b*fx)*(1-fz)+(c*(1-fx)+d*fx)*fz,
         ((b-a)*(1-fz)+(d-c)*fz)*N/period,((c-a)*(1-fx)+(d-b)*fx)*N/period)

def combined(fields,x,z):
 result={key:sum(sample(data[key],x,z,PERIODS[c]) for c,data in enumerate(fields)) for key in fields[0]}
 derivative=[sample_derivative(data['dx'],x,z,PERIODS[c])+sample_derivative(data['dz'],x,z,PERIODS[c]) for c,data in enumerate(fields)]
 # Exact derivative of the SAME sampled displacement, not an interpolated Hessian.
 result['jxx']=sum(d[1] for d in derivative);result['jxz']=sum(d[2] for d in derivative)
 result['jzx']=sum(d[4] for d in derivative);result['jzz']=sum(d[5] for d in derivative)
 return result

def continuous(field,cascade,x,z):
 return sum(value*cmath.exp(1j*(wavevector(ix,iy,cascade)[0]*x+wavevector(ix,iy,cascade)[1]*z))
            for iy,row in enumerate(field) for ix,value in enumerate(row)).real/(N*N)

def tests():
 report={};bounds=[];moments_checks=[];derivative_checks=[];phase_stats=[];packed_error=0.;inverse_errors=[]
 for cascade in (0,1):
  seed=seeds(cascade)
  bound=sum(math.hypot(*wavevector(x,y,cascade))*(abs(seed[y][x])+abs(seed[-y%N][-x%N])) for y in range(N) for x in range(N))/(N*N)
  bounds.append(bound)
  height,_=evolved(seed,cascade,17.5);spectral=spectral_fields(height,cascade);spatial=packed_spatial(spectral)
  # Full DFT is independent of the radix-2 packing implementation.
  for key in spectral:
   truth=inverse_dft2(spectral[key]);error=max(abs(a-b.real) for ar,br in zip(spatial[key],truth) for a,b in zip(ar,br));packed_error=max(packed_error,error);assert error<1e-12
  moments=spectral_moments(height,cascade)
  for fx,fz in ((0.,0.),(.25,.75),(.5,.5),(.875,.125)):
   measured=sum(sample(spatial['sx'],(x+fx)*PERIODS[cascade]/N,(y+fz)*PERIODS[cascade]/N,PERIODS[cascade])**2+
                sample(spatial['sz'],(x+fx)*PERIODS[cascade]/N,(y+fz)*PERIODS[cascade]/N,PERIODS[cascade])**2
                for y in range(N) for x in range(N))/(N*N)
   expected=retained_energy(moments,fx,fz);error=abs(measured-expected);assert error<1e-13
   moments_checks.append(dict(cascade=cascade,fraction=[fx,fz],measured=measured,predicted=expected,error=error))
  epsilon=1e-4
  for x,z in ((.125,.375),(2.75,3.125),(7.5,-4.)):
   for source,axis,key in (('dx',0,'jxx'),('dx',1,'jxz'),('dz',0,'jxz'),('dz',1,'jzz')):
    plus=(x+(epsilon if axis==0 else 0),z+(epsilon if axis==1 else 0));minus=(x-(epsilon if axis==0 else 0),z-(epsilon if axis==1 else 0))
    finite=(continuous(spectral[source],cascade,*plus)-continuous(spectral[source],cascade,*minus))/(2*epsilon)
    analytic=continuous(spectral[key],cascade,x,z);error=abs(finite-analytic);assert error<2e-8
    derivative_checks.append(error)
 exact_sample_checks=[];column_bounds=[0.,0.]
 for cascade in (0,1):
  seed=seeds(cascade);spatial=packed_spatial(spectral_fields(evolved(seed,cascade,17.5)[0],cascade))
  for y in range(N):
   for x in range(N):
    k=wavevector(x,y,cascade);amplitude=(abs(seed[y][x])+abs(seed[-y%N][-x%N]))/(N*N)
    for axis in (0,1):column_bounds[axis]+=abs(k[axis])*amplitude
  for x,z in ((.2,.3),(2.75,3.125),(0.,0.),(15.75,15.75)):
   for key in ('dx','dz'):
    value,dx,dz=sample_derivative(spatial[key],x,z,PERIODS[cascade]);epsilon=1e-5
    # Forward differences remain in floor-selected half-open cell, including seams.
    fx=(sample(spatial[key],x+epsilon,z,PERIODS[cascade])-value)/epsilon
    fz=(sample(spatial[key],x,z+epsilon,PERIODS[cascade])-value)/epsilon
    error=max(abs(dx-fx),abs(dz-fz));assert error<1e-9;exact_sample_checks.append(error)
 sampled_bound=math.hypot(*column_bounds)
 total_bound=sum(bounds);assert total_bound<1.4 and sampled_bound<1.25
 for seconds in (0.,17.5,47.,93.,151.,259.,397.,599.):
  fields=[packed_spatial(spectral_fields(evolved(seeds(c),c,seconds)[0],c)) for c in (0,1)]
  for strength in (.6,1.):
   minimum_eigen=1e9;minimum_area=1e9;maximum_area=0.;compressed=0;strong=0;clipped=0;max_displacement=0.;raw_power=0.;clipped_power=0.;raised_clipped_power=0.
   for y in range(128):
    for x in range(128):
     f=combined(fields,(x+.25)*.5,(y+.75)*.5);scale=CHOPPINESS*strength
     a=1+scale*f['jxx'];b=scale*f['jxz'];c=scale*f['jzx'];d=1+scale*f['jzz'];area=a*d-b*c
     trace=a*a+b*b+c*c+d*d;eigen=math.sqrt(max(0.,.5*(trace-math.sqrt(max(0.,trace*trace-4*area*area)))))
     minimum_eigen=min(minimum_eigen,eigen);minimum_area=min(minimum_area,area);maximum_area=max(maximum_area,area)
     compressed+=area<.98;strong+=area<.90;clipped+=math.hypot(f['sx'],f['sz'])>.12
     max_displacement=max(max_displacement,scale*math.hypot(f['dx'],f['dz']))
     power=f['sx']**2+f['sz']**2;raw_power+=power;clipped_power+=min(power,.12**2);raised_clipped_power+=min(power,.155**2)
   for i in range(24):
    x=(i*17.375+seconds*.01)%64;z=(i*11.125+.375)%64;q=[x,z]
    for _ in range(3):
     f=combined(fields,*q);scale=CHOPPINESS*strength;a=1+scale*f['jxx'];b=scale*f['jxz'];c=scale*f['jzx'];d=1+scale*f['jzz'];det=a*d-b*c
     residual=(q[0]+scale*f['dx']-x,q[1]+scale*f['dz']-z)
     q[0]-=(d*residual[0]-b*residual[1])/det;q[1]-=(a*residual[1]-c*residual[0])/det
    f=combined(fields,*q);error=math.hypot(q[0]+scale*f['dx']-x,q[1]+scale*f['dz']-z);inverse_errors.append(error)
   phase_stats.append(dict(seconds=seconds,strength=strength,min_eigenvalue=minimum_eigen,min_area=minimum_area,max_area=maximum_area,
                           compression_below_98=compressed/16384.,compression_below_90=strong/16384.,old_gradient_clamp_fraction=clipped/16384.,max_displacement_m=max_displacement,clamp_012_power_fraction=clipped_power/raw_power,clamp_0155_power_fraction=raised_clipped_power/raw_power))
 # An independent single sinusoid must compress at its crest, expand at its trough.
 amplitude=.1;k=2*math.pi/4
 crest=1-CHOPPINESS*amplitude*k;trough=1+CHOPPINESS*amplitude*k
 assert crest<1<trough
 report.update(exact_bilinear_derivative_max_error=max(exact_sample_checks),sampled_map_column_bounds=column_bounds,sampled_map_operator_bound=sampled_bound,sampled_map_guaranteed_min_singular=1-CHOPPINESS*sampled_bound,choppiness=CHOPPINESS,per_cascade_all_time_operator_bounds=bounds,total_bound=total_bound,
               guaranteed_min_eigenvalue_at_strength1=1-CHOPPINESS*total_bound,packed_field_max_dft_error=packed_error,
               finite_difference_max_jacobian_error=max(derivative_checks),filtered_moment_checks=moments_checks,
               phase_samples=phase_stats,max_three_step_inverse_residual_m=max(inverse_errors),
               inverse_rejections_at_1e_4=sum(e>1e-4 for e in inverse_errors),inverse_queries=len(inverse_errors),
               single_sinusoid_crest_area=crest,single_sinusoid_trough_area=trough,
               scope='CPU continuous spectral derivatives AND exact half-open bilinear displacement Jacobian, sampled optical map, exact per-cascade global bilinear power moments; not local variance, not clamp-corrected, no native GPU or vertex displacement')
 return report

if __name__=='__main__':print(json.dumps(tests(),indent=2))
