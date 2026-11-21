"""Independent double-precision two-cascade water spectrum / DFT oracle."""
import cmath,json,math
N=64
PERIODS=(16.,64.)
MIN_WAVELENGTHS=(1.5,8.)
MAX_WAVELENGTHS=(8.,32.)
HEIGHT_RMS=(.035,.12)
GRAVITY=9.81
LOOP_SECONDS=600.

def smooth(a,b,x):
 t=max(0.,min(1.,(x-a)/(b-a)));return t*t*(3-2*t)

def hash32(v):
 v&=0xffffffff;v^=v>>16;v=(v*0x7feb352d)&0xffffffff
 v^=v>>15;v=(v*0x846ca68b)&0xffffffff;v^=v>>16;return v

def gaussian(x,y,cascade):
 seed=(x+N*y+cascade*N*N+0xa511e9b3)&0xffffffff
 u=max(2**-24,(hash32(seed)>>8)/float(1<<24))
 angle=2*math.pi*((hash32(seed^0x63d83595)>>8)/float(1<<24))
 return math.sqrt(-2*math.log(u))*complex(math.cos(angle),math.sin(angle))

def wavevector(x,y,cascade):
 return tuple(2*math.pi*(v if v<N//2 else v-N)/PERIODS[cascade] for v in (x,y))

def shape(x,y,cascade):
 kx,kz=wavevector(x,y,cascade);k=math.hypot(kx,kz)
 if k==0 or x==N//2 or y==N//2:return 0.
 lo=2*math.pi/MAX_WAVELENGTHS[cascade];hi=2*math.pi/MIN_WAVELENGTHS[cascade]
 band=smooth(lo,lo*1.2,k)*(1-smooth(hi*.8,hi,k))
 if band==0:return 0.
 alignment=(kx*.8+kz*.6)/k;wind_length=64/GRAVITY
 return band*math.exp(-1/(k*wind_length)**2)*alignment**2/(k**4)*math.exp(-(k*.12)**2)*(1 if alignment>=0 else .25)

SHAPE_SUMS=tuple(sum(shape(x,y,c) for y in range(N) for x in range(N)) for c in (0,1))
SEED_SCALES=tuple(HEIGHT_RMS[c]*N*N/math.sqrt(4*SHAPE_SUMS[c]) for c in (0,1))
SLOPE_VARIANCES=tuple(HEIGHT_RMS[c]**2*sum(shape(x,y,c)*sum(k*k for k in wavevector(x,y,c)) for y in range(N) for x in range(N))/SHAPE_SUMS[c] for c in (0,1))

def seeds(cascade):
 return [[gaussian(x,y,cascade)*SEED_SCALES[cascade]*math.sqrt(shape(x,y,cascade)) for x in range(N)] for y in range(N)]

def evolved(seed,cascade,seconds,speed=1.):
 height=[];slopes=[]
 for y in range(N):
  hrow=[];srow=[]
  for x in range(N):
   kx,kz=wavevector(x,y,cascade);magnitude=math.hypot(kx,kz)
   harmonic=math.floor(math.sqrt(GRAVITY*magnitude)*LOOP_SECONDS/(2*math.pi)+.5)
   angle=2*math.pi*((max(seconds,0)*speed)%LOOP_SECONDS/LOOP_SECONDS)*harmonic
   phase=cmath.exp(1j*angle)
   h=seed[y][x]*phase+seed[-y%N][-x%N].conjugate()*phase.conjugate()
   # Pack two real spatial slope fields into one complex IFFT.
   hrow.append(h);srow.append(1j*kx*h+1j*(1j*kz*h))
  height.append(hrow);slopes.append(srow)
 return height,slopes

def inverse_dft2(field):
 n=len(field);twiddle=[[cmath.exp(2j*math.pi*x*k/n) for k in range(n)] for x in range(n)]
 rows=[[sum(v*w for v,w in zip(row,twiddle[x]))/n for x in range(n)] for row in field]
 return [[sum(rows[k][x]*twiddle[y][k] for k in range(n))/n for x in range(n)] for y in range(n)]

def ifft1(values):
 n=len(values)
 if n==1:return list(values)
 even=ifft1(values[::2]);odd=ifft1(values[1::2]);result=[0j]*n
 for k in range(n//2):
  t=cmath.exp(2j*math.pi*k/n)*odd[k];result[k]=(even[k]+t)*.5;result[k+n//2]=(even[k]-t)*.5
 return result

def ifft2(field):
 rows=[ifft1(row) for row in field];columns=[ifft1(column) for column in zip(*rows)]
 return [list(row) for row in zip(*columns)]

def cpu_tests():
 checks=[]
 for n in (4,8):
  fields=[[[complex((3*x+7*y)%11-5,(5*x+y)%13-6) for x in range(n)] for y in range(n)],
          [[complex(int(x==1 and y==2),0) for x in range(n)] for y in range(n)]]
  for field in fields:
   a,b=ifft2(field),inverse_dft2(field);error=max(abs(x-y) for ar,br in zip(a,b) for x,y in zip(ar,br));assert error<1e-13;checks.append(error)
 stats=[]
 for c in (0,1):
  seed=seeds(c);h,s=evolved(seed,c,17.5);height,slopes=ifft2(h),ifft2(s)
  hermitian=max(abs(h[y][x]-h[-y%N][-x%N].conjugate()) for y in range(N) for x in range(N));assert hermitian<1e-10
  imaginary=max(abs(v.imag) for row in height for v in row);assert imaginary<1e-12
  h2,s2=evolved(seed,c,17.5+3600);loop=max(abs(a-b) for ar,br in zip(h,h2) for a,b in zip(ar,br));assert loop<1e-9
  assert all(shape(x,y,c)==0 for y in range(N) for x in range(N) if x==N//2 or y==N//2)
  stats.append(dict(cascade=c,period_m=PERIODS[c],wavelength_band_m=[MIN_WAVELENGTHS[c],MAX_WAVELENGTHS[c]],
    shape_sum=SHAPE_SUMS[c],seed_scale=SEED_SCALES[c],expected_slope_variance=SLOPE_VARIANCES[c],
    actual_height_rms=math.sqrt(sum(v.real*v.real for row in height for v in row)/(N*N)),
    actual_slope_rms=math.sqrt(sum(abs(v)**2 for row in slopes for v in row)/(N*N)),
    imaginary_residual=imaginary,hermitian_error=hermitian,time_reset_error=loop))
 periods=[]
 for speed in (0.,1.,2.):
  for c in (0,1):
   seed=seeds(c);a,b=evolved(seed,c,17.5,speed);c0,d=evolved(seed,c,3617.5,speed)
   error=max(abs(x-y) for ar,br in zip(a,c0) for x,y in zip(ar,br));assert error==0.
   periods.append(dict(speed=speed,cascade=c,reset_error=error))
 return dict(speed_reset_checks=periods,dft_vs_recursive_fft_errors=checks,cascades=stats,custom_image_bytes=128*64*(8+16+16),
             scope='Independent CPU mathematics; no native dispatch or Iris runtime claimed')

if __name__=='__main__':print(json.dumps(cpu_tests(),indent=2))
