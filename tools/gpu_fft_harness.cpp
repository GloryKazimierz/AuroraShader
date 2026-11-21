// Native fixed-size two-cascade compute proof. Never opens or modifies Minecraft.
// Reuses the existing context, diagnostics, file guards and installed GL stack.
#define main auroraGraphicsHarnessMain
#include "gpu_harness.cpp"
#undef main

int main(int argc,char** argv){
    GlInfo info;std::vector<GLuint64> timings;
    try{
        const std::string command=argc>1?argv[1]:"";
        if(command!="--probe" && command!="--run" && command!="--time")throw Failure("arguments","--probe | --run SETUP ROWS COLUMNS SECONDS SEED_OUT FIELD_OUT [SEED_INPUT] | --time SETUP ROWS COLUMNS SECONDS");
        if((command=="--probe" && argc!=2) || (command=="--run" && argc!=8 && argc!=9) || (command=="--time" && argc!=6))throw Failure("arguments","Wrong argument count");
        if(command=="--run"){
            for(int index:{6,7})if(fs::exists(absolutePath(argv[index])))throw Failure("output","Refusing existing output");
            if(absolutePath(argv[6])==absolutePath(argv[7]))throw Failure("output","Distinct outputs required");
        }
        Context context;context.initialize(info,4,3);GlApi gl;gl.initialize();
        auto dispatch=Context::loadFunction<PFNGLDISPATCHCOMPUTEPROC>("glDispatchCompute");
        auto bind=Context::loadFunction<PFNGLBINDIMAGETEXTUREPROC>("glBindImageTexture");
        auto barrier=Context::loadFunction<PFNGLMEMORYBARRIERPROC>("glMemoryBarrier");
        auto indexed=Context::loadFunction<PFNGLGETINTEGERI_VPROC>("glGetIntegeri_v");
        GLint invocations=0,shared=0,images=0,stageImages=0,local[3]={},groups[3]={};
        glGetIntegerv(GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS,&invocations);
        glGetIntegerv(GL_MAX_COMPUTE_SHARED_MEMORY_SIZE,&shared);
        glGetIntegerv(GL_MAX_IMAGE_UNITS,&images);
        glGetIntegerv(GL_MAX_COMPUTE_IMAGE_UNIFORMS,&stageImages);
        for(int axis=0;axis<3;++axis){indexed(GL_MAX_COMPUTE_WORK_GROUP_SIZE,axis,&local[axis]);indexed(GL_MAX_COMPUTE_WORK_GROUP_COUNT,axis,&groups[axis]);}
        checkGl("compute limits");
        if(invocations<64 || shared<1024 || images<2 || stageImages<2 || local[0]<64 || local[1]<8 || groups[0]<16 || groups[1]<64 || info.maxTextureSize<128)
            throw Failure("compute capability","Insufficient limits for two64-square cascades");
        if(command=="--run" || command=="--time"){
            char* end=nullptr;float seconds=std::strtof(argv[5],&end);
            if(!end || *end || !std::isfinite(seconds) || seconds<0 || seconds>7200)throw Failure("arguments","Invalid time");
            RenderObjects objects(gl);objects.inputs.resize(3);glGenTextures(3,objects.inputs.data());
            const GLenum formats[3]={GL_RG32F,GL_RGBA32F,GL_RGBA32F};
            std::vector<float> blank(128*64*4,0.f);
            for(int index=0;index<3;++index){glBindTexture(GL_TEXTURE_2D,objects.inputs[index]);textureParameters();glTexImage2D(GL_TEXTURE_2D,0,formats[index],128,64,0,GL_RGBA,GL_FLOAT,blank.data());}
            glBindTexture(GL_TEXTURE_2D,0);checkGl("compute image allocation");
            Program setup(gl),rows(gl),columns(gl);setup.buildCompute(argv[2]);rows.buildCompute(argv[3]);columns.buildCompute(argv[4]);
            auto image=[&](GLuint program,const char* name,int unit,int index,GLenum access){
                GLint location=gl.GetUniformLocation(program,name);if(location<0)throw Failure("image binding",std::string("Missing active image ")+name);
                if(uniformType(gl,program,name)!=GL_IMAGE_2D)throw Failure("image binding","Image uniform type mismatch");
                bind(unit,objects.inputs[index],0,GL_FALSE,0,access,formats[index]);gl.Uniform1i(location,unit);
            };
            auto sync=[&](){barrier(GL_SHADER_IMAGE_ACCESS_BARRIER_BIT|GL_TEXTURE_FETCH_BARRIER_BIT|GL_TEXTURE_UPDATE_BARRIER_BIT);checkGl("compute dispatch/barrier");};
            gl.UseProgram(setup.id());image(setup.id(),"waterSpectrumSeed",0,0,GL_WRITE_ONLY);dispatch(16,8,1);sync();
            if(argc==9){ImageSpec input;input.width=128;input.height=64;input.path=argv[8];auto values=readPixelsFile(input);
                glBindTexture(GL_TEXTURE_2D,objects.inputs[0]);glTexSubImage2D(GL_TEXTURE_2D,0,0,0,128,64,GL_RGBA,GL_FLOAT,values.data());glBindTexture(GL_TEXTURE_2D,0);sync();}
            auto frame=[&](float now){
                gl.UseProgram(rows.id());image(rows.id(),"waterSpectrumSeed",0,0,GL_READ_ONLY);image(rows.id(),"waterFftRows",1,1,GL_WRITE_ONLY);
                GLint time=gl.GetUniformLocation(rows.id(),"frameTimeCounter");if(time>=0)gl.Uniform1f(time,now);dispatch(2,64,1);sync();
                gl.UseProgram(columns.id());image(columns.id(),"waterFftRows",0,1,GL_READ_ONLY);image(columns.id(),"waterFftOutput",1,2,GL_WRITE_ONLY);dispatch(2,64,1);sync();
            };
            if(command=="--time"){
                auto gen=Context::loadFunction<PFNGLGENQUERIESPROC>("glGenQueries");
                auto release=Context::loadFunction<PFNGLDELETEQUERIESPROC>("glDeleteQueries");
                auto start=Context::loadFunction<PFNGLBEGINQUERYPROC>("glBeginQuery");
                auto stop=Context::loadFunction<PFNGLENDQUERYPROC>("glEndQuery");
                auto result=Context::loadFunction<PFNGLGETQUERYOBJECTUI64VPROC>("glGetQueryObjectui64v");
                auto query=Context::loadFunction<PFNGLGETQUERYIVPROC>("glGetQueryiv");
                GLint bits=0;query(GL_TIME_ELAPSED,GL_QUERY_COUNTER_BITS,&bits);
                if(bits<=0)throw Failure("timing","Elapsed timer unavailable");
                for(int i=0;i<6;++i)frame(seconds+float(i)/60.f);
                glFinish();
                struct QueryOwner{PFNGLDELETEQUERIESPROC release;std::array<GLuint,25> ids{};
                    ~QueryOwner(){release(static_cast<GLsizei>(ids.size()),ids.data());}} owner{release,{}};
                gen(static_cast<GLsizei>(owner.ids.size()),owner.ids.data());
                for(size_t i=0;i<owner.ids.size();++i){start(GL_TIME_ELAPSED,owner.ids[i]);frame(seconds+float(i+6)/60.f);stop(GL_TIME_ELAPSED);}
                for(GLuint id:owner.ids){GLuint64 ns=0;result(id,GL_QUERY_RESULT,&ns);timings.push_back(ns);}
                checkGl("compute timing");
            }else frame(seconds);
            if(command=="--run")for(int index:{0,2}){
                std::vector<float> pixels(128*64*4);glBindTexture(GL_TEXTURE_2D,objects.inputs[index]);glGetTexImage(GL_TEXTURE_2D,0,GL_RGBA,GL_FLOAT,pixels.data());checkGl("compute image readback");
                if(!std::all_of(pixels.begin(),pixels.end(),[](float v){return std::isfinite(v);}))throw Failure("readback","Nonfinite compute output");
                writePixelsFile(argv[index==0?6:7],pixels);
            }
            gl.UseProgram(0);
        }
        std::cout<<"{\"ok\":true,\"gl\":"<<info.json()<<",\"dispatch_verified\":"<<(command!="--probe"?"true":"false")
            <<",\"max_invocations\":"<<invocations<<",\"shared_bytes\":"<<shared<<",\"image_units\":"<<images
            <<",\"compute_image_uniforms\":"<<stageImages<<",\"allocated_image_bytes\":327680,\"elapsed_nanoseconds\":[";
        for(size_t i=0;i<timings.size();++i){if(i)std::cout<<",";std::cout<<timings[i];}
        std::cout<<"]}"<<std::endl;
        return 0;
    }catch(const Failure& error){std::cerr<<"{\"ok\":false,\"stage\":"<<jsonQuote(error.stage)<<",\"message\":"<<jsonQuote(error.what())<<"}"<<std::endl;return 1;}
    catch(const std::exception& error){std::cerr<<"{\"ok\":false,\"message\":"<<jsonQuote(error.what())<<"}"<<std::endl;return 1;}
}
