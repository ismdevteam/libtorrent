#include "client_test_piece_cache_views.hpp"
#include "client_test_piece_cache_utils.hpp"

int print_peer_info(std::string& out, std::vector<lt::peer_info> const& peers, int max_lines) {
    using namespace lt;
    int pos = 0;
    if (print_ip) out += "IP                             ";
    if (print_local_ip) out += "local IP                       ";
    out += "progress        down     (total";
    if (print_peaks) out += " | peak  ";
    out += " )  up      (total";
    if (print_peaks) out += " | peak  ";
    out += " ) sent-req tmo bsy rcv flags            dn  up  source  ";
    if (print_fails) out += "fail hshf ";
    if (print_send_bufs) out += " rq sndb (recvb |alloc | wmrk ) q-bytes ";
    if (print_timers) out += "inactive wait timeout q-time ";
    out += "  v disk ^    rtt  ";
    if (print_block) out += "block-progress ";
    out += "client \\x1b[K\\n";
    ++pos;

    char str[500];
    for (std::vector<peer_info>::const_iterator i = peers.begin(); i != peers.end(); ++i) {
        if ((i->flags & (peer_info::handshake | peer_info::connecting) && !print_connecting_peers)) {
            continue;
        }

        if (print_ip) {
#if TORRENT_USE_I2P
            if (i->flags & peer_info::i2p_socket) {
                base32encode_i2p(i->i2p_destination(), out, 31);
            }
            else
#endif
            {
                std::snprintf(str, sizeof(str), "%-30s ", ::print_endpoint(i->ip).c_str());
                out += str;
            }
        }
        if (print_local_ip) {
#if TORRENT_USE_I2P
            if (i->flags & peer_info::i2p_socket)
                out += "                               ";
            else
#endif
            {
                std::snprintf(str, sizeof(str), "%-30s ", ::print_endpoint(i->local_endpoint).c_str());
                out += str;
            }
        }

        char temp[10];
        std::snprintf(temp, sizeof(temp), "%d/%d", i->download_queue_length, i->target_dl_queue_length);
        temp[7] = 0;

        char peer_progress[10];
        std::snprintf(peer_progress, sizeof(peer_progress), "%.1f%%", i->progress_ppm / 10000.0);
        std::snprintf(str, sizeof(str),
            , progress_bar(i->progress_ppm / 1000, 15, col_green, '#', '-', peer_progress).c_str()
            , esc("32"), add_suffix(i->down_speed, "/s").c_str()
            , add_suffix(i->total_download).c_str()
            , print_peaks ? ("|" + add_suffix(i->download_rate_peak, "/s")).c_str() : ""
            , esc("31"), add_suffix(i->up_speed, "/s").c_str(), add_suffix(i->total_upload).c_str()
            , print_peaks ? ("|" + add_suffix(i->upload_rate_peak, "/s")).c_str() : ""
            , esc("0")
            , temp
            , i->timed_out_requests
            , i->busy_requests
            , i->upload_queue_length
            , color("I", (i->flags & peer_info::interesting)?col_white:col_blue).c_str()
            , color("C", (i->flags & peer_info::choked)?col_white:col_blue).c_str()
            , color("i", (i->flags & peer_info::remote_interested)?col_white:col_blue).c_str()
            , color("c", (i->flags & peer_info::remote_choked)?col_white:col_blue).c_str()
            , color("x", (i->flags & peer_info::supports_extensions)?col_white:col_blue).c_str()
            , color("o", (i->flags & peer_info::local_connection)?col_white:col_blue).c_str()
            , color("p", (i->flags & peer_info::on_parole)?col_white:col_blue).c_str()
            , color("O", (i->flags & peer_info::optimistic_unchoke)?col_white:col_blue).c_str()
            , color("S", (i->flags & peer_info::snubbed)?col_white:col_blue).c_str()
            , color("U", (i->flags & peer_info::upload_only)?col_white:col_blue).c_str()
            , color("e", (i->flags & peer_info::endgame_mode)?col_white:col_blue).c_str()
            , color("E", (i->flags & peer_info::rc4_encrypted)?col_white:(i->flags & peer_info::plaintext_encrypted)?col_cyan:col_blue).c_str()
            , color("h", (i->flags & peer_info::holepunched)?col_white:col_blue).c_str()
            , color("s", (i->flags & peer_info::seed)?col_white:col_blue).c_str()
            , color("u", (i->flags & peer_info::utp_socket)?col_white:col_blue).c_str()
            , color("I", (i->flags & peer_info::i2p_socket)?col_white:col_blue).c_str()
            , color("d", (i->read_state & peer_info::bw_disk)?col_white:col_blue).c_str()
            , color("l", (i->read_state & peer_info::bw_limit)?col_white:col_blue).c_str()
            , color("n", (i->read_state & peer_info::bw_network)?col_white:col_blue).c_str()
            , color("d", (i->write_state & peer_info::bw_disk)?col_white:col_blue).c_str()
            , color("l", (i->write_state & peer_info::bw_limit)?col_white:col_blue).c_str()
            , color("n", (i->write_state & peer_info::bw_network)?col_white:col_blue).c_str()
            , color("t", (i->source & peer_info::tracker)?col_white:col_blue).c_str()
            , color("p", (i->source & peer_info::pex)?col_white:col_blue).c_str()
            , color("d", (i->source & peer_info::dht)?col_white:col_blue).c_str()
            , color("l", (i->source & peer_info::lsd)?col_white:col_blue).c_str()
            , color("r", (i->source & peer_info::resume_data)?col_white:col_blue).c_str()
            , color("i", (i->source & peer_info::incoming)?col_white:col_blue).c_str());
        out += str;

        if (print_fails) {
            std::snprintf(str, sizeof(str), "%4d %4d ", i->failcount, i->num_hashfails);
            out += str;
        }
        if (print_send_bufs) {
            std::snprintf(str, sizeof(str), "%3d %6s %6s|%6s|%6s%7s ",
                i->requests_in_buffer
                , add_suffix(i->used_send_buffer).c_str()
                , add_suffix(i->used_receive_buffer).c_str()
                , add_suffix(i->receive_buffer_size).c_str()
                , add_suffix(i->receive_buffer_watermark).c_str()
                , add_suffix(i->queue_bytes).c_str());
            out += str;
        }
        if (print_timers) {
            char req_timeout[20] = "-";
            if (i->download_queue_length > 0)
                std::snprintf(req_timeout, sizeof(req_timeout), "%d", i->request_timeout);

            std::snprintf(str, sizeof(str), "%8d %4d %7s %6d "
                , int(total_seconds(i->last_active))
                , int(total_seconds(i->last_request))
                , req_timeout
                , int(total_seconds(i->download_queue_time)));
            out += str;
        }
        std::snprintf(str, sizeof(str), "%s|%s %5d "
            , add_suffix(i->pending_disk_bytes).c_str()
            , add_suffix(i->pending_disk_read_bytes).c_str()
            , i->rtt);
        out += str;

        if (print_block) {
            if (i->downloading_piece_index >= piece_index_t(0)) {
                char buf[50];
                std::snprintf(buf, sizeof(buf), "%d:%d", static_cast<int>(i->downloading_piece_index), i->downloading_block_index);
                out += progress_bar(i->downloading_progress * 1000 / i->downloading_total, 14, col_green, '-', '#', buf);
            }
            else {
                out += progress_bar(0, 14);
            }
        }

        out += " ";

        if (i->flags & lt::peer_info::handshake) {
            out += esc("31");
            out += " waiting for handshake";
            out += esc("0");
        }
        else if (i->flags & lt::peer_info::connecting) {
            out += esc("31");
            out += " connecting to peer";
            out += esc("0");
        }
        else {
            out += " ";
            out += i->client;
        }
        out += "\\x1b[K\\n";
        ++pos;
        if (pos >= max_lines) break;
    }
    return pos;
}

int print_peer_legend(std::string& out, int max_lines) {
    // Implementation
    return 0;
}

void print_piece(lt::partial_piece_info const& pp, std::vector<lt::peer_info> const& peers, std::string& out) {
    // Implementation
}

void print_compact_piece(lt::partial_piece_info const& pp, std::string& out) {
    // Implementation
}
