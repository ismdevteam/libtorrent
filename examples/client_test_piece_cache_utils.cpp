#include "client_test_piece_cache_utils.hpp"
#include <fstream>
#include <cstring>
#include <sys/stat.h>
#include <dirent.h>
#include <regex>
#include <utility>
#include <map>

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

void assign_setting(lt::settings_pack& settings, std::string const& key, char const* value) {
    int const sett_name = lt::setting_by_name(key);
    if (sett_name < 0) {
        std::fprintf(stderr, "unknown setting: \"%s\"\n", key.c_str());
        std::exit(1);
    }

    using lt::settings_pack;

    switch (sett_name & settings_pack::type_mask) {
        case settings_pack::string_type_base:
            settings.set_str(sett_name, value);
            break;
        case settings_pack::bool_type_base:
            if (value == "1"_sv || value == "on"_sv || value == "true"_sv) {
                settings.set_bool(sett_name, true);
            }
            else if (value == "0"_sv || value == "off"_sv || value == "false"_sv) {
                settings.set_bool(sett_name, false);
            }
            else {
                std::fprintf(stderr, "invalid value for \"%s\". expected 0 or 1\n", key.c_str());
                std::exit(1);
            }
            break;
        case settings_pack::int_type_base:
            using namespace lt::literals;
            static std::map<lt::string_view, int> const enums = {
                {"no_piece_suggestions"_sv, settings_pack::no_piece_suggestions},
                {"suggest_read_cache"_sv, settings_pack::suggest_read_cache},
                {"fixed_slots_choker"_sv, settings_pack::fixed_slots_choker},
                {"rate_based_choker"_sv, settings_pack::rate_based_choker},
                {"round_robin"_sv, settings_pack::round_robin},
                {"fastest_upload"_sv, settings_pack::fastest_upload},
                {"anti_leech"_sv, settings_pack::anti_leech},
                {"enable_os_cache"_sv, settings_pack::enable_os_cache},
                {"disable_os_cache"_sv, settings_pack::disable_os_cache},
                {"write_through"_sv, settings_pack::write_through},
                {"prefer_tcp"_sv, settings_pack::prefer_tcp},
                {"peer_proportional"_sv, settings_pack::peer_proportional},
                {"pe_forced"_sv, settings_pack::pe_forced},
                {"pe_enabled"_sv, settings_pack::pe_enabled},
                {"pe_disabled"_sv, settings_pack::pe_disabled},
                {"pe_plaintext"_sv, settings_pack::pe_plaintext},
                {"pe_rc4"_sv, settings_pack::pe_rc4},
                {"pe_both"_sv, settings_pack::pe_both},
                {"none"_sv, settings_pack::none},
                {"socks4"_sv, settings_pack::socks4},
                {"socks5"_sv, settings_pack::socks5},
                {"socks5_pw"_sv, settings_pack::socks5_pw},
                {"http"_sv, settings_pack::http},
                {"http_pw"_sv, settings_pack::http_pw},
            };

            {
                auto const it = enums.find(lt::string_view(value));
                if (it != enums.end()) {
                    settings.set_int(sett_name, it->second);
                    break;
                }
            }

            static std::map<lt::string_view, lt::alert_category_t> const alert_categories = {
                {"error"_sv, lt::alert_category::error},
                {"peer"_sv, lt::alert_category::peer},
                {"port_mapping"_sv, lt::alert_category::port_mapping},
                {"storage"_sv, lt::alert_category::storage},
                {"tracker"_sv, lt::alert_category::tracker},
                {"connect"_sv, lt::alert_category::connect},
                {"status"_sv, lt::alert_category::status},
                {"ip_block"_sv, lt::alert_category::ip_block},
                {"performance_warning"_sv, lt::alert_category::performance_warning},
                {"dht"_sv, lt::alert_category::dht},
                {"session_log"_sv, lt::alert_category::session_log},
                {"torrent_log"_sv, lt::alert_category::torrent_log},
                {"peer_log"_sv, lt::alert_category::peer_log},
                {"incoming_request"_sv, lt::alert_category::incoming_request},
                {"dht_log"_sv, lt::alert_category::dht_log},
                {"dht_operation"_sv, lt::alert_category::dht_operation},
                {"port_mapping_log"_sv, lt::alert_category::port_mapping_log},
                {"picker_log"_sv, lt::alert_category::picker_log},
                {"file_progress"_sv, lt::alert_category::file_progress},
                {"piece_progress"_sv, lt::alert_category::piece_progress},
                {"upload"_sv, lt::alert_category::upload},
                {"block_progress"_sv, lt::alert_category::block_progress},
                {"all"_sv, lt::alert_category::all},
            };

            std::stringstream flags(value);
            std::string f;
            lt::alert_category_t val;
            while (std::getline(flags, f, ',')) try {
                auto const it = alert_categories.find(f);
                if (it == alert_categories.end())
                    val |= lt::alert_category_t{unsigned(std::stoi(f))};
                else
                    val |= it->second;
            }
            catch (std::invalid_argument const&) {
                std::fprintf(stderr, "invalid value for \"%s\". expected integer or enum value\n", key.c_str());
                std::exit(1);
            }

            settings.set_int(sett_name, val);
            break;
    }
}

std::string resume_file(lt::info_hash_t const& info_hash) {
    std::string const resume_dir = path_append(save_path, ".resume");
    return path_append(resume_dir, to_hex(info_hash.get_best()) + ".resume");
}

void print_usage() {
    std::fprintf(stderr, R"(usage: client_test [OPTIONS] [TORRENT|MAGNETURL]
OPTIONS:

CLIENT OPTIONS
  -h                    print this message
  -f <log file>         logs all events to the given file
  -s <path>             sets the save path for downloads. This also determines
                        the resume data save directory. Torrents from the resume
                        directory are automatically added to the session on
                        startup.
  -m <path>             sets the .torrent monitor directory. torrent files
                        dropped in the directory are added the session and the
                        resume data directory, and removed from the monitor dir.
  -t <seconds>          sets the scan interval of the monitor dir
  -F <milliseconds>     sets the UI refresh rate. This is the number of
                        milliseconds between screen refreshes.
  -k                    enable high performance settings. This overwrites any other
                        previous command line options, so be sure to specify this first
  -G                    Add torrents in seed-mode (i.e. assume all pieces
                        are present and check hashes on-demand)
  -e <loops>            exit client after the specified number of iterations
                        through the main loop
  -O                    print session stats counters to the log
  -1                    exit on first torrent completing (useful for benchmarks)
  -C                    cache pieces during download (not just after completion)
  -Z                    disable original content storage (use only piece cache)
  -S                    seed from piece cache only (no original files created)

LIBTORRENT SETTINGS
  --<name-of-setting>=<value>
                        set the libtorrent setting <name> to <value>
  --list-settings       print all libtorrent settings and exit

BITTORRENT OPTIONS
  -T <limit>            sets the max number of connections per torrent
  -U <rate>             sets per-torrent upload rate
  -D <rate>             sets per-torrent download rate
  -Q                    enables share mode. Share mode attempts to maximize
                        share ratio rather than downloading
  -r <IP:port>          connect to specified peer

NETWORK OPTIONS
  -x <file>             loads an emule IP-filter file
  -Y                    Rate limit local peers
  -i <i2p-host>         the hostname to an I2P SAM bridge to use

DISK OPTIONS
  -a <mode>             sets the allocation mode. [sparse|allocate]
  -0                    disable disk I/O, read garbage and don't flush to disk

TORRENT is a path to a .torrent file
MAGNETURL is a magnet link

alert mask flags:
	error peer port_mapping storage tracker connect status ip_block
	performance_warning dht session_log torrent_log peer_log incoming_request
	dht_log dht_operation port_mapping_log picker_log file_progress piece_progress
	upload block_progress all

examples:
  --alert_mask=error,port_mapping,tracker,connect,session_log
  --alert_mask=error,session_log,torrent_log,peer_log
  --alert_mask=error,dht,dht_log,dht_operation
  --alert_mask=all
)");
}
