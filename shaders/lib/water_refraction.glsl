#ifndef AURORA_WATER_REFRACTION_INCLUDED
#define AURORA_WATER_REFRACTION_INCLUDED
// Depth footprint is deliberately conservative; no hidden/off-screen visibility.
// Include after water_resolve declares colortex7/8/9 and depthtex0.
// colortex5/6, depthtex1 and projection matrices come from the shared trace API.
#if WATER_REFRACTION > 0
struct WaterRefractionHit {
    ivec2 pixel;
    vec3 position;
    vec3 radiance;
    float pathLength;
    float directShare;
    float confidence;
    vec3 receiverNormal;
    int steps;
    int reason; // 0 hit, 1 unsupported, 2 bounds, 3 invalid, 4 foreground,
                // 5 discontinuity, 6 budget/range, 7 TIR
};
bool waterRefractFinite3(vec3 v) { return !any(isnan(v)) && !any(isinf(v)); }
bool waterRefractProject(vec3 p, ivec2 size, out vec2 pixel) {
    vec4 clip=gbufferProjection*vec4(p,1.0);
    if (any(isnan(clip)) || any(isinf(clip)) || clip.w<=1e-6) return false;
    pixel=(clip.xy/clip.w*.5+.5)*vec2(size);
    return !any(isnan(pixel)) && !any(isinf(pixel));
}
bool waterRefractSample(ivec2 pixel, ivec2 size, vec3 sourceSurface, vec3 waterUp, out vec3 point, out vec3 rgb) {
    if (any(lessThan(pixel,ivec2(0))) || any(greaterThanEqual(pixel,size))) return false;
    vec4 scene=texelFetch(colortex5,pixel,0);
    float depth=texelFetch(colortex6,pixel,0).r;
    float opaque=texelFetch(depthtex1,pixel,0).r;
    float owner=texelFetch(colortex9,pixel,0).r;
    if (!waterRefractFinite3(scene.rgb) || scene.a!=1.0 || any(lessThan(scene.rgb,vec3(0))) || any(greaterThan(scene.rgb,vec3(65504)))
        || isnan(depth) || isinf(depth) || depth<0.0 || depth>=1.0 || depth!=opaque
        || isnan(owner) || isinf(owner) || owner<0.0 || owner>1.0) return false;
    vec4 waterRecord=texelFetch(colortex7,pixel,0);
    vec4 ownership=texelFetch(colortex8,pixel,0);
    float finalDepth=texelFetch(depthtex0,pixel,0).r;
    if(any(isnan(waterRecord)) || any(isinf(waterRecord))
       || any(isnan(ownership)) || any(isinf(ownership))
       || abs(ownership.r*255.0-1.0)>.002 || ownership.a!=0.0
       || abs(dot(waterRecord.xyz,waterRecord.xyz)-1.0)>.001
       || dot(waterRecord.xyz,waterUp)<=.65
       || waterRecord.a<0.0 || waterRecord.a>=1.0
       || isnan(finalDepth) || isinf(finalDepth) || finalDepth<0.0 || finalDepth>=1.0
       || abs(waterRecord.a-finalDepth)>1.0/16777215.0
       || depth<=waterRecord.a) return false;
    vec2 waterUV=(vec2(pixel)+.5)/vec2(size);
    vec4 front=gbufferProjectionInverse*vec4(waterUV*2.0-1.0,waterRecord.a*2.0-1.0,1.0);
    if(any(isnan(front)) || any(isinf(front)) || front.w<=1e-6) return false;
    // Existing top-interface capture is local evidence, never an inferred
    // infinite water plane. Different-height pools/flows fall back for now.
    if(abs(dot(front.xyz/front.w-sourceSurface,waterUp))>.04) return false;
    vec2 uv=(vec2(pixel)+.5)/vec2(size);
    vec4 view=gbufferProjectionInverse*vec4(uv*2.0-1.0,depth*2.0-1.0,1.0);
    if (any(isnan(view)) || any(isinf(view)) || view.w<=1e-6) return false;
    point=view.xyz/view.w;rgb=scene.rgb;
    return waterRefractFinite3(point) && point.z<0.0;
}
int waterRefractInspect(vec3 point,vec3 surface,vec3 geometric,ivec2 size,
              out ivec2 pixel,out vec3 rgb,out vec3 receiverNormal,out float gap) {
    vec2 projected;
    if (!waterRefractProject(point,size,projected)) return 2;
    pixel=ivec2(floor(projected));
    if (any(lessThan(pixel,ivec2(1))) || any(greaterThanEqual(pixel+1,size))) return 2;
    const ivec2 offsets[9]=ivec2[9](ivec2(0),ivec2(1,0),ivec2(0,1),ivec2(1),
        ivec2(-1,0),ivec2(0,-1),ivec2(-1),ivec2(-1,1),ivec2(1,-1));
    vec3 positions[9];vec3 unused;
    for(int i=0;i<9;++i) {
        if(!waterRefractSample(pixel+offsets[i],size,surface,geometric,positions[i],unused)) return 3;
        if(dot(geometric,positions[i]-surface)>=-.001) return 4;
        if(i==0)rgb=unused;
    }
    // Nine actual points distinguish a sampled depth step from a tilted plane;
    // this avoids an angle-dependent depth-gradient cutoff. Cost is unmeasured.
    vec3 plane=cross(positions[1]-positions[0],positions[2]-positions[0]);
    if(dot(plane,plane)<1e-14) return 5;
    plane=normalize(plane);
    receiverNormal=plane;
    float offset=dot(plane,positions[0]);
    for(int i=3;i<9;++i)if(abs(dot(plane,positions[i])-offset)>.002) return 5;
    vec3 eyeRay=normalize(point);
    float denominator=dot(plane,eyeRay);
    if(abs(denominator)<1e-8) return 5;
    float travel=offset/denominator;
    if(travel<=0.0) return 5;
    gap=-point.z+(eyeRay*travel).z;
    return 0;
}
bool traceWaterRefraction(vec3 surface,vec3 geometricNormal,vec3 shadingNormal,
                      float incidentIOR,float transmittedIOR,int budget,
                      out WaterRefractionHit hit) {
    hit=WaterRefractionHit(ivec2(0),vec3(0),vec3(0),0.0,0.0,0.0,vec3(0),0,1);
    if(budget!=64 && budget!=128)return false;
    ivec2 size=textureSize(colortex5,0);
    if(any(lessThan(size,ivec2(2))) || any(notEqual(size,textureSize(colortex6,0)))
       || any(notEqual(size,textureSize(depthtex1,0)))
       || any(notEqual(size,textureSize(colortex9,0)))
       || any(notEqual(size,textureSize(colortex7,0)))
       || any(notEqual(size,textureSize(colortex8,0)))
       || any(notEqual(size,textureSize(depthtex0,0)))) return false;
    if(!waterRefractFinite3(surface)||!waterRefractFinite3(geometricNormal)||!waterRefractFinite3(shadingNormal)
       || dot(surface,surface)<=1e-12 || dot(geometricNormal,geometricNormal)<=1e-12
       || dot(shadingNormal,shadingNormal)<=1e-12
       || incidentIOR<=0.0 || transmittedIOR<=0.0) return false;
    vec3 incident=normalize(surface),geometric=normalize(geometricNormal),normal=normalize(shadingNormal);
    if(dot(incident,geometric)>=0.0 || dot(normal,geometric)<.65 || dot(incident,normal)>=0.0) return false;
    vec3 direction=refract(incident,normal,incidentIOR/transmittedIOR);
    if(dot(direction,direction)<1e-12){hit.reason=7;return false;}
    if(direction.z>=-1e-6)return false;
    direction=normalize(direction);
    vec3 start=surface+direction*.005;
    float previous=0.0,distance=0.0,previousGap=0.0;
    for(int index=0;index<128;++index) {
        if(index>=clamp(budget,1,128))break;
        hit.steps=index+1;
        vec3 point=start+direction*distance;
        ivec2 pixel;vec3 rgb,receiverNormal;float gap;
        int reason=waterRefractInspect(point,surface,geometric,size,pixel,rgb,receiverNormal,gap);
        if(reason!=0){hit.reason=reason;return false;}
        if(gap>=0.0) {
            if(index==0 || previousGap>=0.0)return false;
            float lo=previous,hi=distance;
            for(int refine=0;refine<10;++refine) {
                float middle=(lo+hi)*.5;
                reason=waterRefractInspect(start+direction*middle,surface,geometric,size,pixel,rgb,receiverNormal,gap);
                if(reason!=0){hit.reason=reason;return false;}
                if(gap>=0.0)hi=middle;else lo=middle;
            }
            point=start+direction*hi;
            reason=waterRefractInspect(point,surface,geometric,size,pixel,rgb,receiverNormal,gap);
            if(reason!=0){hit.reason=reason;return false;}
            if(gap>max(.002,abs(point.z)*2e-5)){hit.reason=5;return false;}
            hit.pixel=pixel;hit.position=point;hit.radiance=rgb;
            hit.pathLength=hi+.005;
            hit.directShare=texelFetch(colortex9,pixel,0).r;
            vec2 hitScreen;
            if(!waterRefractProject(point,size,hitScreen)){hit.reason=2;return false;}
            vec2 edge=min(hitScreen,vec2(size)-hitScreen);
            hit.confidence=smoothstep(0.0,8.0,min(edge.x,edge.y))
                *(1.0-smoothstep(48.0,64.0,hit.pathLength))
                *(1.0-smoothstep(float(budget)*.75,float(budget),float(hit.steps)));
            if(hit.confidence<=0.0){hit.reason=6;return false;}
            hit.receiverNormal=dot(receiverNormal,-point)>=0.0?receiverNormal:-receiverNormal;
            hit.reason=0;return true;
        }
        if(distance>=64.0){hit.reason=6;return false;}
        vec2 here,ahead;
        if(!waterRefractProject(point,size,here)||!waterRefractProject(point+direction,size,ahead)){hit.reason=2;return false;}
        float velocity=max(abs(ahead.x-here.x),abs(ahead.y-here.y));
        float stepSize=min(.5,.75/max(velocity,1e-8));
        previous=distance;previousGap=gap;
        distance=min(64.0,distance+max(.005,stepSize));
    }
    hit.reason=6;return false;
}
#endif // WATER_REFRACTION
#endif // AURORA_WATER_REFRACTION_INCLUDED
