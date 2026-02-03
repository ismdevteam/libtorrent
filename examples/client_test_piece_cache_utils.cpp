#include "client_test_piece_cache_utils.hpp"
#include "client_test_piece_cache_globals.hpp"
#include <fstream>
#include <cstring>
#include <sys/stat.h>
#include <dirent.h>

bool load_file(std::string const& filename, std::vector<char>& v, int limit) {
    std::fstream f(filename, std::ios_base::in | std::ios_base::binary);
    f.seekg(0, std::ios_base::end);
    auto const s = f.tellg();
    if (s > limit || s < 0) return false;
    f.seekg(0, std::ios_base::beg);
    v.resize(static_cast<std::size_t>(s));
    if (s == std::fstream::pos_type(0)) return !f.fail();
    f.read(v.data(), int(v.size()));
    return !f.fail();
}

bool is_absolute_path(std::string const& f) {
    if (f.empty()) return false;
#if defined(TORRENT_WINDOWS) || defined(TORRENT_OS2)
    int i = 0;
    while (f[i] && strchr("abcdefghijklmnopqrstuvxyzABCDEFGHIJKLMNOPQRSTUVXYZ", f[i])) ++i;
    if (i < int(f.size()-1) && f[i] == ':' && (f[i+1] == '\\' || f[i+1] == '/'))
        return true;
    if (int(f.size()) >= 2 && f[0] == '\\' && f[1] == '\\')
        return true;
    return false;
#else
    if (f[0] == '/') return true;
    return false;
#endif
}

std::string path_append(std::string const& lhs, std::string const& rhs) {
    if (lhs.empty() || lhs == ".") return rhs;
    if (rhs.empty() || rhs == ".") return lhs;

#if defined(TORRENT_WINDOWS) || defined(TORRENT_OS2)
#define TORRENT_SEPARATOR "\\"
    bool need_sep = lhs[lhs.size()-1] != '\\' && lhs[lhs.size()-1] != '/';
#else
#define TORRENT_SEPARATOR "/"
    bool need_sep = lhs[lhs.size()-1] != '/';
#endif
    return lhs + (need_sep?TORRENT_SEPARATOR:"") + rhs;
}

std::string make_absolute_path(std::string const& p) {
    if (is_absolute_path(p)) return p;
    std::string ret;
#if defined TORRENT_WINDOWS
    char* cwd = ::_getcwd(nullptr, 0);
    ret = path_append(cwd, p);
    std::free(cwd);
#else
    char* cwd = ::getcwd(nullptr, 0);
    ret = path_append(cwd, p);
    std::free(cwd);
#endif
    return ret;
}

std::string print_endpoint(lt::tcp::endpoint const& ep) {
    using namespace lt;
    char buf[200];
    address const& addr = ep.address();
    if (addr.is_v6())
        std::snprintf(buf, sizeof(buf), "[%s]:%d", addr.to_string().c_str(), ep.port());
    else
        std::snprintf(buf, sizeof(buf), "%s:%d", addr.to_string().c_str(), ep.port());
    return buf;
}

std::string to_hex(lt::sha1_hash const& s) {
    std::stringstream ret;
    ret << s;
    return ret.str();
}

std::vector<std::string> list_dir(std::string path, bool (*filter_fun)(lt::string_view), lt::error_code& ec) {
    std::vector<std::string> ret;
#ifdef TORRENT_WINDOWS
    if (!path.empty() && path[path.size()-1] != '\\') path += "\\*";
    else path += "*";

    WIN32_FIND_DATAA fd;
    HANDLE handle = FindFirstFileA(path.c_str(), &fd);
    if (handle == INVALID_HANDLE_VALUE) {
        ec.assign(GetLastError(), boost::system::system_category());
        return ret;
    }

    do {
        lt::string_view p = fd.cFileName;
        if (filter_fun(p))
            ret.push_back(p.to_string());
    } while (FindNextFileA(handle, &fd));
    FindClose(handle);
#else
    if (!path.empty() && path[path.size()-1] == '/')
        path.resize(path.size()-1);

    DIR* handle = opendir(path.c_str());
    if (handle == nullptr) {
        ec.assign(errno, boost::system::system_category());
        return ret;
    }

    struct dirent* de;
    while ((de = readdir(handle))) {
        lt::string_view p(de->d_name);
        if (filter_fun(p))
            ret.push_back(p.to_string());
    }
    closedir(handle);
#endif
    return ret;
}

bool is_resume_file(std::string const& s) {
    static std::string const hex_digit = "0123456789abcdef";
    if (s.size() != 40 + 7) return false;
    if (s.substr(40) != ".resume") return false;
    for (char const c : s.substr(0, 40)) {
        if (hex_digit.find(c) == std::string::npos) return false;
    }
    return true;
}

char const* timestamp() {
    time_t t = std::time(nullptr);
#ifdef TORRENT_WINDOWS
    std::tm const* timeinfo = localtime(&t);
#else
    std::tm buf;
    std::tm const* timeinfo = localtime_r(&t, &buf);
#endif
    static char str[200];
    std::strftime(str, 200, "%b %d %X", timeinfo);
    return str;
}
