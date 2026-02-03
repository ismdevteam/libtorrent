#pragma once

#include <libtorrent/torrent_handle.hpp>
#include <libtorrent/add_torrent_params.hpp>

bool add_torrent(lt::session& ses, std::string torrent);
