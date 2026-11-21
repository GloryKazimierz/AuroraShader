#ifndef AURORA_WATER_INTERFACE_SCATTER_INCLUDED
#define AURORA_WATER_INTERFACE_SCATTER_INCLUDED
struct WaterInterfaceScatter {
    vec3 reflected;
    vec3 transmitted;
    float fresnel;
    float radianceScale;
    bool totalInternalReflection;
    bool valid;
};
bool waterMediumFinite(float value) { return !isnan(value)&&!isinf(value); }
bool waterMediumFinite3(vec3 value) { return !any(isnan(value))&&!any(isinf(value)); }
WaterInterfaceScatter scatterWaterInterface(vec3 incident,vec3 incidentSideNormal,
                                            float incidentIOR,float transmittedIOR) {
    WaterInterfaceScatter result=WaterInterfaceScatter(vec3(0),vec3(0),1.0,1.0,false,false);
    if(!waterMediumFinite3(incident)||!waterMediumFinite3(incidentSideNormal)
       ||!waterMediumFinite(incidentIOR)||!waterMediumFinite(transmittedIOR)
       ||incidentIOR<1.0||incidentIOR>2.0||transmittedIOR<1.0||transmittedIOR>2.0)return result;
    float iScale=max(max(abs(incident.x),abs(incident.y)),abs(incident.z));
    float nScale=max(max(abs(incidentSideNormal.x),abs(incidentSideNormal.y)),abs(incidentSideNormal.z));
    if(iScale<=1e-6||nScale<=1e-6)return result;
    vec3 direction=normalize(incident/iScale),normal=normalize(incidentSideNormal/nScale);
    float cosine=-dot(direction,normal);
    if(!waterMediumFinite(cosine)||cosine<=0.0)return result;
    cosine=clamp(cosine,0.0,1.0);
    float eta=incidentIOR/transmittedIOR;
    float sineSquared=eta*eta*max(0.0,1.0-cosine*cosine);
    result.reflected=reflect(direction,normal);
    result.radianceScale=eta*eta;
    if(sineSquared>=1.0){result.totalInternalReflection=true;result.valid=true;return result;}
    float transmittedCosine=sqrt(max(0.0,1.0-sineSquared));
    result.transmitted=eta*direction+(eta*cosine-transmittedCosine)*normal;
    float perpendicular=(incidentIOR*cosine-transmittedIOR*transmittedCosine)
                       /(incidentIOR*cosine+transmittedIOR*transmittedCosine);
    float parallel=(transmittedIOR*cosine-incidentIOR*transmittedCosine)
                  /(transmittedIOR*cosine+incidentIOR*transmittedCosine);
    result.fresnel=clamp(.5*(perpendicular*perpendicular+parallel*parallel),0.0,1.0);
    result.valid=waterMediumFinite3(result.transmitted)&&waterMediumFinite3(result.reflected)
                &&waterMediumFinite(result.fresnel);
    return result;
}
#endif
