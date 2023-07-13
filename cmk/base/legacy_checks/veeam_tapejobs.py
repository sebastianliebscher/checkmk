#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


import time

from cmk.base.check_api import (
    check_levels,
    get_age_human_readable,
    get_item_state,
    get_timestamp_human_readable,
    LegacyCheckDefinition,
    set_item_state,
)
from cmk.base.config import check_info

veeam_tapejobs_default_levels = (1 * 3600 * 24, 2 * 3600 * 24)

BACKUP_STATE = {"Success": 0, "Warning": 1, "Failed": 2}


def parse_veeam_tapejobs(info):
    parsed = {}
    columns = [s.lower() for s in info[0]]

    for line in info[1:]:
        if len(line) < len(columns):
            continue

        name = " ".join(line[: -(len(columns) - 1)])
        job_id, last_result, last_state = line[-(len(columns) - 1) :]
        parsed[name] = {
            "job_id": job_id,
            "last_result": last_result,
            "last_state": last_state,
        }

    return parsed


def inventory_veeam_tapejobs(parsed):
    for job in parsed:
        yield job, veeam_tapejobs_default_levels


def check_veeam_tapejobs(item, params, parsed):
    if not (data := parsed.get(item)):
        return
    job_id = data["job_id"]
    last_result = data["last_result"]
    last_state = data["last_state"]

    if last_result != "None" or last_state not in ("Working", "Idle"):
        yield BACKUP_STATE.get(last_result, 2), "Last backup result: %s" % last_result
        yield 0, "Last state: %s" % last_state
        set_item_state("%s.running_since" % job_id, None)
        return

    running_since = get_item_state("%s.running_since" % job_id)
    now = time.time()
    if not running_since:
        running_since = now
        set_item_state("%s.running_since" % job_id, now)
    running_time = now - running_since

    yield 0, "Backup in progress since %s (currently %s)" % (
        get_timestamp_human_readable(running_since),
        last_state.lower(),
    )
    yield check_levels(
        running_time,
        None,
        params,
        human_readable_func=get_age_human_readable,
        infoname="Running time",
    )


check_info["veeam_tapejobs"] = LegacyCheckDefinition(
    parse_function=parse_veeam_tapejobs,
    service_name="VEEAM Tape Job %s",
    discovery_function=inventory_veeam_tapejobs,
    check_function=check_veeam_tapejobs,
    check_ruleset_name="veeam_tapejobs",
)
