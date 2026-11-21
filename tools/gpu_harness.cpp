// AuroraShader native OpenGL validation, not an Iris/Minecraft runtime.
// Build on Windows with MinGW: g++ -std=c++17 -O2 -static gpu_harness.cpp
//     -lopengl32 -lgdi32 -luser32 -o gpu_harness.exe
// This process owns one never-shown window and renders only to its own FBO.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <GL/gl.h>
#include <GL/glext.h>
#include <GL/wglext.h>

#include <algorithm>
#include <array>
#include <cerrno>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace fs = std::filesystem;
namespace {
constexpr std::size_t MAX_SOURCE_BYTES = 8u * 1024u * 1024u;
constexpr std::size_t MAX_LOG_BYTES = 1024u * 1024u;
constexpr std::size_t MAX_MANIFEST_BYTES = 16u * 1024u * 1024u;
constexpr std::size_t MAX_PIXELS = 4u * 1024u * 1024u;
constexpr std::size_t MAX_INPUT_BYTES = 256u * 1024u * 1024u;
constexpr int MAX_EXTENT = 4096;
constexpr int MAX_TEXTURES = 16;
constexpr std::size_t MAX_BATCH_CASES = 16384;

struct Failure : std::runtime_error {
    std::string stage;
    DWORD windowsCode = 0;
    GLenum glCode = GL_NO_ERROR;
    Failure(std::string where, std::string message, DWORD win = 0,
            GLenum gl = GL_NO_ERROR)
        : std::runtime_error(std::move(message)), stage(std::move(where)),
          windowsCode(win), glCode(gl) {}
};

std::string utf8(const std::wstring& text) {
    if (text.empty()) return {};
    int length = WideCharToMultiByte(CP_UTF8, 0, text.data(),
        static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
    std::string result(static_cast<std::size_t>(std::max(length, 0)), '\0');
    if (length > 0) WideCharToMultiByte(CP_UTF8, 0, text.data(),
        static_cast<int>(text.size()), result.data(), length, nullptr, nullptr);
    return result;
}

std::string windowsMessage(DWORD code) {
    wchar_t* buffer = nullptr;
    DWORD length = FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER |
        FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        nullptr, code, 0, reinterpret_cast<wchar_t*>(&buffer), 0, nullptr);
    std::wstring message = length ? std::wstring(buffer, length) : L"No system description";
    if (buffer) LocalFree(buffer);
    while (!message.empty() && (message.back() == L'\n' || message.back() == L'\r'))
        message.pop_back();
    return utf8(message);
}

[[noreturn]] void failWindows(const std::string& stage, DWORD code) {
    throw Failure(stage, stage + " failed: " + windowsMessage(code), code);
}

std::string jsonQuote(const std::string& value) {
    std::ostringstream out;
    out << '"';
    for (unsigned char c : value) {
        switch (c) {
        case '"': out << "\\\""; break;
        case '\\': out << "\\\\"; break;
        case '\b': out << "\\b"; break;
        case '\f': out << "\\f"; break;
        case '\n': out << "\\n"; break;
        case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default:
            if (c < 0x20) out << "\\u00" << std::hex << std::setw(2)
                             << std::setfill('0') << static_cast<int>(c) << std::dec;
            else out << static_cast<char>(c);
        }
    }
    out << '"';
    return out.str();
}

void checkGl(const std::string& stage) {
    GLenum error = glGetError();
    if (error != GL_NO_ERROR) {
        std::ostringstream message;
        message << stage << " produced OpenGL error 0x" << std::hex << error;
        throw Failure(stage, message.str(), 0, error);
    }
}

fs::path absolutePath(const std::string& value) {
    if (value.empty() || value.find('\0') != std::string::npos)
        throw Failure("input", "Empty path or embedded NUL");
    fs::path path = fs::u8path(value);
    if (!path.is_absolute()) throw Failure("input", "Expected absolute path: " + value);
    return path;
}

std::string readText(const std::string& name, std::size_t maximum) {
    fs::path path = absolutePath(name);
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file) throw Failure("input", "Cannot open file: " + name);
    std::streamoff length = file.tellg();
    if (length < 0 || static_cast<std::uint64_t>(length) > maximum)
        throw Failure("input", "File exceeds size limit: " + name);
    std::string result(static_cast<std::size_t>(length), '\0');
    file.seekg(0);
    if (length && !file.read(result.data(), length))
        throw Failure("input", "Cannot read complete file: " + name);
    if (result.find('\0') != std::string::npos)
        throw Failure("input", "Text file contains embedded NUL: " + name);
    return result;
}

struct GlInfo {
    std::string vendor, renderer, version, glsl;
    GLint major = 0, minor = 0, profileMask = 0, maxTextureSize = 0, maxTextureUnits = 0;
    GLint maxDrawBuffers = 0, maxColorAttachments = 0;
    bool ready = false;
    std::string json() const {
        if (!ready) return "null";
        std::ostringstream out;
        out << "{\"vendor\":" << jsonQuote(vendor)
            << ",\"renderer\":" << jsonQuote(renderer)
            << ",\"version\":" << jsonQuote(version)
            << ",\"glsl_version\":" << jsonQuote(glsl)
            << ",\"major\":" << major << ",\"minor\":" << minor
            << ",\"profile_mask\":" << profileMask
            << ",\"profile\":\"compatibility\""
            << ",\"max_texture_size\":" << maxTextureSize
            << ",\"max_texture_units\":" << maxTextureUnits
            << ",\"max_draw_buffers\":" << maxDrawBuffers
            << ",\"max_color_attachments\":" << maxColorAttachments << '}';
        return out.str();
    }
};

class Context {
    HINSTANCE instance_ = nullptr;
    ATOM classAtom_ = 0;
    HWND window_ = nullptr;
    HDC dc_ = nullptr;
    HGLRC bootstrap_ = nullptr, modern_ = nullptr;
    static constexpr const wchar_t* CLASS_NAME = L"AuroraShaderHiddenGpuValidation";
public:
    Context() = default;
    Context(const Context&) = delete;
    Context& operator=(const Context&) = delete;
    ~Context() {
        HGLRC current = wglGetCurrentContext();
        if (current && (current == modern_ || current == bootstrap_))
            wglMakeCurrent(nullptr, nullptr);
        if (modern_) wglDeleteContext(modern_);
        if (bootstrap_) wglDeleteContext(bootstrap_);
        if (dc_ && window_) ReleaseDC(window_, dc_);
        if (window_) DestroyWindow(window_);
        if (classAtom_) UnregisterClassW(CLASS_NAME, instance_);
    }
    static PROC load(const char* name) {
        PROC result = wglGetProcAddress(name);
        std::intptr_t address = reinterpret_cast<std::intptr_t>(result);
        if (!result || address == 1 || address == 2 || address == 3 || address == -1)
            result = GetProcAddress(GetModuleHandleW(L"opengl32.dll"), name);
        if (!result) throw Failure("OpenGL loader", std::string("Unavailable function: ") + name);
        return result;
    }
    template<class Function> static Function loadFunction(const char* name) {
        // WGL supplies an untyped function pointer. The void() bridge is GCC's
        // documented generic function-pointer form; Windows preserves its address.
        return reinterpret_cast<Function>(reinterpret_cast<void(*)()>(load(name)));
    }
    void initialize(GlInfo& info) {
        instance_ = GetModuleHandleW(nullptr);
        WNDCLASSW description{};
        description.style = CS_OWNDC;
        description.lpfnWndProc = DefWindowProcW;
        description.hInstance = instance_;
        description.lpszClassName = CLASS_NAME;
        classAtom_ = RegisterClassW(&description);
        if (!classAtom_) failWindows("RegisterClassW", GetLastError());
        // Neither WS_VISIBLE nor any show, activate, focus or swap call is used.
        window_ = CreateWindowExW(WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, CLASS_NAME,
            L"AuroraShader hidden validation", WS_POPUP, 0, 0, 16, 16,
            nullptr, nullptr, instance_, nullptr);
        if (!window_) failWindows("CreateWindowExW", GetLastError());
        dc_ = GetDC(window_);
        if (!dc_) failWindows("GetDC", GetLastError());
        PIXELFORMATDESCRIPTOR pixel{};
        pixel.nSize = sizeof(pixel);
        pixel.nVersion = 1;
        pixel.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL;
        pixel.iPixelType = PFD_TYPE_RGBA;
        pixel.cColorBits = 32;
        pixel.cAlphaBits = 8;
        pixel.iLayerType = PFD_MAIN_PLANE;
        int format = ChoosePixelFormat(dc_, &pixel);
        if (!format) failWindows("ChoosePixelFormat", GetLastError());
        if (!SetPixelFormat(dc_, format, &pixel)) failWindows("SetPixelFormat", GetLastError());
        bootstrap_ = wglCreateContext(dc_);
        if (!bootstrap_) failWindows("wglCreateContext", GetLastError());
        if (!wglMakeCurrent(dc_, bootstrap_)) failWindows("wglMakeCurrent bootstrap", GetLastError());
        auto create = loadFunction<PFNWGLCREATECONTEXTATTRIBSARBPROC>("wglCreateContextAttribsARB");
        const int attributes[] = {WGL_CONTEXT_MAJOR_VERSION_ARB, 3,
            WGL_CONTEXT_MINOR_VERSION_ARB, 3, WGL_CONTEXT_PROFILE_MASK_ARB,
            WGL_CONTEXT_COMPATIBILITY_PROFILE_BIT_ARB, 0};
        modern_ = create(dc_, nullptr, attributes);
        if (!modern_) failWindows("wglCreateContextAttribsARB 3.3 compatibility", GetLastError());
        if (!wglMakeCurrent(dc_, modern_)) failWindows("wglMakeCurrent modern", GetLastError());
        wglDeleteContext(bootstrap_);
        bootstrap_ = nullptr;
        auto text = [](GLenum key) {
            const GLubyte* value = glGetString(key);
            if (!value) throw Failure("OpenGL probe", "glGetString returned null");
            return std::string(reinterpret_cast<const char*>(value));
        };
        info.vendor = text(GL_VENDOR);
        info.renderer = text(GL_RENDERER);
        info.version = text(GL_VERSION);
        info.glsl = text(GL_SHADING_LANGUAGE_VERSION);
        glGetIntegerv(GL_MAJOR_VERSION, &info.major);
        glGetIntegerv(GL_MINOR_VERSION, &info.minor);
        glGetIntegerv(GL_CONTEXT_PROFILE_MASK, &info.profileMask);
        glGetIntegerv(GL_MAX_TEXTURE_SIZE, &info.maxTextureSize);
        glGetIntegerv(GL_MAX_TEXTURE_IMAGE_UNITS, &info.maxTextureUnits);
        glGetIntegerv(GL_MAX_DRAW_BUFFERS, &info.maxDrawBuffers);
        glGetIntegerv(GL_MAX_COLOR_ATTACHMENTS, &info.maxColorAttachments);
        checkGl("OpenGL probe");
        if (info.major < 3 || (info.major == 3 && info.minor < 3)
            || !(info.profileMask & GL_CONTEXT_COMPATIBILITY_PROFILE_BIT))
            throw Failure("OpenGL probe", "Driver did not provide OpenGL >=3.3 compatibility");
        info.ready = true;
    }
};

#define GL_FUNCTIONS(X) \
    X(PFNGLCREATESHADERPROC, CreateShader) \
    X(PFNGLSHADERSOURCEPROC, ShaderSource) \
    X(PFNGLCOMPILESHADERPROC, CompileShader) \
    X(PFNGLGETSHADERIVPROC, GetShaderiv) \
    X(PFNGLGETSHADERINFOLOGPROC, GetShaderInfoLog) \
    X(PFNGLDELETESHADERPROC, DeleteShader) \
    X(PFNGLCREATEPROGRAMPROC, CreateProgram) \
    X(PFNGLATTACHSHADERPROC, AttachShader) \
    X(PFNGLLINKPROGRAMPROC, LinkProgram) \
    X(PFNGLGETPROGRAMIVPROC, GetProgramiv) \
    X(PFNGLGETPROGRAMINFOLOGPROC, GetProgramInfoLog) \
    X(PFNGLDELETEPROGRAMPROC, DeleteProgram) \
    X(PFNGLUSEPROGRAMPROC, UseProgram) \
    X(PFNGLGETUNIFORMLOCATIONPROC, GetUniformLocation) \
    X(PFNGLGETUNIFORMINDICESPROC, GetUniformIndices) \
    X(PFNGLGETACTIVEUNIFORMSIVPROC, GetActiveUniformsiv) \
    X(PFNGLUNIFORM1FPROC, Uniform1f) \
    X(PFNGLUNIFORM2FPROC, Uniform2f) \
    X(PFNGLUNIFORM3FPROC, Uniform3f) \
    X(PFNGLUNIFORM4FPROC, Uniform4f) \
    X(PFNGLUNIFORM1IPROC, Uniform1i) \
    X(PFNGLUNIFORM2IPROC, Uniform2i) \
    X(PFNGLUNIFORM3IPROC, Uniform3i) \
    X(PFNGLUNIFORM4IPROC, Uniform4i) \
    X(PFNGLUNIFORMMATRIX4FVPROC, UniformMatrix4fv) \
    X(PFNGLACTIVETEXTUREPROC, ActiveTexture) \
    X(PFNGLCLEARBUFFERFVPROC, ClearBufferfv) \
    X(PFNGLDRAWBUFFERSPROC, DrawBuffers) \
    X(PFNGLGENFRAMEBUFFERSPROC, GenFramebuffers) \
    X(PFNGLBINDFRAMEBUFFERPROC, BindFramebuffer) \
    X(PFNGLFRAMEBUFFERTEXTURE2DPROC, FramebufferTexture2D) \
    X(PFNGLCHECKFRAMEBUFFERSTATUSPROC, CheckFramebufferStatus) \
    X(PFNGLDELETEFRAMEBUFFERSPROC, DeleteFramebuffers)

struct GlApi {
#define DECLARE(type, name) type name = nullptr;
    GL_FUNCTIONS(DECLARE)
#undef DECLARE
    void initialize() {
#define LOAD(type, name) name = Context::loadFunction<type>("gl" #name);
        GL_FUNCTIONS(LOAD)
#undef LOAD
    }
};

class Program {
    const GlApi& gl_;
    GLuint vertex_ = 0, fragment_ = 0, program_ = 0;
    std::string log(GLuint object, bool program) const {
        GLint size = 0;
        if (program) gl_.GetProgramiv(object, GL_INFO_LOG_LENGTH, &size);
        else gl_.GetShaderiv(object, GL_INFO_LOG_LENGTH, &size);
        if (size <= 1) return "(driver supplied no diagnostic log)";
        GLsizei bounded = static_cast<GLsizei>(std::min<std::size_t>(size, MAX_LOG_BYTES));
        std::string result(static_cast<std::size_t>(bounded), '\0');
        GLsizei written = 0;
        if (program) gl_.GetProgramInfoLog(object, bounded, &written, result.data());
        else gl_.GetShaderInfoLog(object, bounded, &written, result.data());
        result.resize(static_cast<std::size_t>(std::max(written, 0)));
        if (size > bounded) result += "\n[driver log truncated at 1 MiB]";
        return result;
    }
    void compile(GLuint& shader, GLenum kind, const std::string& path) {
        std::string source = readText(path, MAX_SOURCE_BYTES);
        if (source.empty()) throw Failure("shader input", "Empty shader: " + path);
        shader = gl_.CreateShader(kind);
        if (!shader) throw Failure("shader creation", "glCreateShader returned zero: " + path);
        const GLchar* data = source.data();
        GLint length = static_cast<GLint>(source.size());
        gl_.ShaderSource(shader, 1, &data, &length);
        gl_.CompileShader(shader);
        GLint passed = GL_FALSE;
        gl_.GetShaderiv(shader, GL_COMPILE_STATUS, &passed);
        if (passed != GL_TRUE) throw Failure("shader compilation", path + "\n" + log(shader, false));
        checkGl("shader compilation");
    }
public:
    explicit Program(const GlApi& gl) : gl_(gl) {}
    Program(const Program&) = delete;
    Program& operator=(const Program&) = delete;
    ~Program() {
        if (program_) gl_.DeleteProgram(program_);
        if (vertex_) gl_.DeleteShader(vertex_);
        if (fragment_) gl_.DeleteShader(fragment_);
    }
    void build(const std::string& vertex, const std::string& fragment) {
        compile(vertex_, GL_VERTEX_SHADER, vertex);
        compile(fragment_, GL_FRAGMENT_SHADER, fragment);
        program_ = gl_.CreateProgram();
        if (!program_) throw Failure("program creation", "glCreateProgram returned zero");
        gl_.AttachShader(program_, vertex_);
        gl_.AttachShader(program_, fragment_);
        gl_.LinkProgram(program_);
        GLint passed = GL_FALSE;
        gl_.GetProgramiv(program_, GL_LINK_STATUS, &passed);
        if (passed != GL_TRUE) throw Failure("program link", vertex + " + " + fragment + "\n" + log(program_, true));
        checkGl("program link");
    }
    GLuint id() const { return program_; }
};

std::string token(std::istringstream& line) {
    std::string result;
    if (!(line >> result)) throw Failure("manifest", "Missing token");
    return result;
}
std::string quoted(std::istringstream& line) {
    line >> std::ws;
    if (line.peek() != '"') throw Failure("manifest", "Expected double-quoted string");
    std::string result;
    if (!(line >> std::quoted(result)) || result.size() > 32768)
        throw Failure("manifest", "Invalid or excessive quoted string");
    for (unsigned char ch : result)
        if (ch < 0x20) throw Failure("manifest", "Control character in quoted string");
    return result;
}
void endLine(std::istringstream& line) {
    line >> std::ws;
    if (!line.eof()) throw Failure("manifest", "Unexpected trailing tokens");
}
int integer(const std::string& value) {
    int result = 0;
    const auto parsed = std::from_chars(value.data(), value.data() + value.size(), result);
    if (parsed.ec != std::errc() || parsed.ptr != value.data() + value.size())
        throw Failure("manifest", "Invalid int32 token: " + value);
    return result;
}
float real(const std::string& value) {
    char* end = nullptr;
    errno = 0;
    float result = std::strtof(value.c_str(), &end);
    if (end == value.c_str() || end != value.c_str() + value.size() || errno == ERANGE)
        throw Failure("manifest", "Invalid float32 token: " + value);
    // Explicit nan/inf are allowed for testing shader invalid-input defenses.
    return result;
}
void identifier(const std::string& name) {
    auto alpha = [](char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'; };
    if (name.empty() || name.size() > 128 || !alpha(name[0]))
        throw Failure("manifest", "Invalid uniform name: " + name);
    for (char c : name) if (!alpha(c) && !(c >= '0' && c <= '9'))
        throw Failure("manifest", "Invalid uniform name: " + name);
}
std::size_t pixels(int width, int height) {
    if (width <= 0 || height <= 0 || width > MAX_EXTENT || height > MAX_EXTENT)
        throw Failure("manifest", "Image extents must be in [1,4096]");
    std::size_t count = static_cast<std::size_t>(width) * static_cast<std::size_t>(height);
    if (count > MAX_PIXELS) throw Failure("manifest", "Image exceeds 4194304 pixels");
    return count;
}
GLint storageFormat(const std::string& name) {
    if (name == "RGBA16") return GL_RGBA16;
    if (name == "RGBA16F") return GL_RGBA16F;
    if (name == "RGBA32F") return GL_RGBA32F;
    if (name == "R32F") return GL_R32F;
    if (name == "RG32F") return GL_RG32F;
    if (name == "R16F") return GL_R16F;
    if (name == "RGBA8") return GL_RGBA8;
    throw Failure("manifest", "Unsupported storage format: " + name);
}

template<class Function> void manifestLines(const std::string& path, Function function) {
    std::istringstream file(readText(path, MAX_MANIFEST_BYTES));
    std::string text;
    std::size_t number = 0;
    while (std::getline(file, text)) {
        ++number;
        if (text.size() > 65536) throw Failure("manifest", "Line exceeds 65536 bytes");
        std::istringstream line(text);
        line.imbue(std::locale::classic());
        line >> std::ws;
        if (line.eof() || line.peek() == '#') continue;
        try { function(line); endLine(line); }
        catch (const Failure& error) {
            throw Failure(error.stage, path + ":" + std::to_string(number) + ": " + error.what(),
                          error.windowsCode, error.glCode);
        }
    }
}

struct CompileCase { std::string label, vertex, fragment; };
std::vector<CompileCase> readBatch(const std::string& path) {
    std::vector<CompileCase> result;
    std::set<std::string> labels;
    manifestLines(path, [&](std::istringstream& line) {
        CompileCase entry{quoted(line), quoted(line), quoted(line)};
        if (entry.label.empty() || entry.label.size() > 256 || !labels.insert(entry.label).second)
            throw Failure("manifest", "Empty, excessive or duplicate case label");
        absolutePath(entry.vertex); absolutePath(entry.fragment);
        result.push_back(std::move(entry));
        if (result.size() > MAX_BATCH_CASES) throw Failure("manifest", "Too many compile cases");
    });
    if (result.empty()) throw Failure("manifest", "Compile batch is empty");
    return result;
}

struct ImageSpec { int width = 0, height = 0; std::string format, path; };
struct TextureSpec : ImageSpec { std::string name; };
struct ColorTargetSpec { int slot = 0, attachment = 0; std::string format; };
struct UniformSpec {
    std::string name, type;
    std::array<float, 16> floats{};
    std::array<int, 4> integers{};
};
struct RenderSpec {
    std::string vertex, fragment;
    ImageSpec target;
    std::vector<ColorTargetSpec> colorTargets;
    int readTarget = 0;
    std::vector<TextureSpec> textures;
    std::vector<UniformSpec> uniforms;
};
void imageFields(std::istringstream& line, ImageSpec& image) {
    image.width = integer(token(line)); image.height = integer(token(line));
    pixels(image.width, image.height);
    image.format = token(line); storageFormat(image.format);
    image.path = quoted(line); absolutePath(image.path);
}
RenderSpec readRender(const std::string& path) {
    RenderSpec result;
    bool hasShaders = false, hasTarget = false, hasReadTarget = false;
    std::set<int> targetSlots{0}, targetAttachments{0};
    std::size_t inputBytes = 0;
    std::set<std::string> names;
    manifestLines(path, [&](std::istringstream& line) {
        std::string directive = token(line);
        if (directive == "shaders") {
            if (hasShaders) throw Failure("manifest", "Duplicate shaders directive");
            hasShaders = true;
            result.vertex = quoted(line); result.fragment = quoted(line);
            absolutePath(result.vertex); absolutePath(result.fragment);
        } else if (directive == "target") {
            if (hasTarget) throw Failure("manifest", "Duplicate target directive");
            hasTarget = true; imageFields(line, result.target);
        } else if (directive == "color_target") {
            ColorTargetSpec target;
            target.slot = integer(token(line)); target.attachment = integer(token(line));
            target.format = token(line); storageFormat(target.format);
            if (target.slot < 1 || target.slot > 7 || target.attachment < 1 || target.attachment > 7)
                throw Failure("manifest", "Extra color target slots and attachments must be in [1,7]");
            if (!targetSlots.insert(target.slot).second || !targetAttachments.insert(target.attachment).second)
                throw Failure("manifest", "Duplicate color target slot or attachment");
            result.colorTargets.push_back(std::move(target));
        } else if (directive == "read_target") {
            if (hasReadTarget) throw Failure("manifest", "Duplicate read_target directive");
            hasReadTarget = true;
            result.readTarget = integer(token(line));
            if (result.readTarget < 0 || result.readTarget > 7)
                throw Failure("manifest", "Read target slot must be in [0,7]");
        } else if (directive == "texture") {
            TextureSpec texture;
            texture.name = quoted(line); identifier(texture.name);
            if (!names.insert(texture.name).second) throw Failure("manifest", "Duplicate uniform/sampler name");
            imageFields(line, texture);
            inputBytes += pixels(texture.width, texture.height) * 4 * sizeof(float);
            if (inputBytes > MAX_INPUT_BYTES || result.textures.size() >= MAX_TEXTURES)
                throw Failure("manifest", "Texture input budget exceeded (16 textures / 256 MiB)");
            result.textures.push_back(std::move(texture));
        } else if (directive == "uniform") {
            UniformSpec uniform;
            uniform.name = quoted(line); identifier(uniform.name);
            if (!names.insert(uniform.name).second) throw Failure("manifest", "Duplicate uniform/sampler name");
            uniform.type = token(line);
            if (uniform.type == "m4") {
                for (float& item : uniform.floats) item = real(token(line));
            } else if (uniform.type.size() == 2 && (uniform.type[0] == 'f' || uniform.type[0] == 'i')
                       && uniform.type[1] >= '1' && uniform.type[1] <= '4') {
                int count = uniform.type[1] - '0';
                for (int index = 0; index < count; ++index) {
                    if (uniform.type[0] == 'f') uniform.floats[index] = real(token(line));
                    else uniform.integers[index] = integer(token(line));
                }
            } else throw Failure("manifest", "Unsupported uniform type: " + uniform.type);
            if (result.uniforms.size() >= 1024) throw Failure("manifest", "Too many uniform directives");
            result.uniforms.push_back(std::move(uniform));
        } else throw Failure("manifest", "Unknown directive: " + directive);
    });
    if (!hasShaders || !hasTarget) throw Failure("manifest", "Both shaders and target directives are required");
    if (!targetSlots.count(result.readTarget)) throw Failure("manifest", "Read target slot is not defined");
    result.colorTargets.push_back({0, 0, result.target.format});
    std::sort(result.colorTargets.begin(), result.colorTargets.end(),
        [](const ColorTargetSpec& a, const ColorTargetSpec& b) { return a.slot < b.slot; });
    // Reserve an RGBA32F-sized allocation for every attachment plus one raw
    // readback, even for smaller R32F/RGBA16F storage. Input budget is separate.
    std::size_t targetBytes = pixels(result.target.width, result.target.height) * 4 * sizeof(float)
                            * (result.colorTargets.size() + 1);
    if (targetBytes > MAX_INPUT_BYTES)
        throw Failure("manifest", "Color target and readback budget exceeded (256 MiB)");
    fs::path output = absolutePath(result.target.path);
    if (!fs::is_directory(output.parent_path())) throw Failure("output", "Output parent directory does not exist");
    if (fs::exists(output)) throw Failure("output", "Refusing to overwrite output: " + result.target.path);
    return result;
}

const ColorTargetSpec& selectedTarget(const RenderSpec& spec) {
    for (const auto& target : spec.colorTargets)
        if (target.slot == spec.readTarget) return target;
    throw Failure("manifest", "Read target slot is not defined");
}

std::vector<float> readPixelsFile(const ImageSpec& image) {
    std::size_t count = pixels(image.width, image.height) * 4;
    std::size_t bytes = count * sizeof(float);
    std::ifstream file(absolutePath(image.path), std::ios::binary | std::ios::ate);
    if (!file) throw Failure("texture input", "Cannot open texture: " + image.path);
    std::streamoff length = file.tellg();
    if (length < 0 || static_cast<std::uint64_t>(length) != bytes)
        throw Failure("texture input", "Texture length must be exactly " + std::to_string(bytes) + " bytes: " + image.path);
    std::vector<float> result(count);
    file.seekg(0);
    if (!file.read(reinterpret_cast<char*>(result.data()), static_cast<std::streamsize>(bytes)))
        throw Failure("texture input", "Incomplete texture read: " + image.path);
    return result;
}
void writePixelsFile(const std::string& path, const std::vector<float>& values) {
    fs::path output = absolutePath(path);
    HANDLE handle = CreateFileW(output.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                                FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle == INVALID_HANDLE_VALUE) failWindows("CreateFileW output (no overwrite)", GetLastError());
    struct Close { HANDLE value; ~Close() { CloseHandle(value); } } close{handle};
    const auto* data = reinterpret_cast<const unsigned char*>(values.data());
    std::size_t remaining = values.size() * sizeof(float);
    while (remaining) {
        DWORD chunk = static_cast<DWORD>(std::min<std::size_t>(remaining, 16u * 1024u * 1024u));
        DWORD written = 0;
        if (!WriteFile(handle, data, chunk, &written, nullptr)) failWindows("WriteFile output", GetLastError());
        if (!written) throw Failure("output", "WriteFile made no progress; partial output retained");
        data += written; remaining -= written;
    }
}

class RenderObjects {
    const GlApi& gl_;
public:
    GLuint framebuffer = 0;
    std::vector<GLuint> targets, inputs;
    explicit RenderObjects(const GlApi& gl) : gl_(gl) {}
    RenderObjects(const RenderObjects&) = delete;
    RenderObjects& operator=(const RenderObjects&) = delete;
    ~RenderObjects() {
        gl_.UseProgram(0);
        gl_.BindFramebuffer(GL_FRAMEBUFFER, 0);
        if (framebuffer) gl_.DeleteFramebuffers(1, &framebuffer);
        if (!targets.empty()) glDeleteTextures(static_cast<GLsizei>(targets.size()), targets.data());
        if (!inputs.empty()) glDeleteTextures(static_cast<GLsizei>(inputs.size()), inputs.data());
    }
};
void textureParameters() {
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_BASE_LEVEL, 0);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAX_LEVEL, 0);
}
GLenum uniformType(const GlApi& gl, GLuint program, const std::string& name) {
    const GLchar* pointer = name.c_str();
    GLuint index = GL_INVALID_INDEX;
    gl.GetUniformIndices(program, 1, &pointer, &index);
    checkGl("uniform index " + name);
    if (index == GL_INVALID_INDEX)
        throw Failure("uniform type", "Active location has no uniform index: " + name);
    GLint type = 0;
    gl.GetActiveUniformsiv(program, 1, &index, GL_UNIFORM_TYPE, &type);
    checkGl("uniform type " + name);
    return static_cast<GLenum>(type);
}
bool compatibleUniformType(const std::string& supplied, GLenum actual) {
    if (supplied == "m4") return actual == GL_FLOAT_MAT4;
    const GLenum floats[] = {GL_FLOAT, GL_FLOAT_VEC2, GL_FLOAT_VEC3, GL_FLOAT_VEC4};
    const GLenum integers[] = {GL_INT, GL_INT_VEC2, GL_INT_VEC3, GL_INT_VEC4};
    const GLenum booleans[] = {GL_BOOL, GL_BOOL_VEC2, GL_BOOL_VEC3, GL_BOOL_VEC4};
    int index = supplied[1] - '1'; // Manifest parser already restricts f1..4/i1..4.
    return supplied[0] == 'f' ? actual == floats[index]
        : actual == integers[index] || actual == booleans[index];
}
void setUniform(const GlApi& gl, GLuint program, const UniformSpec& value,
                std::vector<std::string>& inactiveBindings) {
    GLint location = gl.GetUniformLocation(program, value.name.c_str());
    if (location < 0) {
        inactiveBindings.push_back(value.name);
        return; // Runner must explicitly allow optimized-out bindings per fixture.
    }
    GLenum type = uniformType(gl, program, value.name);
    if (!compatibleUniformType(value.type, type))
        throw Failure("uniform type", "Manifest type " + value.type + " mismatches active uniform: " + value.name);
    const auto& f = value.floats; const auto& i = value.integers;
    if (value.type == "f1") gl.Uniform1f(location, f[0]);
    else if (value.type == "f2") gl.Uniform2f(location, f[0], f[1]);
    else if (value.type == "f3") gl.Uniform3f(location, f[0], f[1], f[2]);
    else if (value.type == "f4") gl.Uniform4f(location, f[0], f[1], f[2], f[3]);
    else if (value.type == "i1") gl.Uniform1i(location, i[0]);
    else if (value.type == "i2") gl.Uniform2i(location, i[0], i[1]);
    else if (value.type == "i3") gl.Uniform3i(location, i[0], i[1], i[2]);
    else if (value.type == "i4") gl.Uniform4i(location, i[0], i[1], i[2], i[3]);
    else if (value.type == "m4") gl.UniformMatrix4fv(location, 1, GL_FALSE, f.data());
    checkGl("uniform " + value.name);
}

void drawFullscreenTriangle() {
    // Compatibility input matches pack ftransform/gl_MultiTexCoord0 fullscreen vertices.
    glBegin(GL_TRIANGLES);
    glTexCoord2f(0.0f, 0.0f); glVertex2f(-1.0f, -1.0f);
    glTexCoord2f(2.0f, 0.0f); glVertex2f( 3.0f, -1.0f);
    glTexCoord2f(0.0f, 2.0f); glVertex2f(-1.0f,  3.0f);
    glEnd();
}

std::vector<std::string> render(const GlApi& gl, const GlInfo& info, const RenderSpec& spec,
                                std::vector<GLuint64>* elapsedNanoseconds = nullptr) {
    std::vector<std::string> inactiveBindings;
    if (spec.target.width > info.maxTextureSize || spec.target.height > info.maxTextureSize
        || spec.textures.size() > static_cast<std::size_t>(info.maxTextureUnits))
        throw Failure("render limits", "Target or sampler count exceeds driver limits");
    for (const auto& target : spec.colorTargets)
        if (target.slot >= info.maxDrawBuffers || target.attachment >= info.maxColorAttachments)
            throw Failure("render limits", "Color target mapping exceeds driver draw-buffer or attachment limits");
    Program program(gl);
    program.build(spec.vertex, spec.fragment);
    RenderObjects objects(gl);
    gl.ActiveTexture(GL_TEXTURE0);
    gl.GenFramebuffers(1, &objects.framebuffer);
    gl.BindFramebuffer(GL_FRAMEBUFFER, objects.framebuffer);
    std::vector<GLenum> drawBuffers(static_cast<std::size_t>(spec.colorTargets.back().slot + 1), GL_NONE);
    for (const auto& target : spec.colorTargets) {
        objects.targets.push_back(0);
        glGenTextures(1, &objects.targets.back());
        glBindTexture(GL_TEXTURE_2D, objects.targets.back());
        textureParameters();
        glTexImage2D(GL_TEXTURE_2D, 0, storageFormat(target.format), spec.target.width,
                     spec.target.height, 0, GL_RGBA, GL_FLOAT, nullptr);
        GLenum attachment = GL_COLOR_ATTACHMENT0 + static_cast<GLenum>(target.attachment);
        gl.FramebufferTexture2D(GL_FRAMEBUFFER, attachment, GL_TEXTURE_2D, objects.targets.back(), 0);
        drawBuffers[static_cast<std::size_t>(target.slot)] = attachment;
    }
    gl.DrawBuffers(static_cast<GLsizei>(drawBuffers.size()), drawBuffers.data());
    glReadBuffer(GL_COLOR_ATTACHMENT0 + static_cast<GLenum>(selectedTarget(spec).attachment));
    GLenum status = gl.CheckFramebufferStatus(GL_FRAMEBUFFER);
    if (status != GL_FRAMEBUFFER_COMPLETE) {
        std::ostringstream message; message << "Incomplete framebuffer: 0x" << std::hex << status;
        throw Failure("framebuffer", message.str());
    }
    checkGl("framebuffer allocation");
    gl.UseProgram(program.id());
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glBindTexture(GL_TEXTURE_2D, 0); // Never sample the output attachment by accident.
    for (std::size_t index = 0; index < spec.textures.size(); ++index) {
        const auto& input = spec.textures[index];
        if (input.width > info.maxTextureSize || input.height > info.maxTextureSize)
            throw Failure("render limits", "Input texture exceeds driver limits: " + input.name);
        std::vector<float> data = readPixelsFile(input);
        objects.inputs.push_back(0);
        glGenTextures(1, &objects.inputs.back());
        gl.ActiveTexture(GL_TEXTURE0 + static_cast<GLenum>(index));
        glBindTexture(GL_TEXTURE_2D, objects.inputs.back());
        textureParameters();
        glTexImage2D(GL_TEXTURE_2D, 0, storageFormat(input.format), input.width,
                     input.height, 0, GL_RGBA, GL_FLOAT, data.data());
        GLint location = gl.GetUniformLocation(program.id(), input.name.c_str());
        if (location >= 0) {
            if (uniformType(gl, program.id(), input.name) != GL_SAMPLER_2D)
                throw Failure("sampler type", "Texture binding requires an active sampler2D: " + input.name);
            gl.Uniform1i(location, static_cast<GLint>(index));
        } else inactiveBindings.push_back(input.name);
        checkGl("texture upload " + input.name);
    }
    for (const auto& uniform : spec.uniforms) setUniform(gl, program.id(), uniform, inactiveBindings);
    gl.ActiveTexture(GL_TEXTURE0);
    glMatrixMode(GL_TEXTURE); glLoadIdentity();
    glMatrixMode(GL_PROJECTION); glLoadIdentity();
    glMatrixMode(GL_MODELVIEW); glLoadIdentity();
    glDisable(GL_BLEND); glDisable(GL_DEPTH_TEST); glDisable(GL_STENCIL_TEST);
    glDisable(GL_SCISSOR_TEST); glDisable(GL_CULL_FACE); glDisable(GL_DITHER);
    glDisable(GL_MULTISAMPLE); glDisable(GL_FRAMEBUFFER_SRGB); glDisable(GL_ALPHA_TEST);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glViewport(0, 0, spec.target.width, spec.target.height);
    // A missing fragment write must fail even when the expected result is zero.
    // ClearBufferfv avoids the legacy glClearColor state/clamping path.
    const GLfloat sentinel[] = {-11931.25f, -719.5f, -37.25f, -13.0f};
    for (const auto& target : spec.colorTargets) gl.ClearBufferfv(GL_COLOR, target.slot, sentinel);
    checkGl("render setup");
    if (elapsedNanoseconds) {
        // Warmed fixed inputs; measure draws only, outside compilation, uploads and readback.
        auto gen = Context::loadFunction<PFNGLGENQUERIESPROC>("glGenQueries");
        auto release = Context::loadFunction<PFNGLDELETEQUERIESPROC>("glDeleteQueries");
        auto begin = Context::loadFunction<PFNGLBEGINQUERYPROC>("glBeginQuery");
        auto end = Context::loadFunction<PFNGLENDQUERYPROC>("glEndQuery");
        auto result = Context::loadFunction<PFNGLGETQUERYOBJECTUI64VPROC>("glGetQueryObjectui64v");
        auto query = Context::loadFunction<PFNGLGETQUERYIVPROC>("glGetQueryiv");
        GLint bits = 0;
        query(GL_TIME_ELAPSED, GL_QUERY_COUNTER_BITS, &bits);
        if (bits <= 0) throw Failure("timing", "Elapsed timer query unavailable");
        for (int i = 0; i < 6; ++i) drawFullscreenTriangle();
        glFinish();
        // Queue independent draws, then retrieve results to avoid timing host waits.
        std::array<GLuint, 25> ids{};
        gen(static_cast<GLsizei>(ids.size()), ids.data());
        for (GLuint id : ids) {
            begin(GL_TIME_ELAPSED, id);
            drawFullscreenTriangle();
            end(GL_TIME_ELAPSED);
        }
        for (GLuint id : ids) {
            GLuint64 duration = 0;
            result(id, GL_QUERY_RESULT, &duration);
            elapsedNanoseconds->push_back(duration);
        }
        release(static_cast<GLsizei>(ids.size()), ids.data());
    } else {
        drawFullscreenTriangle();
    }
    checkGl("draw");
    std::vector<float> output(pixels(spec.target.width, spec.target.height) * 4);
    // ReadPixels synchronizes these framebuffer writes; no timing claim is made.
    glReadPixels(0, 0, spec.target.width, spec.target.height, GL_RGBA, GL_FLOAT, output.data());
    checkGl("pixel readback");
    writePixelsFile(spec.target.path, output);
    return inactiveBindings;
}

// Narrow protocol proof, intentionally separate from the ordinary render path.
// The fragment supplied by the Python fixture copies these three uniforms.
std::string waterBlendCheck(const GlApi& gl, const GlInfo& info,
                            const std::string& vertex, const std::string& fragment) {
    if (info.maxDrawBuffers < 3 || info.maxColorAttachments < 3)
        throw Failure("water blend limits", "Three simultaneous color attachments required");
    auto enable = Context::loadFunction<PFNGLENABLEIPROC>("glEnablei");
    auto disable = Context::loadFunction<PFNGLDISABLEIPROC>("glDisablei");
    auto blend = Context::loadFunction<PFNGLBLENDFUNCSEPARATEIPROC>("glBlendFuncSeparatei");
    auto equation = Context::loadFunction<PFNGLBLENDEQUATIONIPROC>("glBlendEquationi");
    Program program(gl); program.build(vertex, fragment);
    RenderObjects objects(gl);
    gl.GenFramebuffers(1, &objects.framebuffer);
    gl.BindFramebuffer(GL_FRAMEBUFFER, objects.framebuffer);
    const GLint formats[] = {GL_RGBA32F, GL_RGBA32F, GL_RGBA8};
    const GLenum attachments[] = {GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1, GL_COLOR_ATTACHMENT2};
    for (int slot=0; slot<3; ++slot) {
        objects.targets.push_back(0); glGenTextures(1, &objects.targets.back());
        glBindTexture(GL_TEXTURE_2D, objects.targets.back()); textureParameters();
        glTexImage2D(GL_TEXTURE_2D,0,formats[slot],2,2,0,GL_RGBA,GL_FLOAT,nullptr);
        gl.FramebufferTexture2D(GL_FRAMEBUFFER,attachments[slot],GL_TEXTURE_2D,objects.targets.back(),0);
    }
    gl.DrawBuffers(3,attachments);
    if (gl.CheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE)
        throw Failure("water blend framebuffer","Mixed-format indexed blend framebuffer incomplete");
    gl.UseProgram(program.id());
    glDisable(GL_DEPTH_TEST); glDisable(GL_STENCIL_TEST); glDisable(GL_SCISSOR_TEST);
    glDisable(GL_CULL_FACE); glDisable(GL_DITHER); glDisable(GL_MULTISAMPLE);
    glDisable(GL_FRAMEBUFFER_SRGB); glDisable(GL_ALPHA_TEST);
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE); glViewport(0,0,2,2);
    glMatrixMode(GL_PROJECTION); glLoadIdentity();
    glMatrixMode(GL_MODELVIEW); glLoadIdentity();
    glMatrixMode(GL_TEXTURE); glLoadIdentity();
    for (int slot=0; slot<3; ++slot) equation(slot,GL_FUNC_ADD);
    disable(GL_BLEND,1);
    blend(0,GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA,GL_ONE,GL_ONE_MINUS_SRC_ALPHA);
    blend(2,GL_ONE,GL_ONE,GL_ONE,GL_ONE);
    const GLfloat base[] = {.2f,.4f,.6f,.8f}, zero[] = {0,0,0,0};
    const std::array<float,4> water = {.8f,.2f,.4f,.25f};
    const std::array<float,4> overlay = {.1f,.9f,.3f,.5f};
    const std::array<float,4> record = {.3f,.4f,.866f,.25f};
    const std::array<float,4> count = {1.f/255.f,.2f,.6f,0};
    const std::vector<std::pair<std::string,std::vector<int>>> patterns = {
        {"one_water",{0}}, {"two_water",{0,0}}, {"water_then_overlay",{0,1}},
        {"overlay_then_water",{1,0}}, {"opaque_replaces_blocker",{1,2,0}},
        {"saturation_260_water",std::vector<int>(260,0)}};
    double maximum = 0; std::ostringstream rows; rows << '[';
    for (std::size_t index=0; index<patterns.size(); ++index) {
        gl.ClearBufferfv(GL_COLOR,0,base); gl.ClearBufferfv(GL_COLOR,1,zero); gl.ClearBufferfv(GL_COLOR,2,zero);
        std::array<double,4> expectedColor={base[0],base[1],base[2],base[3]}, expectedRecord{}, expectedCount{};
        for (int kind:patterns[index].second) {
            bool opaque=kind==2;
            const auto& source=kind==0?water:overlay;
            std::array<float,4> sourceRecord=kind==0?record:std::array<float,4>{0,0,0,0};
            std::array<float,4> sourceCount=kind==0?count:std::array<float,4>{opaque?0.f:1.f,0,0,0};
            if (opaque) { disable(GL_BLEND,0); disable(GL_BLEND,2); }
            else { enable(GL_BLEND,0); enable(GL_BLEND,2); }
            for (const auto& binding:std::vector<std::pair<const char*,std::array<float,4>>>{
                    {"nativeColor",source},{"recordValue",sourceRecord},{"countValue",sourceCount}}) {
                GLint location=gl.GetUniformLocation(program.id(),binding.first);
                if (location<0) throw Failure("water blend uniform",std::string("Missing ")+binding.first);
                gl.Uniform4f(location,binding.second[0],binding.second[1],binding.second[2],binding.second[3]);
            }
            glBegin(GL_TRIANGLES);
            glVertex2f(-1,-1); glVertex2f(3,-1); glVertex2f(-1,3); glEnd();
            checkGl("water indexed blend draw");
            for (int channel=0;channel<4;++channel) {
                expectedColor[channel]=opaque?source[channel]:
                    (channel==3?source[channel]:source[channel]*source[3])+expectedColor[channel]*(1-source[3]);
                expectedRecord[channel]=sourceRecord[channel];
                // RGBA8 destination quantization occurs after every draw.
                double value=sourceCount[channel]+(opaque?0:expectedCount[channel]);
                expectedCount[channel]=std::round(std::clamp(value,0.0,1.0)*255)/255;
            }
        }
        std::array<double,4> countRead{};
        for (int slot=0;slot<3;++slot) {
            glReadBuffer(attachments[slot]); GLfloat pixels[16]{};
            glReadPixels(0,0,2,2,GL_RGBA,GL_FLOAT,pixels); checkGl("water indexed blend read");
            const auto& expected=slot==0?expectedColor:slot==1?expectedRecord:expectedCount;
            for (int pixel=0;pixel<4;++pixel) for (int channel=0;channel<4;++channel) {
                double error=std::abs(pixels[pixel*4+channel]-expected[channel]);
                maximum=std::max(maximum,error);
                if (!std::isfinite(pixels[pixel*4+channel]) || error>2e-6)
                    throw Failure("water blend comparison",patterns[index].first+" attachment "+std::to_string(slot));
                if (slot==2 && pixel==0) countRead[channel]=pixels[channel];
            }
        }
        if(index) rows << ',';
        rows << "{\"label\":" << jsonQuote(patterns[index].first)
             << ",\"draws\":" << patterns[index].second.size()
             << ",\"count_r\":" << std::setprecision(10) << countRead[0] << '}';
    }
    rows << ']';
    std::ostringstream result;
    result << "{\"cases\":" << patterns.size() << ",\"pixels_per_case\":4,\"attachments\":3"
           << ",\"max_absolute_error\":" << std::setprecision(12) << maximum
           << ",\"cases_detail\":" << rows.str()
           << ",\"scope\":\"Native indexed blend protocol, synthetic constant-output fragment; not Iris property wiring\"}";
    return result.str();
}

std::string depthStorageCheck(const GlApi& gl, const std::string& vertex, const std::string& fragment) {
    Program program(gl); program.build(vertex,fragment);
    RenderObjects objects(gl);
    gl.ActiveTexture(GL_TEXTURE0);
    gl.GenFramebuffers(1,&objects.framebuffer);
    gl.BindFramebuffer(GL_FRAMEBUFFER,objects.framebuffer);
    objects.targets.push_back(0);glGenTextures(1,&objects.targets.back());
    glBindTexture(GL_TEXTURE_2D,objects.targets.back());textureParameters();
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA32F,1,1,0,GL_RGBA,GL_FLOAT,nullptr);
    gl.FramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,objects.targets.back(),0);
    objects.inputs.push_back(0);glGenTextures(1,&objects.inputs.back());
    const GLenum output=GL_COLOR_ATTACHMENT0;gl.DrawBuffers(1,&output);glReadBuffer(output);
    gl.UseProgram(program.id());
    GLint location=gl.GetUniformLocation(program.id(),"testDepth");
    if(location<0) throw Failure("depth storage comparison","Missing active testDepth uniform");
    glEnable(GL_DEPTH_TEST);glDepthFunc(GL_ALWAYS);glDepthMask(GL_TRUE);
    glDisable(GL_BLEND);glDisable(GL_STENCIL_TEST);glDisable(GL_SCISSOR_TEST);
    glDisable(GL_CULL_FACE);glDisable(GL_DITHER);glDisable(GL_MULTISAMPLE);
    glDisable(GL_FRAMEBUFFER_SRGB);glDisable(GL_ALPHA_TEST);
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glViewport(0,0,1,1);
    glMatrixMode(GL_PROJECTION);glLoadIdentity();glMatrixMode(GL_MODELVIEW);glLoadIdentity();
    const float values[]={0.f,std::ldexp(1.f,-24),.12345679f,.25f,
        std::nextafter(.5f,0.f),.5f,std::nextafter(.5f,1.f),.75f,std::nextafter(1.f,0.f),
        .000001f,12345.5f/65534.f,54321.5f/65534.f};
    const GLenum formats[]={GL_DEPTH_COMPONENT24,GL_DEPTH_COMPONENT32F};
    std::ostringstream rows;rows << '[';
    for(int format=0;format<2;++format) {
        glBindTexture(GL_TEXTURE_2D,objects.inputs.back());textureParameters();
        glTexImage2D(GL_TEXTURE_2D,0,formats[format],1,1,0,GL_DEPTH_COMPONENT,GL_FLOAT,nullptr);
        gl.FramebufferTexture2D(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_TEXTURE_2D,objects.inputs.back(),0);
        if(gl.CheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE)
            throw Failure("depth storage comparison","Depth framebuffer incomplete");
        glBindTexture(GL_TEXTURE_2D,0);
        for(std::size_t index=0;index<sizeof(values)/sizeof(values[0]);++index) {
            gl.Uniform1f(location,values[index]);glClearDepth(1.0);glClear(GL_DEPTH_BUFFER_BIT);
            glBegin(GL_TRIANGLES);glVertex2f(-1.f,-1.f);glVertex2f(3.f,-1.f);glVertex2f(-1.f,3.f);glEnd();
            float color[4]={0.f,0.f,0.f,0.f},stored=0.f;
            glReadPixels(0,0,1,1,GL_RGBA,GL_FLOAT,color);
            glReadPixels(0,0,1,1,GL_DEPTH_COMPONENT,GL_FLOAT,&stored);
            checkGl("native depth storage readback");
            float tolerance=format==0?1.f/16777215.f:0.f;
            if(color[0]!=values[index] || !std::isfinite(stored) || std::abs(stored-values[index])>tolerance)
                throw Failure("depth storage comparison","Unexpected depth/color conversion");
            if(format || index) rows << ',';
            rows << "{\"format\":" << jsonQuote(format==0?"D24":"D32F")
                 << ",\"source\":" << std::setprecision(12) << values[index]
                 << ",\"stored\":" << stored << '}';
        }
    }
    rows << ']';return rows.str();
}
} // namespace

int main(int argc, char** argv) {
    static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559,
                  "The raw pixel protocol requires IEEE754 float32");
    GlInfo info;
    std::string command = argc > 1 ? argv[1] : "", activeCase;
    std::size_t completed = 0;
    try {
        std::vector<CompileCase> cases;
        RenderSpec spec;
        std::vector<std::string> inactiveBindings;
        if ((command == "--water-blend-check" || command == "--depth-storage-check") && argc == 4) {
            absolutePath(argv[2]); absolutePath(argv[3]);
        } else if (command == "--probe" && argc == 2) {
        } else if (command == "--compile" && argc == 4) {
            cases.push_back({"single", argv[2], argv[3]});
            absolutePath(argv[2]); absolutePath(argv[3]);
        } else if (command == "--compile-batch" && argc == 3) {
            cases = readBatch(argv[2]);
        } else if ((command == "--render" || command == "--time-render") && argc == 3) {
            spec = readRender(argv[2]);
        } else throw Failure("arguments", "Usage: --probe | --compile VERTEX FRAGMENT | --compile-batch MANIFEST | --render MANIFEST | --time-render MANIFEST | --water-blend-check VERTEX FRAGMENT | --depth-storage-check VERTEX FRAGMENT");
        Context context;
        context.initialize(info);
        GlApi gl;
        gl.initialize();
        for (const auto& entry : cases) {
            activeCase = entry.label;
            Program program(gl);
            program.build(entry.vertex, entry.fragment);
            ++completed;
        }
        activeCase.clear();
        std::string waterBlendResult;
        std::string depthResult;
        if (command == "--depth-storage-check") depthResult = depthStorageCheck(gl,argv[2],argv[3]);
        if (command == "--water-blend-check") waterBlendResult = waterBlendCheck(gl,info,argv[2],argv[3]);
        std::vector<GLuint64> elapsedNanoseconds;
        if (command == "--time-render") inactiveBindings = render(gl, info, spec, &elapsedNanoseconds);
        if (command == "--render") inactiveBindings = render(gl, info, spec);
        std::cout << "{\"ok\":true,\"command\":" << jsonQuote(command)
                  << ",\"gl\":" << info.json();
        if (!elapsedNanoseconds.empty()) {
            std::cout << ",\"gpu_nanoseconds\":[";
            for (std::size_t index = 0; index < elapsedNanoseconds.size(); ++index) {
                if (index) std::cout << ',';
                std::cout << elapsedNanoseconds[index];
            }
            std::cout << ']';
        }
        if (!depthResult.empty()) std::cout << ",\"depth_storage\":" << depthResult;
        if (!waterBlendResult.empty()) std::cout << ",\"water_blend\":" << waterBlendResult;
        if (!cases.empty()) std::cout << ",\"compiled\":" << completed << ",\"case_count\":" << cases.size();
        if (command == "--render" || command == "--time-render") {
            std::cout << ",\"width\":" << spec.target.width << ",\"height\":" << spec.target.height
                      << ",\"format\":" << jsonQuote(spec.target.format)
                      << ",\"output\":" << jsonQuote(spec.target.path)
                      << ",\"row_order\":\"bottom_to_top\",\"pixel_type\":\"RGBA_float32_little_endian\""
                      << ",\"read_target\":" << spec.readTarget
                      << ",\"read_format\":" << jsonQuote(selectedTarget(spec).format);
            std::cout << ",\"color_targets\":[";
            for (std::size_t index = 0; index < spec.colorTargets.size(); ++index) {
                if (index) std::cout << ',';
                const auto& target = spec.colorTargets[index];
                std::cout << "{\"slot\":" << target.slot << ",\"attachment\":" << target.attachment
                          << ",\"format\":" << jsonQuote(target.format) << '}';
            }
            std::cout << ']';
            std::cout << ",\"inactive_bindings\":[";
            for (std::size_t index = 0; index < inactiveBindings.size(); ++index) {
                if (index) std::cout << ',';
                std::cout << jsonQuote(inactiveBindings[index]);
            }
            std::cout << ']';
        }
        std::cout << "}" << std::endl;
        return 0;
    } catch (const Failure& error) {
        std::cout << "{\"ok\":false,\"command\":" << jsonQuote(command)
                  << ",\"gl\":" << info.json() << ",\"stage\":" << jsonQuote(error.stage)
                  << ",\"error\":" << jsonQuote(error.what()) << ",\"compiled\":" << completed;
        if (!activeCase.empty()) std::cout << ",\"case\":" << jsonQuote(activeCase);
        if (error.windowsCode) std::cout << ",\"win32_error\":" << error.windowsCode;
        if (error.glCode) std::cout << ",\"gl_error\":" << error.glCode;
        std::cout << "}" << std::endl;
        return 1;
    } catch (const std::exception& error) {
        std::cout << "{\"ok\":false,\"command\":" << jsonQuote(command)
                  << ",\"gl\":" << info.json() << ",\"stage\":\"host\",\"error\":"
                  << jsonQuote(error.what()) << ",\"compiled\":" << completed;
        if (!activeCase.empty()) std::cout << ",\"case\":" << jsonQuote(activeCase);
        std::cout << "}" << std::endl;
        return 1;
    }
}
