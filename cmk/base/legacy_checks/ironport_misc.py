#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info


def check_ironport_misc(item, params, info):
    return (3, "Sorry. Check not implemented in this version.")


check_info["ironport_misc"] = LegacyCheckDefinition(
    service_name="%s",
    check_function=check_ironport_misc,
    check_ruleset_name="obsolete",
)
