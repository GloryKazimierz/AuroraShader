#ifndef AURORA_WATER_REFRACTION_TRANSPORT_INCLUDED
#define AURORA_WATER_REFRACTION_TRANSPORT_INCLUDED
#if WATER_REFRACTION > 0
vec3 waterRefractedTransport(WaterRefractionHit hit,vec3 surfaceView,vec3 up,
                            float lightCosine,float waterIOR,vec2 levels,vec3 skySource) {
    WaterParams params=waterParams();
    float drop=dot(surfaceView-hit.position,up)*params.worldBlockMeters;
    float viewMeters=hit.pathLength*params.worldBlockMeters;
    float waterCosine=sqrt(max(1.0-(1.0-lightCosine*lightCosine)/(waterIOR*waterIOR),0.0));
    float lightMeters=drop/max(waterCosine,.001);
    // M4 receiver hook belongs here: any caustic gain acts on this hit's q*L,
    // at hit.position/receiverNormal, before either Beer leg; never reuse source q.
    return waterTransportRadiance(hit.radiance,hit.directShare,viewMeters,lightMeters,
                                  levels.x,levels.y,skySource);
}
vec3 applyWaterRefractionTransport(vec3 sameRay,vec3 surfaceView,vec3 up,vec3 normal,
                                   float lightCosine,vec2 levels,vec3 skySource) {
    WaterParams params=waterParams();
    float greenIOR=params.refractiveIndex;
#if WATER_DISPERSION == 1
    // IAPWS R9-97 Eq.1 at 293.15 K, 998.207 kg/m^3:
    // representative R/G/B wavelengths 650/550/450 nm. Three RGB samples are
    // an approximation, not spectral rendering or a temperature simulation.
    greenIOR=1.334682548;
#endif
    WaterRefractionHit greenHit;
    if(!traceWaterRefraction(surfaceView,up,normal,1.0,greenIOR,WATER_REFRACTION_STEPS,greenHit))return sameRay;
    vec3 green=waterRefractedTransport(greenHit,surfaceView,up,lightCosine,greenIOR,levels,skySource);
    vec3 result=mix(sameRay,green,greenHit.confidence);
#if WATER_DISPERSION == 1
    WaterRefractionHit redHit,blueHit;
    bool redValid=traceWaterRefraction(surfaceView,up,normal,1.0,1.331667825,WATER_REFRACTION_STEPS,redHit);
    bool blueValid=traceWaterRefraction(surfaceView,up,normal,1.0,1.339607890,WATER_REFRACTION_STEPS,blueHit);
    // A missing color ray falls back to the coherent center result; it never
    // creates a colored hole by borrowing an invalid or foreground sample.
    if(redValid && blueValid) {
        vec3 red=waterRefractedTransport(redHit,surfaceView,up,lightCosine,1.331667825,levels,skySource);
        vec3 blue=waterRefractedTransport(blueHit,surfaceView,up,lightCosine,1.339607890,levels,skySource);
        float confidence=min(greenHit.confidence,min(redHit.confidence,blueHit.confidence));
        result=mix(sameRay,vec3(red.r,green.g,blue.b),confidence);
    }
#endif
    return result;
}
#endif
#endif
