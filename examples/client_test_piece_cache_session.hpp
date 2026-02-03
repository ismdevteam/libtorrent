#pragma once

#include <libtorrent/session.hpp>

void set_torrent_params(lt::add_torrent_params& p);
void scan_dir(std::string const& dir_path, lt::session& ses);
void add_magnet(lt::session& ses, lt::string_view uri);

