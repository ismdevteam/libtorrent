#include "client_test_piece_cache_session.hpp"
#include "client_test_piece_cache_globals.hpp"
#include "client_test_piece_cache_utils.hpp"
#include "piece_cache_manager.hpp"

void set_torrent_params(lt::add_torrent_params& p) {
    p.max_connections = max_connections_per_torrent;
    p.max_uploads = -1;
    p.upload_limit = torrent_upload_limit;
    p.download_limit = torrent_download_limit;

    if (disable_original_storage) {
        if (seed_from_cache) {
            p.save_path = cache_root;
        } else {
            p.save_path = "/tmp/dummy_save_path";
        }
    } else {
        p.save_path = save_path;
    }

    if (seed_mode) p.flags |= lt::torrent_flags::seed_mode;
    if (share_mode) p.flags |= lt::torrent_flags::share_mode;
    p.storage_mode = allocation_mode;
}

void scan_dir(std::string const& dir_path, lt::session& ses) {
    using namespace lt;
    error_code ec;
    std::vector<std::string> ents = list_dir(dir_path,
        [](lt::string_view p) { return p.size() > 8 && p.substr(p.size() - 8) == ".torrent"; }, ec);
    if (ec) {
        std::fprintf(stderr, "failed to list directory: (%s : %d) %s\\n",
            ec.category().name(), ec.value(), ec.message().c_str());
        return;
    }

    for (auto const& e : ents) {
        std::string const file = path_append(dir_path, e);
        if (add_torrent(ses, file)) {
            if (::remove(file.c_str()) < 0) {
                std::fprintf(stderr, "failed to remove torrent file: \"%s\"\\n", file.c_str());
            }
        }
    }
}

void add_magnet(lt::session& ses, lt::string_view uri) {
    lt::error_code ec;
    lt::add_torrent_params p = lt::parse_magnet_uri(uri.to_string(), ec);

    if (ec) {
        std::printf("invalid magnet link \"%s\": %s\\n", uri.to_string().c_str(), ec.message().c_str());
        return;
    }

    std::vector<char> resume_data;
    if (load_file(resume_file(p.info_hashes), resume_data)) {
        p = lt::read_resume_data(resume_data, ec);
        if (ec) std::printf("  failed to load resume data: %s\\n", ec.message().c_str());
    }

    set_torrent_params(p);

    std::printf("adding magnet: %s\\n", uri.to_string().c_str());
    ses.async_add_torrent(std::move(p));
}
