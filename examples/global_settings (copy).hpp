// global_settings.hpp
#pragma once

#include <string>
#include "libtorrent/storage.hpp"

namespace global_settings {

// Global settings for client_test_piece_cache
extern std::string save_path;
extern int max_connections_per_torrent;
extern int torrent_upload_limit;
extern int torrent_download_limit;
extern bool seed_mode;
extern bool share_mode;
extern lt::storage_mode_t allocation_mode;

} // namespace global_settings
