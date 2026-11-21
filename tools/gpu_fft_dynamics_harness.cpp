// Bounded native persistent-frame proof for spectral displacement and moments.
#define main auroraGraphicsHarnessMain
#include "gpu_harness.cpp"
#undef main
int main(int argc,char** argv){
    GlInfo info;
    try{
        const std::string command=argc>1?argv[1]:"";
        bool timing=command=="--time", suppliedSeed=command=="--seed";
        int firstTime=timing?6:(suppliedSeed?8:7);
        if((!timing && !suppliedSeed && command!="--run") || argc<=firstTime || argc>firstTime+12 || (timing && argc!=7))
            throw Failure("arguments","--run SETUP ROWS COLUMNS MOMENTS DIR T... | --seed SETUP ROWS COLUMNS MOMENTS DIR SEED T... | --time SETUP ROWS COLUMNS MOMENTS T");
        fs::path directory;
        if(!timing){
            directory=absolutePath(argv[6]);
            if(!fs::is_directory(directory))throw Failure("output","Existing output directory required");
        }
        std::vector<float> times;
        for(int i=firstTime;i<argc;++i){
            char* end=nullptr;float t=std::strtof(argv[i],&end);
            if(!end || *end || !std::isfinite(t) || t<0 || t>7200)throw Failure("arguments","Invalid finite time");
            times.push_back(t);
        }
        auto output=[&](const std::string& kind,size_t frame){return directory/(kind+"-"+std::to_string(frame)+".raw");};
        if(!timing)for(size_t frame=0;frame<times.size();++frame)for(const std::string kind:{"seed","field","displacement","previous","moments"})
            if(fs::exists(output(kind,frame)))throw Failure("output","Refusing existing output");
        Context context;context.initialize(info,4,3);GlApi gl;gl.initialize();
        auto dispatch=Context::loadFunction<PFNGLDISPATCHCOMPUTEPROC>("glDispatchCompute");
        auto bind=Context::loadFunction<PFNGLBINDIMAGETEXTUREPROC>("glBindImageTexture");
        auto barrier=Context::loadFunction<PFNGLMEMORYBARRIERPROC>("glMemoryBarrier");
        GLint invocations=0,shared=0,images=0,stageImages=0;
        glGetIntegerv(GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS,&invocations);glGetIntegerv(GL_MAX_COMPUTE_SHARED_MEMORY_SIZE,&shared);
        glGetIntegerv(GL_MAX_IMAGE_UNITS,&images);glGetIntegerv(GL_MAX_COMPUTE_IMAGE_UNIFORMS,&stageImages);
        if(invocations<64 || shared<1536 || images<5 || stageImages<5 || info.maxTextureSize<128)throw Failure("limits","Insufficient spectral dynamics limits");
        RenderObjects objects(gl);objects.inputs.resize(7);glGenTextures(7,objects.inputs.data());
        const GLenum formats[7]={GL_RG32F,GL_RGBA32F,GL_RGBA32F,GL_RG32F,GL_RG32F,GL_RG32F,GL_RGBA32F};
        const int widths[7]={128,128,128,128,128,128,2},heights[7]={64,64,64,64,64,64,66};
        for(int i=0;i<7;++i){std::vector<float> zero(static_cast<size_t>(widths[i])*heights[i]*4,0.f);glBindTexture(GL_TEXTURE_2D,objects.inputs[i]);textureParameters();glTexImage2D(GL_TEXTURE_2D,0,formats[i],widths[i],heights[i],0,GL_RGBA,GL_FLOAT,zero.data());}
        glBindTexture(GL_TEXTURE_2D,0);checkGl("dynamics allocation");
        Program setup(gl),rows(gl),columns(gl),moments(gl);setup.buildCompute(argv[2]);rows.buildCompute(argv[3]);columns.buildCompute(argv[4]);moments.buildCompute(argv[5]);
        auto image=[&](GLuint program,const char* name,int unit,int index,GLenum access){
            GLint location=gl.GetUniformLocation(program,name);if(location<0 || uniformType(gl,program,name)!=GL_IMAGE_2D)throw Failure("image",std::string("Missing/mistyped image: ")+name);
            bind(unit,objects.inputs[index],0,GL_FALSE,0,access,formats[index]);gl.Uniform1i(location,unit);
        };
        auto sync=[&](){barrier(GL_SHADER_IMAGE_ACCESS_BARRIER_BIT|GL_TEXTURE_FETCH_BARRIER_BIT|GL_TEXTURE_UPDATE_BARRIER_BIT);checkGl("dynamics dispatch/barrier");};
        gl.UseProgram(setup.id());image(setup.id(),"waterSpectrumSeed",0,0,GL_WRITE_ONLY);image(setup.id(),"waterFftDisplacement",1,4,GL_WRITE_ONLY);
        image(setup.id(),"waterFftPreviousDisplacement",2,5,GL_WRITE_ONLY);image(setup.id(),"waterFftMomentAtlas",3,6,GL_WRITE_ONLY);dispatch(16,8,1);sync();
        if(suppliedSeed){
            ImageSpec input;input.width=128;input.height=64;input.path=argv[7];
            auto data=readPixelsFile(input);
            glBindTexture(GL_TEXTURE_2D,objects.inputs[0]);
            glTexSubImage2D(GL_TEXTURE_2D,0,0,0,128,64,GL_RGBA,GL_FLOAT,data.data());
            glBindTexture(GL_TEXTURE_2D,0);sync();
        }
        auto advance=[&](float seconds){
            gl.UseProgram(rows.id());image(rows.id(),"waterSpectrumSeed",0,0,GL_READ_ONLY);image(rows.id(),"waterFftRows",1,1,GL_WRITE_ONLY);
            image(rows.id(),"waterFftDisplacementRows",2,3,GL_WRITE_ONLY);image(rows.id(),"waterFftMomentAtlas",3,6,GL_WRITE_ONLY);
            GLint time=gl.GetUniformLocation(rows.id(),"frameTimeCounter");if(time>=0)gl.Uniform1f(time,seconds);dispatch(2,64,1);sync();
            gl.UseProgram(columns.id());image(columns.id(),"waterFftRows",0,1,GL_READ_ONLY);image(columns.id(),"waterFftOutput",1,2,GL_WRITE_ONLY);
            image(columns.id(),"waterFftDisplacementRows",2,3,GL_READ_ONLY);image(columns.id(),"waterFftDisplacement",3,4,GL_READ_WRITE);
            image(columns.id(),"waterFftPreviousDisplacement",4,5,GL_WRITE_ONLY);dispatch(2,64,1);sync();
            gl.UseProgram(moments.id());image(moments.id(),"waterFftMomentAtlas",0,6,GL_READ_WRITE);
            time=gl.GetUniformLocation(moments.id(),"frameTimeCounter");if(time<0)throw Failure("uniform","Missing moment frame time");gl.Uniform1f(time,seconds);dispatch(2,1,1);sync();
        };
        std::vector<GLuint64> samples;
        if(timing){
            auto gen=Context::loadFunction<PFNGLGENQUERIESPROC>("glGenQueries");
            auto release=Context::loadFunction<PFNGLDELETEQUERIESPROC>("glDeleteQueries");
            auto start=Context::loadFunction<PFNGLBEGINQUERYPROC>("glBeginQuery");
            auto stop=Context::loadFunction<PFNGLENDQUERYPROC>("glEndQuery");
            auto receive=Context::loadFunction<PFNGLGETQUERYOBJECTUI64VPROC>("glGetQueryObjectui64v");
            auto query=Context::loadFunction<PFNGLGETQUERYIVPROC>("glGetQueryiv");
            GLint bits=0;query(GL_TIME_ELAPSED,GL_QUERY_COUNTER_BITS,&bits);
            if(bits<=0)throw Failure("timing","GPU elapsed timer unavailable");
            for(int i=0;i<6;++i)advance(times[0]+float(i)/60.f);
            glFinish();
            struct QueryOwner{
                PFNGLDELETEQUERIESPROC release;
                std::array<GLuint,25> ids{};
                ~QueryOwner(){release(static_cast<GLsizei>(ids.size()),ids.data());}
            } queries{release,{}};
            gen(static_cast<GLsizei>(queries.ids.size()),queries.ids.data());
            for(size_t i=0;i<queries.ids.size();++i){
                start(GL_TIME_ELAPSED,queries.ids[i]);
                advance(times[0]+float(i+6)/60.f);
                stop(GL_TIME_ELAPSED);
            }
            for(auto id:queries.ids){
                GLuint64 ns=0;receive(id,GL_QUERY_RESULT,&ns);
                if(!ns)throw Failure("timing","Empty elapsed-time query");
                samples.push_back(ns);
            }
            // Check the last pass published a fresh frame after the timer stops.
            std::vector<float> atlas(2*66*4);
            glBindTexture(GL_TEXTURE_2D,objects.inputs[6]);glGetTexImage(GL_TEXTURE_2D,0,GL_RGBA,GL_FLOAT,atlas.data());
            if(atlas[65*8]!=times[0]+30.f/60.f || atlas[65*8+2]!=1.f || atlas[64*8]<=0.f)
                throw Failure("timing","The timed moment reduction did not publish the final field");
            checkGl("timed spectral update");
        }
        if(!timing)for(size_t frame=0;frame<times.size();++frame){
            advance(times[frame]);
            const int indices[5]={0,2,4,5,6};const std::string names[5]={"seed","field","displacement","previous","moments"};
            for(int i=0;i<5;++i){int index=indices[i];std::vector<float> data(static_cast<size_t>(widths[index])*heights[index]*4);
                glBindTexture(GL_TEXTURE_2D,objects.inputs[index]);glGetTexImage(GL_TEXTURE_2D,0,GL_RGBA,GL_FLOAT,data.data());checkGl("dynamics readback");
                if(!std::all_of(data.begin(),data.end(),[](float v){return std::isfinite(v);}))throw Failure("readback","Nonfinite spectral image");
                writePixelsFile(output(names[i],frame).string(),data);
            }
        }
        gl.UseProgram(0);
        std::cout<<"{\"ok\":true,\"gl\":"<<info.json()<<",\"frames\":"<<times.size()<<",\"image_bytes\":526400,\"peak_bound_images\":5,\"shared_bytes_per_fft_group\":1536,\"elapsed_nanoseconds\":[";
        for(size_t i=0;i<samples.size();++i){if(i)std::cout<<",";std::cout<<samples[i];}
        std::cout<<"]}"<<std::endl;
        return 0;
    }catch(const Failure& e){std::cerr<<"{\"ok\":false,\"stage\":"<<jsonQuote(e.stage)<<",\"message\":"<<jsonQuote(e.what())<<"}"<<std::endl;return 1;}
    catch(const std::exception& e){std::cerr<<"{\"ok\":false,\"message\":"<<jsonQuote(e.what())<<"}"<<std::endl;return 1;}
}
