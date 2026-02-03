#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <utility>
#include <deque>
#include <fstream>
#include <regex>
#include <algorithm>
#include <numeric>

#include "libtorrent/config.hpp"

#ifdef TORRENT_WINDOWS
#include <direct.h>
#include <sys/types.h>
#include <sys/stat.h>
#endif

#include "libtorrent/torrent_info.hpp"
#include "libtorrent/announce_entry.hpp"
#include "libtorrent/entry.hpp"
#include "libtorrent/bencode.hpp"
#include "libtorrent/session.hpp"
#include "libtorrent/session_params.hpp"
#include "libtorrent/identify_client.hpp"
#include "libtorrent/alert_types.hpp"
#include "libtorrent/ip_filter.hpp"
#include "libtorrent/magnet_uri.hpp"
#include "libtorrent/peer_info.hpp"
#include "libtorrent/bdecode.hpp"
#include "libtorrent/add_torrent_params.hpp"
#include "libtorrent/time.hpp"
#include "libtorrent/read_resume_data.hpp"
#include "libtorrent/write_resume_data.hpp"
#include "libtorrent/string_view.hpp"
#include "libtorrent/disk_interface.hpp"
#include "libtorrent/disabled_disk_io.hpp"
#include "libtorrent/load_torrent.hpp"

#include "torrent_view.hpp"
#include "session_view.hpp"
#include "print.hpp"

#include "piece_cache_manager.hpp"

#include "client_test_piece_cache_utils.hpp"
#include "client_test_piece_cache_alerts.hpp"
#include "client_test_piece_cache_session.hpp"
#include "client_test_piece_cache_torrent.hpp"
#include "client_test_piece_cache_views.hpp"
#include "client_test_piece_cache_globals.hpp"

#ifdef _WIN32
#include <windows.h>
#include <conio.h>
#else
#include <termios.h>
#include <sys/ioctl.h>
#include <csignal>
#include <utility>
#include <iostream>
#include <dirent.h>
#endif

// Global variables and constants
bool print_trackers = false;
bool print_peers = false;
bool print_peers_legend = false;
bool print_connecting_peers = false;
bool print_log = false;
bool print_downloads = false;
bool print_matrix = false;
bool print_file_progress = false;
bool print_piece_availability = false;
bool show_pad_files = false;
bool show_dht_status = false;
bool print_ip = true;
bool print_peaks = false;
bool print_local_ip = false;
bool print_timers = false;
bool print_block = false;
bool print_fails = false;
bool print_send_bufs = true;
bool print_disk_stats = false;

bool enable_piece_cache = true;
bool cache_during_download = false;
std::string cache_root = "./piece_cache";
std::unique_ptr<PieceCacheManager> cache_manager;
std::set<lt::info_hash_t> g_initialized_torrents;

bool disable_original_storage = false;
bool seed_from_cache = false;

int num_outstanding_resume_data = 0;

#ifndef TORRENT_DISABLE_DHT
std::vector<lt::dht_lookup> dht_active_requests;
std::vector<lt::dht_routing_bucket> dht_routing_table;
#endif

FILE* g_log_file = nullptr;

lt::storage_mode_t allocation_mode = lt::storage_mode_sparse;
std::string save_path(".");
int torrent_upload_limit = 0;
int torrent_download_limit = 0;
std::string monitor_dir;
int poll_interval = 5;
int max_connections_per_torrent = 50;
bool seed_mode = false;
bool stats_enabled = false;
bool exit_on_finish = false;
bool share_mode = false;
bool quit = false;

#ifndef _WIN32
void signal_handler(int) {
    quit = true;
}
#endif

std::string peer;

int main(int argc, char* argv[]) {
#ifndef _WIN32
    set_keypress s_;
#endif

    if (argc == 1) {
        print_usage();
        return 0;
    }

    using lt::settings_pack;
    using lt::session_handle;

    torrent_view view;
    session_view ses_view;

    if (enable_piece_cache || disable_original_storage) {
        try {
            cache_manager = std::make_unique<PieceCacheManager>(cache_root);
            if (disable_original_storage) {
                std::cout << "Original content storage disabled, using piece cache only" << std::endl;
            }
            std::cout << "Piece cache initialized at: " << cache_root << std::endl;
        }
        catch (const std::exception& e) {
            std::cerr << "Failed to initialize piece cache: " << e.what() << std::endl;
            enable_piece_cache = false;
        }
    }

    lt::session_params params;

    if (disable_original_storage) {
        params.disk_io_constructor = lt::disabled_disk_io_constructor;
    }

#ifndef TORRENT_DISABLE_DHT
    std::vector<char> in;
    if (load_file(".ses_state", in))
        params = read_session_params(in, session_handle::save_dht_state);
#endif

    auto& settings = params.settings;

    settings.set_str(settings_pack::user_agent, "client_test/" LIBTORRENT_VERSION);
    settings.set_int(settings_pack::alert_mask,
        lt::alert_category::error
        | lt::alert_category::peer
        | lt::alert_category::port_mapping
        | lt::alert_category::storage
        | lt::alert_category::tracker
        | lt::alert_category::connect
        | lt::alert_category::status
        | lt::alert_category::ip_block
        | lt::alert_category::performance_warning
        | lt::alert_category::dht
        | lt::alert_category::incoming_request
        | lt::alert_category::dht_operation
        | lt::alert_category::port_mapping_log
        | lt::alert_category::file_progress
        | lt::alert_category::piece_progress);

    lt::time_duration refresh_delay = lt::milliseconds(500);
    bool rate_limit_locals = false;

    client_state_t client_state{view, ses_view, {}, {}, {}, {}, {}, {}, {}};
    int loop_limit = -1;

    lt::time_point next_dir_scan = lt::clock_type::now();

    std::vector<lt::string_view> torrents;
    lt::ip_filter loaded_ip_filter;

    for (int i = 1; i < argc; ++i) {
        if (argv[i][0] != '-') {
            torrents.push_back(argv[i]);
            continue;
        }

        if (argv[i] == "--list-settings"_sv) {
            print_settings(settings_pack::string_type_base, settings_pack::num_string_settings, "string");
            print_settings(settings_pack::bool_type_base, settings_pack::num_bool_settings, "bool");
            print_settings(settings_pack::int_type_base, settings_pack::num_int_settings, "int");
            return 0;
        }

        if (argv[i][1] == '-' && strchr(argv[i], '=') != nullptr) {
            char const* equal = strchr(argv[i], '=');
            char const* start = argv[i]+2;
            std::string const key(start, std::size_t(equal - start));
            char const* value = equal + 1;
            assign_setting(settings, key, value);
            continue;
        }

        switch (argv[i][1]) {
            case 'k': settings = lt::high_performance_seed(); continue;
            case 'G': seed_mode = true; continue;
            case 'O': stats_enabled = true; continue;
            case '1': exit_on_finish = true; continue;
            case 'C': cache_during_download = true; continue;
            case 'Z': disable_original_storage = true; continue;
            case 'S': seed_from_cache = true; disable_original_storage = true; continue;
#ifdef TORRENT_UTP_LOG_ENABLE
            case 'q': lt::set_utp_stream_logging(true); continue;
#endif
            case 'Q': share_mode = true; continue;
            case 'Y': rate_limit_locals = true; continue;
            case '0': params.disk_io_constructor = lt::disabled_disk_io_constructor; continue;
            case 'h': print_usage(); return 0;
        }

        if (argc == i + 1) {
            std::fprintf(stderr, "invalid command line argument or missing parameter: %s\\n", argv[i]);
            return 1;
        }
        char const* arg = argv[i+1];
        if (arg == nullptr) arg = "";

        switch (argv[i][1]) {
            case 'f': g_log_file = std::fopen(arg, "w+"); break;
            case 's': save_path = make_absolute_path(arg); break;
            case 'U': torrent_upload_limit = atoi(arg) * 1000; break;
            case 'D': torrent_download_limit = atoi(arg) * 1000; break;
            case 'm': monitor_dir = make_absolute_path(arg); break;
            case 't': poll_interval = atoi(arg); break;
            case 'F': refresh_delay = lt::milliseconds(atoi(arg)); break;
            case 'a': allocation_mode = (arg == std::string("sparse")) ? lt::storage_mode_sparse : lt::storage_mode_allocate; break;
            case 'x': {
                std::fstream filter(arg, std::ios_base::in);
                if (!filter.fail()) {
                    std::regex regex(R"(^\\s*([0-9.]+)\\s*-\\s*([0-9.]+)\\s+([0-9]+)$)");
                    std::string line;
                    while (std::getline(filter, line)) {
                        std::smatch m;
                        if (std::regex_match(line, m, regex)) {
                            address_v4 start = make_address_v4(m[1]);
                            address_v4 last = make_address_v4(m[2]);
                            loaded_ip_filter.add_rule(start, last, stoi(m[3]) <= 127 ? lt::ip_filter::blocked : 0);
                        }
                    }
                }
                break;
            }
            case 'T': max_connections_per_torrent = atoi(arg); break;
            case 'r': peer = arg; break;
            case 'e': loop_limit = atoi(arg); break;
        }
        ++i;
    }

    int mkdir_ret = mkdir(path_append(save_path, ".resume").c_str(), 0777);
    if (mkdir_ret < 0 && errno != EEXIST) {
        std::fprintf(stderr, "failed to create resume file directory: (%d) %s\\n", errno, strerror(errno));
    }

    lt::session ses(std::move(params));

    if (rate_limit_locals) {
        lt::ip_filter pcf;
        pcf.add_rule(make_address_v4("0.0.0.0"), make_address_v4("255.255.255.255"), 1 << static_cast<std::uint32_t>(lt::session::global_peer_class_id));
        pcf.add_rule(make_address_v6("::"), make_address_v6("ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"), 1);
        ses.set_peer_class_filter(pcf);
    }

    ses.set_ip_filter(loaded_ip_filter);

    for (auto const& i : torrents) {
        if (i.substr(0, 7) == "magnet:") add_magnet(ses, i);
        else add_torrent(ses, i.to_string());
    }

    std::thread resume_data_loader([&ses] {
        lt::error_code ec;
        std::string const resume_dir = disable_original_storage ? path_append(cache_root, ".resume") : path_append(save_path, ".resume");
        std::vector<std::string> ents = list_dir(resume_dir, [](lt::string_view p) { return p.size() > 7 && p.substr(p.size() - 7) == ".resume"; }, ec);
        if (ec) {
            std::fprintf(stderr, "failed to list resume directory \"%s\": (%s : %d) %s\\n", resume_dir.c_str(), ec.category().name(), ec.value(), ec.message().c_str());
        }
        else {
            for (auto const& e : ents) {
                if (!is_resume_file(e)) continue;
                std::string const file = path_append(resume_dir, e);

                std::vector<char> resume_data;
                if (!load_file(file, resume_data)) {
                    std::printf("  failed to load resume file \"%s\": %s\\n", file.c_str(), ec.message().c_str());
                    continue;
                }
                add_torrent_params p = lt::read_resume_data(resume_data, ec);
                if (ec) {
                    std::printf("  failed to parse resume data \"%s\": %s\\n", file.c_str(), ec.message().c_str());
                    continue;
                }

                ses.async_add_torrent(std::move(p));
            }
        }
    });

#ifndef _WIN32
    signal(SIGTERM, signal_handler);
    signal(SIGINT, signal_handler);
#endif

    while (!quit && loop_limit != 0) {
        if (loop_limit > 0) --loop_limit;

        ses.post_torrent_updates();
        ses.post_session_stats();
        ses.post_dht_stats();

        int terminal_width = 80;
        int terminal_height = 50;
        std::tie(terminal_width, terminal_height) = terminal_size();

        int const height = std::min(terminal_height / 2, std::max(5, view.num_visible_torrents() + 2));
        view.set_size(terminal_width, height);
        ses_view.set_pos(height);
        ses_view.set_width(terminal_width);

        int c = 0;
        if (sleep_and_input(&c, refresh_delay)) {
            // Handle input
        }

        pop_alerts(client_state, ses);

        std::string out;
        char str[500];

        int pos = view.height() + ses_view.height();
        set_cursor_pos(0, pos);

        torrent_handle h = view.get_active_handle();

#ifndef TORRENT_DISABLE_DHT
        if (show_dht_status) {
            // DHT status
        }
#endif

        lt::time_point const now = lt::clock_type::now();
        if (h.is_valid()) {
            torrent_status const& s = view.get_active_torrent();

            if (!print_matrix) {
                print((piece_bar(s.pieces, terminal_width - 2) + "\\x1b[K\\n").c_str());
                pos += 1;
            }

            if ((print_downloads && s.state != torrent_status::seeding) || print_peers)
                h.post_peer_info();

            auto& peers = client_state.peers;
            if (print_peers && !peers.empty()) {
                using lt::peer_info;
                std::sort(peers.begin(), peers.end(),
                    [](peer_info const& lhs, peer_info const& rhs) {
                        bool const l = bool(lhs.flags & peer_info::connecting);
                        bool const r = bool(rhs.flags & peer_info::connecting);
                        if (l != r) return l < r;
                        bool const lh = bool(lhs.flags & peer_info::handshake);
                        bool const rh = bool(rhs.flags & peer_info::handshake);
                        if (lh != rh) return lh < rh;
                        return lhs.pid < rhs.pid;
                    });
                pos += print_peer_info(out, peers, terminal_height - pos - 2);
                if (print_peers_legend) {
                    pos += print_peer_legend(out, terminal_height - pos - 2);
                }
            }

            if (print_trackers) {
                // Trackers
            }

            if (print_matrix) {
                // Matrix
            }

            if (print_piece_availability) {
                // Piece availability
            }

            if (print_downloads) {
                // Downloads
            }

            if (print_file_progress && s.has_metadata && h.is_valid()) {
                // File progress
            }
        }

        if (print_log) {
            // Log
        }

        out += "\\x1b[J";
        print(out.c_str());

        std::fflush(stdout);

        if (!monitor_dir.empty() && next_dir_scan < now) {
            scan_dir(monitor_dir, ses);
            next_dir_scan = now + seconds(poll_interval);
        }
    }

    resume_data_loader.join();

    quit = true;
    ses.pause();
    std::printf("saving resume data\\n");

    std::vector<torrent_status> const temp = ses.get_torrent_status(
        [](torrent_status const& st) {
            return st.handle.is_valid() && st.has_metadata && st.need_save_resume;
        }, {});

    int idx = 0;
    for (auto const& st : temp) {
        st.handle.save_resume_data(torrent_handle::save_info_dict);
        ++num_outstanding_resume_data;
        ++idx;
        if ((idx % 32) == 0) {
            std::printf("\\r%d  ", num_outstanding_resume_data);
            pop_alerts(client_state, ses);
        }
    }
    std::printf("\\nwaiting for resume data [%d]\\n", num_outstanding_resume_data);

    while (num_outstanding_resume_data > 0) {
        alert const* a = ses.wait_for_alert(seconds(10));
        if (a == nullptr) continue;
        pop_alerts(client_state, ses);
    }

    if (g_log_file) std::fclose(g_log_file);

#ifndef TORRENT_DISABLE_DHT
    std::printf("\\nsaving session state\\n");
    {
        std::vector<char> out = write_session_params_buf(ses.session_state(lt::session::save_dht_state));
        save_file(".ses_state", out);
    }
#endif

    std::printf("closing session\\n");

    return 0;
}
