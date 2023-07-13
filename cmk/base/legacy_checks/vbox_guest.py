#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info


def vbox_guest_make_dict(info):
    # output differs in version 6.x so we need to deal with empty values for
    # /VirtualBox/GuestInfo/OS/ServicePack
    return {l[1].split("/", 2)[2].rstrip(","): l[3] if len(l) == 4 else "" for l in info}


def check_vbox_guest(_no_item, _no_params, info):
    if len(info) == 1 and info[0][0] == "ERROR":
        return (3, "Error running VBoxControl guestproperty enumerate")
    try:
        d = vbox_guest_make_dict(info)
    except Exception:
        d = {}

    if len(d) == 0:
        return (2, "No guest additions installed")

    version = d.get("GuestAdd/Version")
    revision = d.get("GuestAdd/Revision")
    if not version or not version[0].isdigit():
        return (3, "No guest addition version available")
    infotext = "version: %s, revision: %s" % (version, revision)

    host_version = d["HostInfo/VBoxVer"]
    host_revision = d["HostInfo/VBoxRev"]
    if (host_version, host_revision) != (version, revision):
        return (1, infotext + ", Host has %s/%s" % (host_version, host_revision))
    return (0, infotext)


def inventory_vbox_guest(info):
    if len(info) > 0:
        return [(None, None)]
    return []


check_info["vbox_guest"] = LegacyCheckDefinition(
    service_name="VBox Guest Additions",
    discovery_function=inventory_vbox_guest,
    check_function=check_vbox_guest,
    check_ruleset_name="vm_state",
)
