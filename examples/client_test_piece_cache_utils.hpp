#pragma once

#include <string>
#include <vector>
#include <libtorrent/session.hpp>
#include <libtorrent/error_code.hpp>
#include <libtorrent/string_view.hpp>

bool load_file(std::string const& filename, std::vector<char>& v, int limit = 8000000);
bool is_absolute_path(std::string const& f);
std::string path_append(std::string const& lhs, std::string const& rhs);
std::string make_absolute_path(std::string const& p);
std::string print_endpoint(lt::tcp::endpoint const& ep);
std::string to_hex(lt::sha1_hash const& s);
std::vector<std::string> list_dir(std::string path, bool (*filter_fun)(lt::string_view), lt::error_code& ec);
bool is_resume_file(std::string const& s);
char const* timestamp();
