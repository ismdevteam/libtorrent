#include "client_test_piece_cache_alerts.hpp"
#include "client_test_piece_cache_globals.hpp"
#include "client_test_piece_cache_utils.hpp"
#include "piece_cache_manager.hpp"
#include <iostream>

bool handle_alert(client_state_t& client_state, lt::alert* a) {
    using namespace lt;

    if (a->type() == lt::read_piece_alert::alert_type) {
        auto* rp = lt::alert_cast<lt::read_piece_alert>(a);
        if (rp && cache_manager) {
            auto handle = rp->handle;
            if (handle.is_valid()) {
                try {
                    lt::info_hash_t ih = handle.info_hashes();
                    if (g_initialized_torrents.find(ih) != g_initialized_torrents.end()) {
                        cache_manager->cache_piece_data(
                            ih,
                            rp->piece,
                            rp->buffer.get(),
                            rp->size
                        );
                    }
                } catch (const std::exception& e) {
                    std::cerr << "Error caching piece: " << e.what() << std::endl;
                }
            }
        }
        return false;
    }
    else if (a->type() == lt::piece_finished_alert::alert_type) {
        auto* pf = lt::alert_cast<lt::piece_finished_alert>(a);
        if (pf && cache_manager && cache_during_download) {
            auto handle = pf->handle;
            if (handle.is_valid()) {
                try {
                    lt::info_hash_t ih = handle.info_hashes();
                    if (g_initialized_torrents.find(ih) != g_initialized_torrents.end()) {
                        std::cout << "Piece " << static_cast<int>(pf->piece_index)
                                  << " finished, reading for cache..." << std::endl;
                        handle.read_piece(pf->piece_index);
                    }
                } catch (const std::exception& e) {
                    std::cerr << "Error reading finished piece: " << e.what() << std::endl;
                }
            }
        }
        return false;
    }
    else if (a->type() == lt::add_torrent_alert::alert_type) {
        auto* ata = lt::alert_cast<lt::add_torrent_alert>(a);
        if (ata && cache_manager && !ata->error) {
            auto handle = ata->handle;
            if (handle.is_valid() && handle.status().has_metadata) {
                try {
                    lt::info_hash_t ih = handle.info_hashes();
                    if (g_initialized_torrents.find(ih) == g_initialized_torrents.end()) {
                        cache_manager->initialize_torrent(ih, handle.torrent_file());
                        g_initialized_torrents.insert(ih);
                        std::cout << "Initialized cache for torrent: " << handle.status().name << std::endl;
                    }
                } catch (const std::exception& e) {
                    std::cerr << "Error initializing cache: " << e.what() << std::endl;
                }
            }
        }
    }
    else if (a->type() == lt::metadata_received_alert::alert_type) {
        auto* mra = lt::alert_cast<lt::metadata_received_alert>(a);
        if (mra && cache_manager) {
            auto handle = mra->handle;
            if (handle.is_valid() && handle.status().has_metadata) {
                try {
                    lt::info_hash_t ih = handle.info_hashes();
                    if (g_initialized_torrents.find(ih) == g_initialized_torrents.end()) {
                        cache_manager->initialize_torrent(ih, handle.torrent_file());
                        g_initialized_torrents.insert(ih);
                        std::cout << "Initialized cache for magnet torrent: " << handle.status().name << std::endl;
                    }
                } catch (const std::exception& e) {
                    std::cerr << "Error initializing cache for magnet: " << e.what() << std::endl;
                }
            }
        }
    }

    if (session_stats_alert* s = alert_cast<session_stats_alert>(a)) {
        client_state.ses_view.update_counters(s->counters(), s->timestamp());
        return !stats_enabled;
    }

    if (auto* p = alert_cast<peer_info_alert>(a)) {
        if (client_state.view.get_active_torrent().handle == p->handle)
            client_state.peers = std::move(p->peer_info);
        return true;
    }

    if (auto* p = alert_cast<file_progress_alert>(a)) {
        if (client_state.view.get_active_torrent().handle == p->handle)
            client_state.file_progress = std::move(p->files);
        return true;
    }

    if (auto* p = alert_cast<piece_info_alert>(a)) {
        if (client_state.view.get_active_torrent().handle == p->handle) {
            client_state.download_queue = std::move(p->piece_info);
            client_state.download_queue_block_info = std::move(p->block_data);
        }
        return true;
    }

    if (auto* p = alert_cast<piece_availability_alert>(a)) {
        if (client_state.view.get_active_torrent().handle == p->handle)
            client_state.piece_availability = std::move(p->piece_availability);
        return true;
    }

    if (auto* p = alert_cast<tracker_list_alert>(a)) {
        if (client_state.view.get_active_torrent().handle == p->handle)
            client_state.trackers = std::move(p->trackers);
        return true;
    }

#ifndef TORRENT_DISABLE_DHT
    if (dht_stats_alert* p = alert_cast<dht_stats_alert>(a)) {
        dht_active_requests = p->active_requests;
        dht_routing_table = p->routing_table;
        return true;
    }
#endif

    if (alert_cast<peer_connect_alert>(a)) return true;

    if (peer_disconnected_alert* pd = alert_cast<peer_disconnected_alert>(a)) {
        if (pd->op == operation_t::connect || pd->error == errors::timed_out_no_handshake)
            return true;
    }

    if (metadata_received_alert* p = alert_cast<metadata_received_alert>(a)) {
        torrent_handle h = p->handle;
        h.save_resume_data(torrent_handle::save_info_dict);
        ++num_outstanding_resume_data;
    }

    if (add_torrent_alert* p = alert_cast<add_torrent_alert>(a)) {
        if (p->error) {
            std::fprintf(stderr, "failed to add torrent: %s %s\\n"
                , p->params.ti ? p->params.ti->name().c_str() : p->params.name.c_str()
                , p->error.message().c_str());
        }
        else {
            torrent_handle h = p->handle;
            h.save_resume_data(torrent_handle::save_info_dict | torrent_handle::if_metadata_changed);
            ++num_outstanding_resume_data;
            if (!peer.empty()) {
                auto port = peer.find_last_of(':');
                if (port != std::string::npos) {
                    peer[port++] = '\\0';
                    char const* ip = peer.data();
                    int const peer_port = atoi(peer.data() + port);
                    error_code ec;
                    if (peer_port > 0)
                        h.connect_peer(tcp::endpoint(make_address(ip, ec), std::uint16_t(peer_port)));
                }
            }
        }
    }

    if (torrent_finished_alert* p = alert_cast<torrent_finished_alert>(a)) {
        p->handle.set_max_connections(max_connections_per_torrent / 2);
        if (cache_manager) {
            auto handle = p->handle;
            if (handle.is_valid() && handle.status().has_metadata) {
                try {
                    lt::info_hash_t ih = handle.info_hashes();
                    if (g_initialized_torrents.find(ih) != g_initialized_torrents.end()) {
                        auto ti = handle.torrent_file();
                        if (ti) {
                            std::cout << "Torrent finished, caching all " << ti->num_pieces() << " pieces..." << std::endl;
                            for (lt::piece_index_t i(0); i < ti->num_pieces(); ++i) {
                                handle.read_piece(i);
                            }
                        }
                    }
                } catch (const std::exception& e) {
                    std::cerr << "Error reading pieces for cache: " << e.what() << std::endl;
                }
            }
        }
        torrent_handle h = p->handle;
        h.save_resume_data(torrent_handle::save_info_dict | torrent_handle::if_download_progress);
        ++num_outstanding_resume_data;
        if (exit_on_finish) quit = true;
    }

    if (save_resume_data_alert* p = alert_cast<save_resume_data_alert>(a)) {
        --num_outstanding_resume_data;
        auto const buf = write_resume_data_buf(p->params);
        save_file(resume_file(p->params.info_hashes), buf);
    }

    if (save_resume_data_failed_alert* p = alert_cast<save_resume_data_failed_alert>(a)) {
        --num_outstanding_resume_data;
        return p->error == lt::errors::resume_data_not_modified;
    }

    if (torrent_paused_alert* p = alert_cast<torrent_paused_alert>(a)) {
        if (!quit) {
            torrent_handle h = p->handle;
            h.save_resume_data(torrent_handle::save_info_dict);
            ++num_outstanding_resume_data;
        }
    }

    if (state_update_alert* p = alert_cast<state_update_alert>(a)) {
        lt::torrent_handle const prev = client_state.view.get_active_handle();
        client_state.view.update_torrents(std::move(p->status));
        if (client_state.view.get_active_handle() != prev)
            client_state.clear();
        return true;
    }

    if (torrent_removed_alert* p = alert_cast<torrent_removed_alert>(a)) {
        client_state.view.remove_torrent(std::move(p->handle));
    }
    return false;
}

void pop_alerts(client_state_t& client_state, lt::session& ses) {
    std::vector<lt::alert*> alerts;
    ses.pop_alerts(&alerts);
    for (auto a : alerts) {
        if (::handle_alert(client_state, a)) continue;
        std::string event_string;
        print_alert(a, event_string);
        client_state.events.push_back(event_string);
        if (client_state.events.size() >= 20) client_state.events.pop_front();
    }
}
