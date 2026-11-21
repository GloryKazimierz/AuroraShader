#ifndef AURORA_WATER_REFRACTION_TILES_INCLUDED
#define AURORA_WATER_REFRACTION_TILES_INCLUDED
#if WATER_REFRACTION > 0
uniform sampler2D colortex11;
bool waterPlanarInterval(ivec2 tile,ivec2 tiles,float waterHeight,float bedHeight,out vec4 interval){
    if(any(lessThan(tile,ivec2(0)))||any(greaterThanEqual(tile,tiles)))return false;
    interval=texelFetch(colortex11,tile,0);
    if(any(isnan(interval))||any(isinf(interval))||interval.x>interval.y||interval.z>interval.w
       ||interval.y-interval.x>.00401||interval.w-interval.z>.00401
       ||abs((interval.x+interval.y)*.5-waterHeight)>.006
       ||abs((interval.z+interval.w)*.5-bedHeight)>.006
       ||interval.x-interval.w<=.001)return false;
    return true;
}
bool waterPlanarPath(vec2 first,vec2 last,ivec2 tiles,float waterHeight,float bedHeight,out int visited){
    vec2 delta=last-first;
    ivec2 direction=ivec2(sign(delta)),cell=ivec2(floor(first/8.0));
    vec2 next=vec2(2.0),stride=vec2(2.0);
    for(int axis=0;axis<2;++axis){
        if(direction[axis]==0)continue;
        if(direction[axis]<0 && first[axis]==8.0*float(cell[axis]))cell[axis]--;
        float boundary=8.0*float(cell[axis]+(direction[axis]>0?1:0));
        next[axis]=(boundary-first[axis])/delta[axis];
        stride[axis]=8.0/abs(delta[axis]);
    }
    visited=0;
    float entered=0.0;
    float span=max(abs(delta.x),abs(delta.y));
    for(int index=0;index<32;++index){
        vec4 interval;
        if(!waterPlanarInterval(cell,tiles,waterHeight,bedHeight,interval))return false;
        visited=index+1;
        float leave=min(1.0,min(next.x,next.y));
        if(leave>=1.0)return true;
        if(leave<entered)return false;
        // The one-pixel halo is much wider than this FP32 corner convention;
        // both adjacent near-corner strips have already been checked.
        if(abs(next.x-next.y)*span<=.002){
            cell+=direction;next+=stride;
        }else if(next.x<next.y){
            cell.x+=direction.x;next.x+=stride.x;
        }else{
            cell.y+=direction.y;next.y+=stride.y;
        }
        entered=leave;
    }
    return false;
}
bool traceWaterRefractionPlanar(vec3 surface,vec3 geometricNormal,vec3 shadingNormal,
                                float incidentIOR,float transmittedIOR,out WaterRefractionHit hit){
    hit=WaterRefractionHit(ivec2(0),vec3(0),vec3(0),0.0,0.0,0.0,vec3(0),0,8);
    ivec2 size=textureSize(colortex5,0),tiles=textureSize(colortex11,0);
    if(any(lessThan(size,ivec2(10)))||any(lessThan(tiles,max(size/8,ivec2(1))))
       ||any(greaterThan(tiles,(size+7)/8)))return false;
    if(!waterRefractFinite3(surface)||!waterRefractFinite3(geometricNormal)||!waterRefractFinite3(shadingNormal)
       ||dot(surface,surface)<=1e-12||dot(geometricNormal,geometricNormal)<=1e-12||dot(shadingNormal,shadingNormal)<=1e-12
       ||isnan(incidentIOR)||isinf(incidentIOR)||isnan(transmittedIOR)||isinf(transmittedIOR)
       ||incidentIOR<=0.0||transmittedIOR<=0.0)return false;
    vec3 up=normalize(geometricNormal),normal=normalize(shadingNormal),incident=normalize(surface);
    if(dot(incident,up)>=0.0||dot(normal,up)<.65||dot(incident,normal)>=0.0)return false;
    vec3 direction=refract(incident,normal,incidentIOR/transmittedIOR);
    if(dot(direction,direction)<1e-12){hit.reason=7;return false;}
    direction=normalize(direction);
    if(direction.z>=-1e-6||dot(up,direction)>=-1e-6)return false;
    vec2 startScreen;
    if(!waterRefractProject(surface,size,startScreen))return false;
    ivec2 first=ivec2(floor(startScreen/8.0));
    if(any(lessThan(first,ivec2(0)))||any(greaterThanEqual(first,tiles)))return false;
    vec4 initial=texelFetch(colortex11,first,0);
    if(any(isnan(initial))||any(isinf(initial))||initial.x>initial.y||initial.z>initial.w)return false;
    float waterHeight=dot(up,surface),bedHeight=(initial.z+initial.w)*.5;
    vec4 checked;
    if(!waterPlanarInterval(first,tiles,waterHeight,bedHeight,checked))return false;
    float distance=(bedHeight-waterHeight)/dot(up,direction);
    if(isnan(distance)||isinf(distance)||distance<=.005||distance>=64.0)return false;
    vec3 predicted=surface+direction*distance;
    vec2 endScreen;
    if(!waterRefractProject(predicted,size,endScreen))return false;
    int visited;
    if(!waterPlanarPath(startScreen,endScreen,tiles,waterHeight,bedHeight,visited))return false;
    ivec2 pixel;vec3 rgb,receiverNormal;float gap;
    WaterRefractionFootprint cached=WaterRefractionFootprint(ivec2(-1),vec3(0),vec3(0),0.0,false);
    int reason=waterRefractInspect(predicted,surface,up,size,pixel,rgb,receiverNormal,gap,cached);
    if(reason!=0)return false;
    // Final full 3x3 fit corrects quantized tile height; no provisional plane shades.
    if(abs(dot(cached.normal,up))<.99999)return false;
    float denominator=dot(cached.normal,direction);
    if(abs(denominator)<=1e-8)return false;
    float corrected=(cached.offset-dot(cached.normal,surface))/denominator;
    if(isnan(corrected)||isinf(corrected)||corrected<=.005||corrected>=64.0||abs(corrected-distance)>.02)return false;
    vec3 point=surface+direction*corrected;
    vec2 finalScreen;
    if(!waterRefractProject(point,size,finalScreen))return false;
    // Refinement may only move inside the already proven endpoint pixel.
    if(any(notEqual(ivec2(floor(finalScreen)),pixel))||any(greaterThan(abs(finalScreen-endScreen),vec2(.25))))return false;
    reason=waterRefractInspect(point,surface,up,size,pixel,rgb,receiverNormal,gap,cached);
    if(reason!=0||abs(gap)>max(.002,abs(point.z)*2e-5))return false;
    vec2 edge=min(finalScreen,vec2(size)-finalScreen);
    float confidence=smoothstep(0.0,8.0,min(edge.x,edge.y))*(1.0-smoothstep(48.0,64.0,corrected))
        *(1.0-smoothstep(24.0,32.0,float(visited)));
    if(confidence<=0.0)return false;
    hit.pixel=pixel;hit.position=point;hit.radiance=rgb;hit.pathLength=corrected;
    hit.directShare=texelFetch(colortex9,pixel,0).r;hit.confidence=confidence;
    hit.receiverNormal=dot(receiverNormal,-point)>=0.0?receiverNormal:-receiverNormal;
    hit.steps=visited;hit.reason=0;return true;
}
bool selectWaterRefraction(vec3 surface,vec3 up,vec3 normal,float incidentIOR,float transmittedIOR,
                           int budget,out WaterRefractionHit hit){
    if(traceWaterRefractionPlanar(surface,up,normal,incidentIOR,transmittedIOR,hit))return true;
#if WATER_REFRACTION == 2
    // Explicit experimental quality only. Normal/RGB planar modes never hide
    // hundreds of per-pixel texture reads behind an unproven tile.
    return traceWaterRefraction(surface,up,normal,incidentIOR,transmittedIOR,budget,hit);
#else
    return false;
#endif
}
#endif
#endif
