#pragma once

#include <libtorrent/session.hpp>
#include <libtorrent/info_hash.hpp>
#include <set>
#include <memory>
#include <vector>
#include <iostream>

extern bool print_trackers;
extern bool print_peers;
extern bool print_peers_legend;
extern bool print_connecting_peers;
extern bool print_log;
extern bool print_downloads;
extern bool print_matrix;
extern bool print_file_progress;
extern bool print_piece_availability;
extern bool show_pad_files;
extern bool show_dht_status;
extern bool print_ip;
extern bool print_peaks;
extern bool print_local_ip;
extern bool print_timers;
extern bool print_block;
extern bool print_fails;
extern bool print_send_bufs;
extern bool print_disk_stats;

extern bool enable_piece_cache;
extern bool cache_during_download;
extern std::string cache_root;
extern std::unique_ptr<PieceCacheManager> cache_manager;
extern std::set<lt::info_hash_t> g_initialized_torrents;

extern bool disable_original_storage;
extern bool seed_from_cache;

extern int num_outstanding_resume_data;

#ifndef TORRENT_DISABLE_DHT
extern std::vector<lt::dht_lookup> dht_active_requests;
extern std::vector<lt::dht_routing_bucket> dht_routing_table;
#endif

extern FILE* g_log_file;

extern lt::storage_mode_t allocation_mode;
extern std::string save_path;
extern int torrent_upload_limit;
extern int torrent_download_limit;
extern std::string monitor_dir;
extern int poll_interval;
extern int max_connections_per_torrent;
extern bool seed_mode;
extern bool stats_enabled;
extern bool exit_on_finish;
extern bool share_mode;
extern bool quit;

extern std::string peer;
