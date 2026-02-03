#include "client_test_piece_cache_torrent.hpp"
#include "client_test_piece_cache_utils.hpp"
#include "piece_cache_manager.hpp"

bool add_torrent(lt::session& ses, std::string torrent) try {
    using lt::storage_mode_t;

    static int counter = 0;

    std::printf("[%d] %s\\n", counter++, torrent.c_str());

    lt::error_code ec;
    lt::add_torrent_params atp = lt::load_torrent_file(torrent);

    std::vector<char> resume_data;
    if (load_file(resume_file(atp.info_hashes), resume_data)) {
        lt::add_torrent_params rd = lt::read_resume_data(resume_data, ec);
        if (ec) std::printf("  failed to load resume data: %s\\n", ec.message().c_str());
        else atp = rd;
    }
    else if (seed_from_cache && cache_manager) {
        if (atp.ti) {
            atp = create_cache_resume_data(atp.info_hashes, atp.ti);
            std::printf("  created resume data from cache for %s\\n", atp.ti->name().c_str());
        }
    }

    set_torrent_params(atp);

    atp.flags &= ~lt::torrent_flags::duplicate_is_error;
    ses.async_add_torrent(std::move(atp));
    return true;
}
catch (lt::system_error const& e) {
    std::printf("failed to load torrent \"%s\": %s\\n", torrent.c_str(), e.code().message().c_str());
    return false;
}
