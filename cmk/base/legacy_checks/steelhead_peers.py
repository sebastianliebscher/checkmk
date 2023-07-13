#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

# .1.3.6.1.4.1.17163.1.1.2.6.1.1.2.1 vadetsh1 --> STEELHEAD-MIB::peerHostname.1
# .1.3.6.1.4.1.17163.1.1.2.6.1.1.3.1 8.5.3c --> STEELHEAD-MIB::peerVersion.1
# .1.3.6.1.4.1.17163.1.1.2.6.1.1.4.1 10.1.0.14 --> STEELHEAD-MIB::peerAddress.1
# .1.3.6.1.4.1.17163.1.1.2.6.1.1.5.1 CX770 --> STEELHEAD-MIB::peerModel.1


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info
from cmk.base.plugins.agent_based.agent_based_api.v1 import SNMPTree
from cmk.base.plugins.agent_based.utils.steelhead import DETECT_STEELHEAD


def inventory_steelhead_peers(info):
    return [(x[0], None) for x in info if x[-1] != "Steelhead Mobile"]


def check_steelhead_peers(item, _no_params, info):
    for host, version, client, client_type in info:
        if host == item:
            return 0, "Version: %s, Client Address: %s (%s)" % (version, client, client_type)
    return 2, "Peer not connected"


check_info["steelhead_peers"] = LegacyCheckDefinition(
    detect=DETECT_STEELHEAD,
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.17163.1.1.2.6.1.1",
        oids=["2", "3", "4", "5"],
    ),
    service_name="Peer %s",
    discovery_function=inventory_steelhead_peers,
    check_function=check_steelhead_peers,
)
