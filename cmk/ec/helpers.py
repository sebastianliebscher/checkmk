#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.
from __future__ import annotations

import threading
from logging import Logger
from types import TracebackType
from typing import Callable, Literal, TypeAlias, TypeVar

# Our tokens are bytes, so we use a memoryview as a stream of bytes.
Tokens: TypeAlias = memoryview

# No error reporting, we just state that we failed.
Failure = None
FailureType: TypeAlias = None

# The result of the parser is the value it parsed + the still unparsed tokens.
T = TypeVar("T")
ParseResult: TypeAlias = tuple[T | FailureType, Tokens]

# It would be nice if we could reuse this for defs, but Python is too restricted for this.
Parser = Callable[[Tokens], ParseResult[T]]


def parse_bytes(length: int, tokens: Tokens) -> ParseResult[bytes]:
    msg = tokens[:length]
    if len(msg) != length:
        return Failure, tokens
    return bytes(msg), tokens[length:]


def parse_one_of(expected: bytes, tokens: Tokens) -> ParseResult[bytes]:
    byte, rest = parse_bytes(1, tokens)
    if byte is Failure or byte not in expected:
        return Failure, tokens
    return byte, rest


# Shorter: partial(parse_one_of, b"0123456789")
def parse_digit(tokens: Tokens) -> ParseResult[bytes]:
    return parse_one_of(b"0123456789", tokens)


def zero_or_more(parser: Parser[T], tokens: Tokens) -> ParseResult[list[T]]:
    result: list[T] = []
    while True:
        value, tokens = parser(tokens)
        if value is Failure:
            return result, tokens
        result.append(value)


def parse_msg_len(tokens: Tokens) -> ParseResult[int]:
    digit, rest1 = parse_one_of(b"123456789", tokens)
    if digit is Failure:
        return Failure, tokens
    digits, rest2 = zero_or_more(parse_digit, rest1)
    if digits is Failure:
        return Failure, tokens
    spc, rest3 = parse_one_of(b" ", rest2)
    if spc is Failure:
        return Failure, tokens
    return int(b"".join([digit] + digits)), rest3


def parse_non_transparent_frame(tokens: Tokens) -> ParseResult[bytes]:
    for i, b in enumerate(tokens):
        if b == ord(b"\n"):
            return bytes(tokens[:i]), tokens[i + 1 :]
    return Failure, tokens


def parse_syslog_message(tokens: Tokens) -> ParseResult[bytes]:
    msg_len, rest1 = parse_msg_len(tokens)
    if msg_len is Failure:
        return parse_non_transparent_frame(tokens)
    msg, rest2 = parse_bytes(msg_len, rest1)
    if msg is Failure:
        return Failure, tokens
    return msg, rest2


class ECLock:
    def __init__(self, logger: Logger) -> None:
        self._logger = logger
        self._lock = threading.Lock()

    def __enter__(self) -> None:
        self._logger.debug("[%s] Trying to acquire lock", threading.current_thread().name)
        self._lock.acquire()
        self._logger.debug("[%s] Acquired lock", threading.current_thread().name)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        self._logger.debug("[%s] Releasing lock", threading.current_thread().name)
        self._lock.release()
        return False  # Do not swallow exceptions
