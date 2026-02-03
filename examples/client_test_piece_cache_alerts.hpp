#pragma once

#include <libtorrent/session.hpp>
#include <libtorrent/alert_types.hpp>

struct client_state_t;

bool handle_alert(client_state_t& client_state, lt::alert* a);
void pop_alerts(client_state_t& client_state, lt::session& ses);
