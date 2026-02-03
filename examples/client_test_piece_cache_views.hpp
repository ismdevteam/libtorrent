#pragma once

#include <string>
#include <vector>
#include <libtorrent/peer_info.hpp>
//#include <libtorrent/partial_piece_info.hpp>

struct client_state_t;

int print_peer_info(std::string& out, std::vector<lt::peer_info> const& peers, int max_lines);
int print_peer_legend(std::string& out, int max_lines);
void print_piece(lt::partial_piece_info const& pp, std::vector<lt::peer_info> const& peers, std::string& out);
void print_compact_piece(lt::partial_piece_info const& pp, std::string& out);
