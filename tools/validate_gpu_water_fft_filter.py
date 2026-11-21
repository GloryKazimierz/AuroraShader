"""Small native check: caustic footprint filter follows the active FFT band."""
import argparse,json,shutil,tempfile
from pathlib import Path
from compile_glsl import ROOT,SHADERS,expand
from validate_gpu import Runner,require
from validate_gpu_water_fft_production import ACTIVE,smooth

def filter_tests(runner):
 source='#version 330 compatibility\n'+expand(SHADERS/'lib/water_caustics.glsl')+"""
layout(location=0) out vec4 result;
void main(){
 const float spans[8]=float[8](0.,.1875,.375,.5625,.75,2.,65536.,0.);
 int i=int(gl_FragCoord.x);float x=spans[i];if(i==7)x=uintBitsToFloat(0x7fc00000u);
 result=vec4(causticResolutionWeight(vec2(x,0),vec2(0,x)),0,0,1);
}
"""
 outputs={};spans=[0.,.1875,.375,.5625,.75,2.,65536.,None]
 for fft in (0,1):
  pair=runner.pair('composite1',dict(ACTIVE,WATER_FFT=fft),wrapper=source)
  image=runner.render('FFT caustic footprint {}'.format(fft),pair,8,1)[0];outputs[fft]=image
  wavelength=1.5 if fft else 128/(151*151+97*97)**.5
  for span,pixel in zip(spans,image):
   expected=0. if span is None else 1-smooth(.25,.5,span/wavelength)
   require(abs(pixel[0]-expected)<2e-6 and pixel[1:]==(0,0,1),'Caustic filter does not follow active spectral wavelength')
 require(outputs[1][2][0]==1. and outputs[0][2][0]==0.,'Fixture did not distinguish FFT and legacy bands')
 return dict(cases=16,fft_shortest_wavelength_m=1.5,legacy_detail_wavelength_m=128/(151*151+97*97)**.5,
             scope='Actual caustic helper native readback; footprint filter only, not full FFT caustic flux quality')
