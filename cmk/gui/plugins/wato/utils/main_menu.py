#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

import re

from cmk.gui.i18n import _l
from cmk.gui.watolib.main_menu import (
    ABCMainModule,
    main_module_registry,
    main_module_topic_registry,
    MainModuleTopic,
    MenuItem,
)


class WatoModule(MenuItem):
    """Used with register_modules() in pre 1.6 versions to register main modules"""


def register_modules(*args: WatoModule) -> None:
    """Register one or more top level modules to Checkmk Setup.
    The registered modules are displayed in the navigation of Setup."""
    for wato_module in args:
        assert isinstance(wato_module, WatoModule)

        internal_name = re.sub("[^a-zA-Z]", "", wato_module.mode_or_url)

        cls = type(
            "LegacyMainModule%s" % internal_name.title(),
            (ABCMainModule,),
            {
                "mode_or_url": wato_module.mode_or_url,
                "topic": MainModuleTopicExporter,
                "title": wato_module.title,
                "icon": wato_module.icon,
                "permission": wato_module.permission,
                "description": wato_module.description,
                "sort_index": wato_module.sort_index,
                "is_show_more": False,
            },
        )
        main_module_registry.register(cls)


#   .--Topics--------------------------------------------------------------.
#   |                     _____           _                                |
#   |                    |_   _|__  _ __ (_) ___ ___                       |
#   |                      | |/ _ \| '_ \| |/ __/ __|                      |
#   |                      | | (_) | |_) | | (__\__ \                      |
#   |                      |_|\___/| .__/|_|\___|___/                      |
#   |                              |_|                                     |
#   +----------------------------------------------------------------------+
#   | Register the builtin topics. These are the ones that may be          |
#   | referenced by different Setup plugins. Additional individual plugins  |
#   | are allowed to create their own topics.                              |
#   '----------------------------------------------------------------------'
# .

MainModuleTopicHosts = main_module_topic_registry.register(
    MainModuleTopic(
        name="hosts",
        title=_l("Hosts"),
        icon_name="topic_hosts",
        sort_index=10,
    )
)

MainModuleTopicServices = main_module_topic_registry.register(
    MainModuleTopic(
        name="services",
        title=_l("Services"),
        icon_name="topic_services",
        sort_index=20,
    )
)

MainModuleTopicBI = main_module_topic_registry.register(
    MainModuleTopic(
        name="bi",
        title=_l("Business Intelligence"),
        icon_name="topic_bi",
        sort_index=30,
    )
)

MainModuleTopicAgents = main_module_topic_registry.register(
    MainModuleTopic(
        name="agents",
        title=_l("Agents"),
        icon_name="topic_agents",
        sort_index=40,
    )
)

MainModuleTopicEvents = main_module_topic_registry.register(
    MainModuleTopic(
        name="events",
        title=_l("Events"),
        icon_name="topic_events",
        sort_index=50,
    )
)

MainModuleTopicUsers = main_module_topic_registry.register(
    MainModuleTopic(
        name="users",
        title=_l("Users"),
        icon_name="topic_users",
        sort_index=60,
    )
)

MainModuleTopicGeneral = main_module_topic_registry.register(
    MainModuleTopic(
        name="general",
        title=_l("General"),
        icon_name="topic_general",
        sort_index=70,
    )
)

MainModuleTopicMaintenance = main_module_topic_registry.register(
    MainModuleTopic(
        name="maintenance",
        title=_l("Maintenance"),
        icon_name="topic_maintenance",
        sort_index=80,
    )
)

MainModuleTopicExporter = main_module_topic_registry.register(
    MainModuleTopic(
        name="exporter",
        title=_l("Exporter"),
        icon_name="topic_exporter",
        sort_index=150,
    )
)
