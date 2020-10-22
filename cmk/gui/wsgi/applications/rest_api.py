#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.
import json
import io
import logging
import shutil
import urllib.parse
from typing import Dict, Type, TextIO

import yaml
from werkzeug import Response
from werkzeug.exceptions import HTTPException

from werkzeug.routing import Map, Submount, Rule

from cmk.gui import config
from cmk.gui.exceptions import MKUserError, MKAuthException
from cmk.gui.openapi import ENDPOINT_REGISTRY
from cmk.gui.plugins.openapi.utils import problem, ProblemException
from cmk.gui.wsgi.auth import verify_user, bearer_auth
from cmk.gui.wsgi.middleware import with_context_middleware, OverrideRequestMethod
from cmk.gui.wsgi.wrappers import ParameterDict
from cmk.utils import paths, crash_reporting
from cmk.utils.exceptions import MKException

ARGS_KEY = 'CHECK_MK_REST_API_ARGS'

logger = logging.getLogger('cmk.gui.wsgi.rest_api')

EXCEPTION_STATUS: Dict[Type[Exception], int] = {
    MKUserError: 400,
    MKAuthException: 401,
}


def spec_file() -> TextIO:
    spec_buffer = io.StringIO()
    with open(openapi_spec_dir() + "/checkmk.yaml", "r") as yaml_file:
        shutil.copyfileobj(yaml_file, spec_buffer)
    spec_buffer.seek(0)
    return spec_buffer


def openapi_spec_dir():
    return paths.web_dir + "/htdocs/openapi"


def serve_content(file_handle: TextIO, content_type):
    file_handle.seek(0)
    content = file_handle.read()

    resp = Response()
    resp.content_type = content_type
    resp.status_code = 200
    resp.data = content
    resp.freeze()

    return resp


def json_file(file_handle: TextIO) -> TextIO:
    """

    >>> yf = io.StringIO("data:\\n  foo:\\n  - bar\\n")
    >>> json_file(yf).read()
    '{"data": {"foo": ["bar"]}}'

    Args:
        file_handle:

    Returns:

    """
    file_handle.seek(0)
    data = yaml.safe_load(file_handle)
    buffer = io.StringIO()
    json.dump(data, buffer)
    buffer.seek(0)
    return buffer


class Authenticate:
    """Wrap an Endpoint so it will be authenticated

    This is not very memory efficient as it wraps every individual endpoint in its own
    authenticator, even though this does not need to be. This has to be done this way right now,
    because we have multiple endpoints without authentication in this app. A refactoring to lower
    the memory foot-print of this is feasible and should be done if a good way has been found.
    """
    def __init__(self, func):
        self.func = func

    def __call__(self, environ, start_response):
        path_args = environ[ARGS_KEY]
        auth_header = environ.get('HTTP_AUTHORIZATION', '')
        try:
            rfc7662 = bearer_auth(auth_header)
        except MKException as exc:
            return problem(
                status=401,
                title=str(exc),
                ext={'auth_header': auth_header},
            )(environ, start_response)

        with verify_user(rfc7662['sub'], rfc7662):
            wsgi_app = self.func(ParameterDict(path_args))
            return wsgi_app(environ, start_response)


class CheckmkRESTAPI:
    def __init__(self, debug: bool = False):
        self.debug = debug
        # TODO: Add resources for swagger-ui and json/yaml endpoints.
        # TODO: Add redoc.js endpoint.
        rules = []
        for endpoint in ENDPOINT_REGISTRY:
            if self.debug:
                # This helps us to make sure we can always generate a valid OpenAPI yaml file.
                _ = endpoint.to_operation_dict()

            rules.append(
                Rule(endpoint.default_path,
                     methods=[endpoint.method],
                     endpoint=Authenticate(endpoint.wrapped)))

        spec_file_buffer = spec_file()
        self.url_map = Map([
            Submount(
                "/<path:_path>",
                [
                    #Rule("/ui/<path:file>", endpoint=ServeFile),
                    #Rule("/doc/<path:file>", endpoint=ServeFile),
                    Rule(
                        "/openapi.yaml",
                        endpoint=serve_content(
                            file_handle=spec_file_buffer,
                            content_type='application/x-yaml; charset=utf-8',
                        ),
                    ),
                    Rule(
                        "/openapi.json",
                        endpoint=serve_content(
                            file_handle=json_file(spec_file_buffer),
                            content_type='application/json',
                        ),
                    ),
                    *rules
                ],
            ),
        ])
        self.wsgi_app = with_context_middleware(OverrideRequestMethod(self._wsgi_app))

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)

    def _wsgi_app(self, environ, start_response):
        urls = self.url_map.bind_to_environ(environ)
        try:
            wsgi_app, path_args = urls.match()

            # Remove this again (see Submount above), so the validators don't go crazy.
            del path_args['_path']

            # This is an implicit dependency, as we only know the args at runtime, but the
            # function at setup-time.
            environ[ARGS_KEY] = path_args
            return wsgi_app(environ, start_response)
        except ProblemException as exc:
            # ProblemException is derived from HTTPException, so we have to catch it first.
            return exc.to_problem()(environ, start_response)
        except HTTPException as e:
            # We don't want to log explicit HTTPExceptions as these are intentional.
            # HTTPExceptions are WSGI apps
            return e(environ, start_response)
        except MKException as exc:
            if self.debug:
                raise

            return problem(
                status=EXCEPTION_STATUS.get(type(exc), 500),
                title=str(exc),
                detail="An exception occurred.",
            )(environ, start_response)
        except Exception as exc:
            crash = APICrashReport.from_exception()
            crash_reporting.CrashReportStore().save(crash)
            logger.exception("Unhandled exception (Crash-ID: %s)", crash.ident_to_text())
            if self.debug:
                raise

            crash_url = f"/{config.omd_site()}/check_mk/crash.py?" + urllib.parse.urlencode([
                ("crash_id", crash.ident_to_text()),
                ("site", config.omd_site()),
            ],)

            return problem(status=EXCEPTION_STATUS.get(type(exc), 500),
                           title=str(exc),
                           detail="An internal error occured while processing your request.",
                           ext={
                               'crash_report': {
                                   'href': crash_url,
                                   'method': 'get',
                                   'rel': 'cmk/crash-report',
                                   'type': 'text/html',
                               },
                               'crash_id': crash.ident_to_text(),
                           })(environ, start_response)


class APICrashReport(crash_reporting.ABCCrashReport):
    """API specific crash reporting class.
    """
    @classmethod
    def type(cls):
        return "rest_api"
