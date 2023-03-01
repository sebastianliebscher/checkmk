#!/usr/bin/env python3
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from collections.abc import Iterable, Mapping

import pytest

from cmk.base.api.agent_based.type_defs import StringTable
from cmk.base.plugins.agent_based.agent_based_api.v1 import Metric, Result, Service, State
from cmk.base.plugins.agent_based.agent_based_api.v1.type_defs import CheckResult
from cmk.base.plugins.agent_based.cisco_mem import (
    _idem_check_cisco_mem,
    discovery_cisco_mem,
    parse_cisco_mem,
    Section,
)


@pytest.mark.parametrize(
    "string_table,expected_parsed_data",
    [
        (
            [
                [["System memory", "319075344", "754665920", "731194056"]],
                [["MEMPOOL_DMA", "41493248", "11754752", "11743928"]],
            ],
            {
                "System memory": ["319075344", "754665920", "731194056"],
                "MEMPOOL_DMA": ["41493248", "11754752", "11743928"],
            },
        ),
        (
            [
                [["System memory", "319075344", "754665920", "731194056"]],
                [[]],
            ],
            {
                "System memory": ["319075344", "754665920", "731194056"],
            },
        ),
        (
            [
                [
                    ["System memory", "1251166290", "3043801006"],
                    ["MEMPOOL_DMA", "0", "0"],
                    ["MEMPOOL_GLOBAL_SHARED", "0", "0"],
                ]
            ],
            {
                "System memory": ["1251166290", "3043801006"],
                "MEMPOOL_DMA": ["0", "0"],
                "MEMPOOL_GLOBAL_SHARED": ["0", "0"],
            },
        ),
    ],
)
def test_parse_cisco_mem_asa(
    string_table: list[StringTable], expected_parsed_data: Section | None
) -> None:
    assert parse_cisco_mem(string_table) == expected_parsed_data


@pytest.mark.parametrize(
    "string_table,expected_parsed_data",
    [
        (
            {
                "System memory": ["1251166290", "3043801006"],
                "MEMPOOL_DMA": ["0", "0"],
                "MEMPOOL_GLOBAL_SHARED": ["0", "0"],
                "Driver text": ["1337", "42"],
            },
            [
                "System memory",
                "MEMPOOL_DMA",
                "MEMPOOL_GLOBAL_SHARED",
            ],
        ),
    ],
)
def test_discovery_cisco_mem(string_table: Section, expected_parsed_data: Iterable[str]) -> None:
    assert list(discovery_cisco_mem(string_table)) == list(
        Service(item=item) for item in expected_parsed_data
    )


@pytest.mark.parametrize(
    "item,params,section,expected_result",
    [
        (
            "MEMPOOL_DMA",
            {
                "trend_perfdata": True,
                "trend_range": 24,
                "trend_showtimeleft": True,
                "trend_timeleft": (12, 6),
            },
            {
                "System memory": ["3848263744", "8765044672"],
                "MEMPOOL_MSGLYR": ["123040", "8265568"],
                "MEMPOOL_DMA": ["429262192", "378092176"],
                "MEMPOOL_GLOBAL_SHARED": ["1092814800", "95541296"],
            },
            (
                Result(state=State.OK, summary="Usage: 53.17% - 409 MiB of 770 MiB"),
                Metric("mem_used_percent", 53.16899356888102, boundaries=(0.0, None)),
            ),
        ),
        (
            "Processor",
            {"levels": (80.0, 90.0)},
            {
                "Processor": ["27086628", "46835412", "29817596"],
            },
            (
                Result(state=State.OK, summary="Usage: 36.64% - 25.8 MiB of 70.5 MiB"),
                Metric(
                    "mem_used_percent",
                    36.64215435612978,
                    levels=(80.0, 90.0),
                    boundaries=(0, None),
                ),
            ),
        ),
        (
            "I/O",
            {"levels": (80.0, 90.0)},
            {
                "I/O": ["12409052", "2271012", "2086880"],
            },
            (
                Result(
                    state=State.WARN,
                    summary="Usage: 84.53% - 11.8 MiB of 14.0 MiB (warn/crit at 80.00%/90.00% used)",
                ),
                Metric(
                    "mem_used_percent",
                    84.52995845249721,
                    levels=(80.00000000000001, 90.0),
                    boundaries=(0, None),
                ),
            ),
        ),
    ],
)
def test_check_cisco_mem(
    item: str,
    params: Mapping[str, object],
    section: Section,
    expected_result: CheckResult,
) -> None:
    assert list(
        _idem_check_cisco_mem(value_store={}, item=item, params=params, section=section)
    ) == list(expected_result)


if __name__ == "__main__":
    # Please keep these lines - they make TDD easy and have no effect on normal test runs.
    # Just run this file from your IDE and dive into the code.
    import os

    from tests.testlib.utils import cmk_path

    assert not pytest.main(
        [
            "--doctest-modules",
            os.path.join(cmk_path(), "cmk/base/plugins/agent_based/cisco_mem_asa.py"),
        ]
    )
    pytest.main(["-T=unit", "-vvsx", __file__])
