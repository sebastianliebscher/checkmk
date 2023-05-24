#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import cmk.utils.cleanup
import cmk.utils.debug
import cmk.utils.paths
from cmk.utils.exceptions import OnError
from cmk.utils.labels import DiscoveredHostLabelsStore, HostLabel, ServiceLabel
from cmk.utils.log import console
from cmk.utils.type_defs import HostName, Item, SectionName, ServiceName

from cmk.automations.results import CheckPreviewEntry

from cmk.checkengine import (
    CheckPlugin,
    DiscoveryPlugin,
    FetcherFunction,
    HostKey,
    ParserFunction,
    SectionPlugin,
    SummarizerFunction,
)
from cmk.checkengine.check_table import ConfiguredService
from cmk.checkengine.checking import CheckPluginName
from cmk.checkengine.checkresults import ActiveCheckResult, ServiceCheckResult
from cmk.checkengine.discovery import (
    analyse_cluster_labels,
    discover_host_labels,
    HostLabelPlugin,
    QualifiedDiscovery,
)
from cmk.checkengine.sectionparser import (
    filter_out_errors,
    make_providers,
    Provider,
    store_piggybacked_sections,
)
from cmk.checkengine.sectionparserutils import check_parsing_errors

import cmk.base.agent_based.checking as checking
import cmk.base.config as config
import cmk.base.core
from cmk.base.api.agent_based.value_store import load_host_value_store, ValueStoreManager
from cmk.base.config import ConfigCache, get_active_check_descriptions

from .autodiscovery import _Transition, get_host_services

__all__ = [
    "CheckPreview",
    "get_check_preview",
    "get_active_check_preview_rows",
    "get_custom_check_preview_rows",
]


@dataclass(frozen=True)
class CheckPreview:
    table: Sequence[CheckPreviewEntry]
    labels: QualifiedDiscovery[HostLabel]
    source_results: Mapping[str, ActiveCheckResult]
    kept_labels: Mapping[HostName, Sequence[HostLabel]]


def get_check_preview(
    host_name: HostName,
    *,
    config_cache: ConfigCache,
    parser: ParserFunction,
    fetcher: FetcherFunction,
    summarizer: SummarizerFunction,
    section_plugins: Mapping[SectionName, SectionPlugin],
    host_label_plugins: Mapping[SectionName, HostLabelPlugin],
    discovery_plugins: Mapping[CheckPluginName, DiscoveryPlugin],
    check_plugins: Mapping[CheckPluginName, CheckPlugin],
    find_service_description: Callable[[HostName, CheckPluginName, Item], ServiceName],
    on_error: OnError,
) -> CheckPreview:
    """Get the list of service of a host or cluster and guess the current state of
    all services if possible"""
    ip_address = (
        None
        if config_cache.is_cluster(host_name)
        # We *must* do the lookup *before* calling `get_host_attributes()`
        # because...  I don't know... global variables I guess.  In any case,
        # doing it the other way around breaks one integration test.
        else config.lookup_ip_address(config_cache, host_name)
    )

    fetched = fetcher(host_name, ip_address=ip_address)
    parsed = parser((f[0], f[1]) for f in fetched)

    host_sections_no_error = filter_out_errors(parser((f[0], f[1]) for f in fetched))
    store_piggybacked_sections(host_sections_no_error)
    providers = make_providers(host_sections_no_error, section_plugins)

    if config_cache.is_cluster(host_name):
        host_labels, kept_labels = analyse_cluster_labels(
            host_name,
            config_cache.nodes_of(host_name) or (),
            discovered_host_labels={
                node_name: discover_host_labels(
                    node_name,
                    host_label_plugins,
                    providers=providers,
                    on_error=on_error,
                )
                for node_name in config_cache.nodes_of(host_name) or ()
            },
            existing_host_labels={
                node_name: DiscoveredHostLabelsStore(node_name).load()
                for node_name in config_cache.nodes_of(host_name) or ()
            },
        )
    else:
        host_labels = QualifiedDiscovery[HostLabel](
            preexisting=DiscoveredHostLabelsStore(host_name).load(),
            current=discover_host_labels(
                host_name,
                host_label_plugins,
                providers=providers,
                on_error=on_error,
            ),
        )
        kept_labels = {host_name: host_labels.kept()}

    for result in check_parsing_errors(
        itertools.chain.from_iterable(resolver.parsing_errors for resolver in providers.values())
    ):
        for line in result.details:
            console.warning(line)

    grouped_services = get_host_services(
        host_name,
        config_cache=config_cache,
        providers=providers,
        plugins=discovery_plugins,
        get_service_description=find_service_description,
        on_error=on_error,
    )

    with load_host_value_store(host_name, store_changes=False) as value_store_manager:
        passive_rows = [
            _check_preview_table_row(
                host_name,
                config_cache=config_cache,
                check_plugins=check_plugins,
                service=ConfiguredService(
                    check_plugin_name=entry.check_plugin_name,
                    item=entry.item,
                    description=find_service_description(host_name, *entry.id()),
                    parameters=config.compute_check_parameters(
                        host_name,
                        entry.check_plugin_name,
                        entry.item,
                        entry.parameters,
                    ),
                    discovered_parameters=entry.parameters,
                    service_labels={n: ServiceLabel(n, v) for n, v in entry.service_labels.items()},
                    is_enforced=True,
                ),
                check_source=check_source,
                providers=providers,
                found_on_nodes=found_on_nodes,
                value_store_manager=value_store_manager,
            )
            for check_source, services_with_nodes in grouped_services.items()
            for entry, found_on_nodes in services_with_nodes
        ] + [
            _check_preview_table_row(
                host_name,
                config_cache=config_cache,
                service=service,
                check_plugins=check_plugins,
                check_source="manual",  # "enforced" would be nicer
                providers=providers,
                found_on_nodes=[host_name],
                value_store_manager=value_store_manager,
            )
            for _ruleset_name, service in config_cache.enforced_services_table(host_name).values()
        ]

    return CheckPreview(
        table=[*passive_rows],
        labels=host_labels,
        source_results={
            src.ident: result for (src, _sections), result in zip(parsed, summarizer(parsed))
        },
        kept_labels=kept_labels,
    )


def _check_preview_table_row(
    host_name: HostName,
    *,
    config_cache: ConfigCache,
    service: ConfiguredService,
    check_plugins: Mapping[CheckPluginName, CheckPlugin],
    check_source: _Transition | Literal["manual"],
    providers: Mapping[HostKey, Provider],
    found_on_nodes: Sequence[HostName],
    value_store_manager: ValueStoreManager,
) -> CheckPreviewEntry:
    check_plugin = check_plugins.get(service.check_plugin_name)
    ruleset_name = (
        str(check_plugin.ruleset_name) if check_plugin and check_plugin.ruleset_name else None
    )

    result = (
        checking.get_aggregated_result(
            host_name,
            config_cache,
            providers,
            service,
            check_plugin,
            value_store_manager=value_store_manager,
            rtc_package=None,
        ).result
        if check_plugin is not None
        else ServiceCheckResult.check_not_implemented()
    )

    def make_output() -> str:
        return (
            result.output
            or f"WAITING - {check_source.split('_')[-1].title()} check, cannot be done offline"
        )

    return CheckPreviewEntry(
        check_source=check_source,
        check_plugin_name=str(service.check_plugin_name),
        ruleset_name=ruleset_name,
        item=service.item,
        discovered_parameters=service.discovered_parameters,
        effective_parameters=service.parameters.preview(cmk.base.core.timeperiod_active),
        description=service.description,
        state=result.state,
        output=make_output(),
        metrics=[],
        labels={l.name: l.value for l in service.service_labels.values()},
        found_on_nodes=list(found_on_nodes),
    )


def get_custom_check_preview_rows(
    config_cache: ConfigCache, host_name: HostName
) -> Sequence[CheckPreviewEntry]:
    custom_checks = config_cache.custom_checks(host_name)
    ignored_services = config.IgnoredServices(config_cache, host_name)

    def make_check_source(desc: str) -> str:
        return "ignored_custom" if desc in ignored_services else "custom"

    def make_output(desc: str) -> str:
        pretty = make_check_source(desc).rsplit("_", maxsplit=1)[-1].title()
        return f"WAITING - {pretty} check, cannot be done offline"

    return list(
        {
            entry["service_description"]: CheckPreviewEntry(
                check_source=make_check_source(entry["service_description"]),
                check_plugin_name="custom",
                ruleset_name=None,
                item=entry["service_description"],
                discovered_parameters=None,
                effective_parameters=None,
                description=entry["service_description"],
                state=None,
                output=make_output(entry["service_description"]),
                metrics=[],
                labels={},
                found_on_nodes=[host_name],
            )
            for entry in custom_checks
        }.values()
    )


def get_active_check_preview_rows(
    config_cache: ConfigCache,
    host_name: HostName,
) -> Sequence[CheckPreviewEntry]:
    alias = config_cache.alias(host_name)
    active_checks = config_cache.active_checks(host_name)
    host_attrs = config_cache.get_host_attributes(host_name)
    ignored_services = config.IgnoredServices(config_cache, host_name)

    def make_check_source(desc: str) -> str:
        return "ignored_active" if desc in ignored_services else "active"

    def make_output(desc: str) -> str:
        pretty = make_check_source(desc).rsplit("_", maxsplit=1)[-1].title()
        return f"WAITING - {pretty} check, cannot be done offline"

    return list(
        {
            descr: CheckPreviewEntry(
                check_source=make_check_source(descr),
                check_plugin_name=plugin_name,
                ruleset_name=None,
                item=descr,
                discovered_parameters=None,
                effective_parameters=None,
                description=descr,
                state=None,
                output=make_output(descr),
                metrics=[],
                labels={},
                found_on_nodes=[host_name],
            )
            for plugin_name, entries in active_checks
            for params in entries
            for descr in get_active_check_descriptions(
                plugin_name,
                config.active_check_info[plugin_name],
                host_name,
                alias,
                host_attrs,
                params,
            )
        }.values()
    )
