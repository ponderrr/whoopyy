#!/usr/bin/env python3
"""
Read-only live check of whoopyy against your own WHOOP account.

Signs in to WHOOP in your browser with your own developer app, calls every
read endpoint the SDK wraps once (GET only), and checks each raw response
against the whoopyy model that parses it. Nothing is ever written to your
WHOOP account: the API client refuses any request that is not a GET, and
``revoke_access()`` is never called.

For every endpoint the check records whether the response validated (and,
if not, the field path and error type), fields the API sent that the model
does not declare (pydantic drops them silently), null and absent counts per
field, the JSON types seen (and any that differ from the type the model
declares, which pydantic only accepts by coercing them), how ``next_token``
looks on the last page of a collection, and the ``X-RateLimit-*`` response
headers.

The single-record endpoints are called with an ID taken from the collection
pages, preferring a completed, scored record so that the score objects are
validated too.

Usage:
    export WHOOP_CLIENT_ID=...
    export WHOOP_CLIENT_SECRET=...
    python scripts/live_check.py [--days 14] [--out DIR] [--token-file PATH]
                                 [--port 8080] [--keep-token]

Outputs (``--out``, default ``~/Projects/whoop-research/live-check-<YYYYmmdd-HHMMSS>``):
    shape_report.json  Field names, JSON types, null/absent counts, record
                       counts, validation error paths and anomalies. It holds
                       no values from your account, so it is safe to share.
    raw/*.json         The raw responses, mode 0600 in a 0700 directory. This
                       is your personal health data: do not share or commit it.

``--out`` may not be inside this repository or any other git working tree.

Tokens are stored in a temporary file (never ``~/.whoop_tokens.json``) that
is deleted when the check ends, also on Ctrl-C, SIGTERM or SIGHUP (closing
the terminal), unless ``--keep-token`` is passed. Tokens are never printed.

Exit codes:
    0  Every endpoint was called and returned data that validated. Only
       ``get_workout`` and ``get_activity_mapping`` may be skipped, when the
       window has no workout or no record with a legacy ``v1_id``.
    1  At least one endpoint failed: an HTTP or validation error, a
       pagination key the SDK does not read, or a required endpoint that
       could not be called because the window had no usable record (try a
       larger ``--days``). Also returned when sign-in fails.
    2  The check did not run (missing credentials, bad arguments, unsafe
       ``--out`` or ``--token-file``).
    130, 143, 129
       Interrupted by Ctrl-C, SIGTERM or SIGHUP. The temporary token file
       is still deleted, and ``--out`` is removed if nothing was written.
"""

import argparse
import functools
import json
import logging
import os
import platform
import re
import shutil
import signal
import sys
import tempfile
import threading
import types
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterator,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
    get_args,
    get_origin,
)
from urllib.parse import urlparse
from uuid import UUID

import httpx
from pydantic import AliasChoices, AliasPath, BaseModel, ValidationError

try:
    import whoopyy
    from whoopyy import WhoopClient
    from whoopyy.constants import ENDPOINTS, MAX_PAGE_LIMIT, SCOPES
    from whoopyy.exceptions import WhoopError
    from whoopyy.models import (
        ActivityIdMapping,
        BodyMeasurement,
        Cycle,
        CycleCollection,
        Recovery,
        RecoveryCollection,
        Sleep,
        SleepCollection,
        UserProfileBasic,
        Workout,
        WorkoutCollection,
    )
except ImportError:  # pragma: no cover - depends on the environment
    sys.stderr.write(
        "live_check.py needs whoopyy to be importable. From the repository "
        "root run:\n    pip install -e .\n"
    )
    raise SystemExit(2)

__all__ = ["main", "run_checks", "Recorder", "ReadOnlyViolation", "RequestLimitReached"]

# =============================================================================
# Constants
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
"""Root of the whoopyy checkout this script lives in."""

DEFAULT_OUT_PARENT = Path("~") / "Projects" / "whoop-research"
"""Parent directory of the default ``--out`` (expanded at run time)."""

DEFAULT_DAYS = 14
DEFAULT_PORT = 8080
MAX_DAYS = 3650

MAX_REQUESTS_PER_ENDPOINT = 400
"""Safety limit on requests per endpoint check (guards against next_token loops)."""

SHAPE_REPORT_NAME = "shape_report.json"
RAW_DIR_NAME = "raw"
SHAPE_REPORT_VERSION = 1

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NOT_RUN = 2

STATUS_OK = "ok"
STATUS_FAIL = "fail"
STATUS_SKIPPED = "skipped"

RATE_LIMIT_HEADERS = (
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
    "Retry-After",
)
"""Response headers copied into the shape report (they hold no personal data)."""

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")

_SAFE_MESSAGE_ERROR_TYPES = frozenset({
    "bool_parsing",
    "bool_type",
    "date_parsing",
    "date_type",
    "datetime_from_date_parsing",
    "datetime_parsing",
    "datetime_type",
    "dict_type",
    "enum",
    "extra_forbidden",
    "finite_number",
    "float_parsing",
    "float_type",
    "greater_than",
    "greater_than_equal",
    "int_from_float",
    "int_parsing",
    "int_type",
    "less_than",
    "less_than_equal",
    "list_type",
    "literal_error",
    "missing",
    "model_attributes_type",
    "model_type",
    "none_required",
    "string_too_long",
    "string_too_short",
    "string_type",
    "too_long",
    "too_short",
})
"""
Pydantic error types whose built-in message never echoes the input value.

Messages of any other type (custom validators, UUID parsing, union tags)
can quote the offending value, so the shape report leaves them out.
"""

_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
_DATETIME_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?P<tz>Z|[+-]\d{2}:?\d{2})?"
)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TZ_OFFSET_RE = re.compile(r"[+-]\d{2}:\d{2}")
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_INTEGER_STRING_RE = re.compile(r"[+-]?\d+")
_DECIMAL_STRING_RE = re.compile(r"[+-]?\d+\.\d+")
_ENUM_LIKE_RE = re.compile(r"[A-Z][A-Z0-9_]*")
_FIELD_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}")
_VALUE_LIKE_FORMATS = ("uuid", "date", "tz-offset", "email", "integer-string", "decimal-string")

_SCALAR_JSON_TYPES: Tuple[Tuple[type, FrozenSet[str]], ...] = (
    (bool, frozenset({"boolean"})),  # before int: bool is an int subclass
    (int, frozenset({"integer"})),
    (float, frozenset({"integer", "number"})),
    (str, frozenset({"string"})),
    (datetime, frozenset({"string"})),
    (date, frozenset({"string"})),
    (dt_time, frozenset({"string"})),
    (UUID, frozenset({"string"})),
)
"""JSON types each Python field type accepts without pydantic's lax coercion."""

_UNION_TYPE: Any = getattr(types, "UnionType", None)
"""``types.UnionType`` (``X | Y`` annotations) on Python 3.10+, else None."""

_TERMINATION_SIGNALS = ("SIGTERM", "SIGHUP")
"""Signals treated like Ctrl-C while the check runs, so the token file is removed."""

_INTERRUPT_SIGNALS = ("SIGINT",) + _TERMINATION_SIGNALS
"""Signals ignored while the token file is being cleaned up."""


class ReadOnlyViolation(RuntimeError):
    """Raised when anything tries to send a non-GET request to the WHOOP API."""


class RequestLimitReached(RuntimeError):
    """Raised when one endpoint check exceeds ``MAX_REQUESTS_PER_ENDPOINT``."""


class _SetupError(Exception):
    """A problem with the arguments or environment; the check does not run."""


class _Terminated(KeyboardInterrupt):
    """
    Raised by the SIGTERM/SIGHUP handler so the Ctrl-C cleanup path runs.

    Attributes:
        signum: The signal that was received.
    """

    def __init__(self, signum: int) -> None:
        """
        Initialize with the received signal.

        Args:
            signum: Signal number.
        """
        super().__init__(signum)
        self.signum = signum


# =============================================================================
# Request recording
# =============================================================================

@dataclass
class Exchange:
    """
    One HTTP request/response pair seen by the API client.

    Request headers (which carry the bearer token) are never stored.

    Attributes:
        seq: 1-based order in which the response arrived.
        label: Endpoint check that was running when the request was sent.
        method: HTTP method.
        path: URL path (may contain record IDs; private).
        query: Query parameters (may contain dates and tokens; private).
        status: HTTP status code.
        headers: Response headers except ``Set-Cookie`` (private).
        rate_limit: The ``RATE_LIMIT_HEADERS`` present on the response.
        body: Parsed JSON body, or None when the body is not JSON.
        is_json: Whether the body parsed as JSON.
        text: Raw body text when it is not JSON (private).
    """

    seq: int
    label: str
    method: str
    path: str
    query: Dict[str, str]
    status: int
    headers: Dict[str, str]
    rate_limit: Dict[str, str]
    body: Any = None
    is_json: bool = False
    text: str = ""

    @property
    def ok(self) -> bool:
        """True for a 2xx response with a JSON body."""
        return 200 <= self.status < 300 and self.is_json


class Recorder:
    """
    httpx event hooks that keep every raw response and block non-GET requests.

    Example:
        >>> recorder = Recorder()
        >>> with recorder.labelled("profile"):
        ...     client.get_profile_basic()
        >>> recorder.documents("profile")
        [{'user_id': ..., ...}]
    """

    def __init__(self, max_requests_per_label: int = MAX_REQUESTS_PER_ENDPOINT) -> None:
        """
        Initialize an empty recorder.

        Args:
            max_requests_per_label: Requests allowed per label before
                ``RequestLimitReached`` is raised.
        """
        self.exchanges: List[Exchange] = []
        self.blocked_methods: List[str] = []
        self.max_requests_per_label = max_requests_per_label
        self._requests: Dict[str, int] = {}
        self._label = "unlabelled"

    @contextmanager
    def labelled(self, label: str) -> Iterator[None]:
        """
        Attribute every response received inside the block to ``label``.

        Args:
            label: Endpoint check name.

        Yields:
            None.
        """
        previous = self._label
        self._label = label
        try:
            yield
        finally:
            self._label = previous

    def on_request(self, request: httpx.Request) -> None:
        """
        Request hook: refuse anything that is not a GET.

        Args:
            request: Outgoing request.

        Raises:
            ReadOnlyViolation: If the method is not GET.
            RequestLimitReached: If the current label has used up its requests.
        """
        method = request.method.upper()
        if method != "GET":
            self.blocked_methods.append(method)
            raise ReadOnlyViolation(
                f"live_check is read-only and refused a {method} request"
            )
        sent = self._requests.get(self._label, 0)
        if sent >= self.max_requests_per_label:
            raise RequestLimitReached(
                f"stopped after {sent} requests (safety limit)"
            )
        self._requests[self._label] = sent + 1

    def on_response(self, response: httpx.Response) -> None:
        """
        Response hook: read the body and keep a copy of the exchange.

        Args:
            response: Incoming response.
        """
        response.read()
        request = response.request
        body: Any = None
        is_json = False
        text = ""
        try:
            body = response.json()
            is_json = True
        except ValueError:
            text = response.text
        rate_limit: Dict[str, str] = {}
        for name in RATE_LIMIT_HEADERS:
            value = response.headers.get(name)
            if value is not None:
                rate_limit[name] = value
        self.exchanges.append(
            Exchange(
                seq=len(self.exchanges) + 1,
                label=self._label,
                method=request.method.upper(),
                path=request.url.path,
                query=dict(request.url.params),
                status=response.status_code,
                headers={
                    key: value
                    for key, value in response.headers.items()
                    if key.lower() != "set-cookie"
                },
                rate_limit=rate_limit,
                body=body,
                is_json=is_json,
                text=text,
            )
        )

    def for_label(self, label: str) -> List[Exchange]:
        """Return every exchange recorded under ``label``."""
        return [ex for ex in self.exchanges if ex.label == label]

    def documents(self, label: str) -> List[Any]:
        """Return the JSON bodies of the 2xx responses recorded under ``label``."""
        return [ex.body for ex in self.for_label(label) if ex.ok]

    def page_count(self, label: str) -> int:
        """Return how many 2xx JSON responses were recorded under ``label``."""
        return len(self.documents(label))

    def records(self, label: str) -> List[Dict[str, Any]]:
        """Return the raw ``records`` items of every page recorded under ``label``."""
        found: List[Dict[str, Any]] = []
        for doc in self.documents(label):
            items = doc.get("records") if isinstance(doc, dict) else None
            if isinstance(items, list):
                found.extend(item for item in items if isinstance(item, dict))
        return found


def install_recorder(
    client: WhoopClient,
    recorder: Recorder,
    transport: Optional[httpx.BaseTransport] = None,
) -> None:
    """
    Route the client's API traffic through ``recorder``'s event hooks.

    Replaces ``client._http_client`` with an equivalent ``httpx.Client`` that
    carries the hooks. OAuth token requests use a separate client and are
    not recorded.

    Args:
        client: Client to instrument.
        recorder: Recorder that receives the hooks.
        transport: Transport to send requests with. None uses httpx's default
            network transport; tests pass an ``httpx.MockTransport``.
    """
    previous = client._http_client
    client._http_client = httpx.Client(
        base_url=previous.base_url,
        timeout=previous.timeout,
        headers=previous.headers,
        transport=transport,
        event_hooks={
            "request": [recorder.on_request],
            "response": [recorder.on_response],
        },
    )
    previous.close()


# =============================================================================
# Endpoint checks
# =============================================================================

@dataclass
class EndpointCheck:
    """
    One read endpoint to call and validate.

    Attributes:
        name: Short endpoint name used in reports and raw file names.
        sdk_call: The SDK method that is exercised.
        http: Method and path template (no IDs).
        model: whoopyy model that parses one raw response document.
        collection: Whether the endpoint is a paginated collection.
        record_key: Field that identifies a collection record (duplicate check).
        required: Whether a skip fails the check. False only for endpoints
            whose input can legitimately be missing from an account (no
            workout, no legacy v1 ID).
        skip_reason: Why the endpoint was not called, if it was not.
        sdk_exception: Exception the SDK call raised, if any.
        notes: Value-free observations made while calling the endpoint.
    """

    name: str
    sdk_call: str
    http: str
    model: Type[BaseModel]
    collection: bool = False
    record_key: Optional[str] = None
    required: bool = True
    skip_reason: Optional[str] = None
    sdk_exception: Optional[BaseException] = None
    notes: List[str] = field(default_factory=list)


def _call(
    check: EndpointCheck,
    recorder: Recorder,
    fetch: Callable[[], Any],
    expect: Optional[Tuple[str, Any]] = None,
) -> None:
    """
    Call one single-document SDK method, recording its response and outcome.

    Args:
        check: Endpoint being checked.
        recorder: Recorder that captures the raw response.
        fetch: Zero-argument callable that makes the SDK call.
        expect: Optional ``(field, value)`` the returned document should carry,
            e.g. the requested ID. A mismatch is noted, not printed.
    """
    with recorder.labelled(check.name):
        try:
            fetch()
        except Exception as exc:  # every failure is reported, none is fatal
            check.sdk_exception = exc
    if expect is None:
        return
    docs = recorder.documents(check.name)
    key, value = expect
    if docs and isinstance(docs[-1], dict) and not _same_id(docs[-1].get(key), value):
        check.notes.append(f"returned {key} differs from the requested one")


def _same_id(returned: Any, requested: Any) -> bool:
    """
    Compare a returned ID with the requested one, ignoring JSON type.

    A cycle ID sent as the string ``"123"`` names the same record as the
    integer 123; the type difference is reported as a type mismatch instead.
    """
    if returned == requested:
        return True
    if returned is None or requested is None or isinstance(returned, (dict, list)):
        return False
    return str(returned).strip() == str(requested).strip()


def _next_token(doc: Any) -> Optional[str]:
    """Return a usable next_token from a raw page, or None."""
    token = doc.get("next_token") if isinstance(doc, dict) else None
    return token if isinstance(token, str) and token else None


def _collect(
    check: EndpointCheck,
    recorder: Recorder,
    client: WhoopClient,
    iterate: Callable[..., Iterator[Any]],
    endpoint_key: str,
    start: datetime,
) -> None:
    """
    Read every page of a collection through the SDK's ``iter_*`` method.

    If the SDK raises a validation error on a page, the remaining pages are
    still fetched (GET, unvalidated) using the raw ``next_token``, so the
    whole window is checked.

    Args:
        check: Endpoint being checked.
        recorder: Recorder that captures the raw pages.
        client: Authenticated client.
        iterate: The SDK iterator, e.g. ``client.iter_cycles``.
        endpoint_key: ``ENDPOINTS`` key for the collection path.
        start: Start of the window.
    """
    with recorder.labelled(check.name):
        try:
            for _ in iterate(start=start):
                pass
        except ValidationError as exc:
            check.sdk_exception = exc
            _continue_unvalidated(check, recorder, client, endpoint_key, start)
        except Exception as exc:  # every failure is reported, none is fatal
            check.sdk_exception = exc


def _continue_unvalidated(
    check: EndpointCheck,
    recorder: Recorder,
    client: WhoopClient,
    endpoint_key: str,
    start: datetime,
) -> None:
    """Fetch the pages after the one the SDK failed to parse (GET only)."""
    docs = recorder.documents(check.name)
    token = _next_token(docs[-1]) if docs else None
    if token is None:
        return
    seen: Set[str] = set()
    while token is not None and token not in seen:
        seen.add(token)
        params = client._build_collection_params(MAX_PAGE_LIMIT, start, None, token)
        try:
            data = client._request("GET", ENDPOINTS[endpoint_key], params=params)
        except RequestLimitReached as exc:
            check.notes.append(str(exc))
            return
        except Exception as exc:  # report and stop paginating
            check.notes.append(f"could not fetch the remaining pages ({type(exc).__name__})")
            return
        token = _next_token(data)
    check.notes.append("later pages fetched raw after the SDK error")


def _int_id(value: Any) -> Optional[int]:
    """
    Return a raw ID as a positive int, or None if it cannot be one.

    Digit strings are accepted, as the SDK models accept them (pydantic lax
    mode), so an API that sends int64 IDs as strings is still exercised.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and _INTEGER_STRING_RE.fullmatch(value.strip()):
        value = int(value.strip())
    if isinstance(value, int) and value > 0:
        return value
    return None


def _uuid_like_id(value: Any) -> Optional[str]:
    """Return a raw ID if it is a non-empty, non-numeric string, else None."""
    if isinstance(value, str) and value.strip() and not value.strip().isdigit():
        return value
    return None


def _has_score(record: Mapping[str, Any]) -> bool:
    """True if a raw record carries a ``score`` object (it is SCORED)."""
    return isinstance(record.get("score"), dict)


def _is_closed(record: Mapping[str, Any]) -> bool:
    """True if a raw cycle has ended (the current cycle has no ``end``)."""
    return record.get("end") is not None


def _is_main_sleep(record: Mapping[str, Any]) -> bool:
    """True if a raw sleep is a main sleep rather than a nap."""
    return record.get("nap") is False


def _pick(
    records: Sequence[Mapping[str, Any]],
    key: str,
    parse: Callable[[Any], Optional[Any]],
    preferences: Sequence[Callable[[Mapping[str, Any]], bool]] = (),
) -> Tuple[Optional[Any], Optional[Mapping[str, Any]]]:
    """
    Choose the ID to call a single-record endpoint with.

    Records matching the earlier ``preferences`` come first (the newest
    record is usually the open, unscored current cycle, which would leave
    the score models unchecked); within a rank the API's order is kept.

    Args:
        records: Raw collection records.
        key: Field holding the ID.
        parse: Turns a raw value into a usable ID, or None.
        preferences: Predicates in priority order.

    Returns:
        ``(id, record)``, or ``(None, None)`` if no record has a usable ID.
    """
    ranked = sorted(records, key=lambda record: tuple(not pref(record) for pref in preferences))
    for record in ranked:
        value = parse(record.get(key))
        if value is not None:
            return value, record
    return None, None


def _no_id_reason(
    collection: EndpointCheck,
    records: Sequence[Mapping[str, Any]],
    noun: str,
    wanted: str,
) -> str:
    """Explain, without values, why no ID could be taken from a collection."""
    if records:
        return f"no {noun} in the window has {wanted}"
    if collection.sdk_exception is not None:
        return f"{collection.name} failed, so there was no {noun} to request"
    return f"no {noun} in the window; try a larger --days"


def _note_unscored(check: EndpointCheck, record: Optional[Mapping[str, Any]]) -> None:
    """Note that the score model goes unchecked when only unscored records exist."""
    if record is not None and not _has_score(record):
        check.notes.append("no scored record in the window, so score was not checked")


def run_checks(client: WhoopClient, recorder: Recorder, days: int) -> List[EndpointCheck]:
    """
    Call every read endpoint once (GET only) and record the raw responses.

    IDs for the single-record endpoints come from the raw collection pages,
    so a collection that fails validation does not stop the later checks.
    Completed, scored records are preferred so the score models are checked
    too. ``revoke_access()`` and every other write are never called.

    Args:
        client: Authenticated client instrumented with ``install_recorder``.
        recorder: Recorder installed on the client.
        days: Size of the collection window in days, ending now.

    Returns:
        The endpoint checks in call order.
    """
    start = datetime.now(timezone.utc) - timedelta(days=days)
    window = f"start=now-{days}d"
    checks: List[EndpointCheck] = []

    def add(check: EndpointCheck) -> EndpointCheck:
        checks.append(check)
        return check

    def http(key: str) -> str:
        return f"GET {ENDPOINTS[key]}"

    # --- User ---------------------------------------------------------------
    profile = add(EndpointCheck(
        "profile", "get_profile_basic()", http("user_profile_basic"), UserProfileBasic,
    ))
    _call(profile, recorder, client.get_profile_basic)

    body = add(EndpointCheck(
        "body_measurement", "get_body_measurement()", http("user_body_measurement"),
        BodyMeasurement,
    ))
    _call(body, recorder, client.get_body_measurement)

    # --- Cycles -------------------------------------------------------------
    cycles = add(EndpointCheck(
        "cycle_collection", f"iter_cycles({window})", http("cycle_collection"),
        CycleCollection, collection=True, record_key="id",
    ))
    _collect(cycles, recorder, client, client.iter_cycles, "cycle_collection", start)
    cycle_records = recorder.records(cycles.name)

    cycle = add(EndpointCheck("cycle", "get_cycle(cycle_id)", http("cycle_single"), Cycle))
    cycle_id, picked = _pick(cycle_records, "id", _int_id, (_has_score, _is_closed))
    if cycle_id is None:
        cycle.skip_reason = _no_id_reason(cycles, cycle_records, "cycle", "an integer id")
    else:
        _note_unscored(cycle, picked)
        _call(cycle, recorder, lambda: client.get_cycle(cycle_id), expect=("id", cycle_id))

    # --- Recovery -----------------------------------------------------------
    recoveries = add(EndpointCheck(
        "recovery_collection", f"iter_recovery({window})", http("recovery_collection"),
        RecoveryCollection, collection=True, record_key="cycle_id",
    ))
    _collect(recoveries, recorder, client, client.iter_recovery, "recovery_collection", start)
    recovery_records = recorder.records(recoveries.name)

    recovery = add(EndpointCheck(
        "recovery_for_cycle", "get_recovery_for_cycle(cycle_id)", http("recovery_for_cycle"),
        Recovery,
    ))
    recovery_cycle_id, picked = _pick(recovery_records, "cycle_id", _int_id, (_has_score,))
    if recovery_cycle_id is None:
        recovery.skip_reason = _no_id_reason(
            recoveries, recovery_records, "recovery", "an integer cycle_id",
        )
    else:
        _note_unscored(recovery, picked)
        _call(
            recovery, recorder,
            lambda: client.get_recovery_for_cycle(recovery_cycle_id),
            expect=("cycle_id", recovery_cycle_id),
        )

    # --- Sleep --------------------------------------------------------------
    sleeps = add(EndpointCheck(
        "sleep_collection", f"iter_sleep({window})", http("sleep_collection"),
        SleepCollection, collection=True, record_key="id",
    ))
    _collect(sleeps, recorder, client, client.iter_sleep, "sleep_collection", start)
    sleep_records = recorder.records(sleeps.name)

    sleep = add(EndpointCheck("sleep", "get_sleep(sleep_id)", http("sleep_single"), Sleep))
    sleep_id, picked = _pick(sleep_records, "id", _uuid_like_id, (_has_score, _is_main_sleep))
    if sleep_id is None:
        sleep.skip_reason = _no_id_reason(sleeps, sleep_records, "sleep", "a UUID id")
    else:
        _note_unscored(sleep, picked)
        _call(sleep, recorder, lambda: client.get_sleep(sleep_id), expect=("id", sleep_id))

    sleep_for_cycle = add(EndpointCheck(
        "sleep_for_cycle", "get_sleep_for_cycle(cycle_id)", http("sleep_for_cycle"), Sleep,
    ))
    # The endpoint returns the cycle's main sleep, so pick the cycle of a scored one.
    sleep_cycle_id, picked = _pick(
        sleep_records, "cycle_id", _int_id, (_is_main_sleep, _has_score),
    )
    if sleep_cycle_id is None:
        sleep_for_cycle.skip_reason = _no_id_reason(
            sleeps, sleep_records, "sleep", "an integer cycle_id",
        )
    else:
        _note_unscored(sleep_for_cycle, picked)
        _call(
            sleep_for_cycle, recorder,
            lambda: client.get_sleep_for_cycle(sleep_cycle_id),
            expect=("cycle_id", sleep_cycle_id),
        )

    # --- Workouts -----------------------------------------------------------
    workouts = add(EndpointCheck(
        "workout_collection", f"iter_workouts({window})", http("workout_collection"),
        WorkoutCollection, collection=True, record_key="id",
    ))
    _collect(workouts, recorder, client, client.iter_workouts, "workout_collection", start)
    workout_records = recorder.records(workouts.name)

    # Optional: an account can go a whole window without a workout.
    workout = add(EndpointCheck(
        "workout", "get_workout(workout_id)", http("workout_single"), Workout, required=False,
    ))
    workout_id, picked = _pick(workout_records, "id", _uuid_like_id, (_has_score,))
    if workout_id is None:
        workout.skip_reason = _no_id_reason(workouts, workout_records, "workout", "a UUID id")
    else:
        _note_unscored(workout, picked)
        _call(workout, recorder, lambda: client.get_workout(workout_id), expect=("id", workout_id))

    # --- Activity ID mapping (optional: only records from before v2 have a v1_id)
    mapping = add(EndpointCheck(
        "activity_mapping", "get_activity_mapping(activity_v1_id)", http("activity_mapping"),
        ActivityIdMapping, required=False,
    ))
    source = next(
        (
            record for record in sleep_records + workout_records
            if _int_id(record.get("v1_id")) is not None
        ),
        None,
    )
    if source is None:
        mapping.skip_reason = "no sleep or workout with a v1_id in the window"
    else:
        v1_id = _int_id(source.get("v1_id"))
        _call(
            mapping, recorder,
            lambda: client.get_activity_mapping(v1_id),
            expect=("v2_activity_id", source.get("id")),
        )

    return checks


# =============================================================================
# Shape analysis (value-free)
# =============================================================================

def _bump(counter: Dict[str, int], key: str, amount: int = 1) -> None:
    """Increment ``counter[key]``."""
    counter[key] = counter.get(key, 0) + amount


def _join(path: str, key: str) -> str:
    """Join a field path and a key with a dot."""
    return f"{path}.{key}" if path else key


def _json_type(value: Any) -> str:
    """Return the JSON type name of a decoded JSON value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _string_format(value: str) -> str:
    """Classify a string's format without keeping the string."""
    if value == "":
        return "empty"
    if value != value.strip():
        return "padded"
    if _UUID_RE.fullmatch(value):
        return "uuid"
    match = _DATETIME_RE.fullmatch(value)
    if match:
        tz = match.group("tz")
        if tz is None:
            return "date-time(no-tz)"
        return "date-time(Z)" if tz == "Z" else "date-time(offset)"
    if _DATE_RE.fullmatch(value):
        return "date"
    if _TZ_OFFSET_RE.fullmatch(value):
        return "tz-offset"
    if _EMAIL_RE.fullmatch(value):
        return "email"
    if _INTEGER_STRING_RE.fullmatch(value):
        return "integer-string"
    if _DECIMAL_STRING_RE.fullmatch(value):
        return "decimal-string"
    if _ENUM_LIKE_RE.fullmatch(value):
        return "enum-like"
    return "text"


def _safe_key(key: Any) -> str:
    """
    Return a JSON object key for use in a field path, masking value-like keys.

    WHOOP objects are keyed by field names, but a map keyed by IDs, dates or
    other data would otherwise put those values into the report.

    Args:
        key: JSON object key.

    Returns:
        The key itself if it looks like a field name, else a placeholder
        such as ``<uuid>`` or ``<key>``.
    """
    text = str(key)
    kind = _string_format(text)
    if kind in _VALUE_LIKE_FORMATS or kind.startswith("date-time"):
        return f"<{kind}>"
    if not _FIELD_NAME_RE.fullmatch(text):
        return "<key>"
    return text


class _ShapeStats:
    """Per-field presence, null counts, JSON types and string formats."""

    def __init__(self) -> None:
        self.objects: Dict[str, int] = {}
        self.fields: Dict[str, Dict[str, Any]] = {}
        self.parents: Dict[str, Optional[str]] = {}

    def add(self, value: Any, path: str = "") -> None:
        """Walk one decoded JSON value."""
        if isinstance(value, dict):
            _bump(self.objects, path)
            for key, child in value.items():
                child_path = _join(path, _safe_key(key))
                self._observe(child_path, path, child)
                self.add(child, child_path)
        elif isinstance(value, list):
            item_path = f"{path}[]"
            for item in value:
                self._observe(item_path, None, item)
                self.add(item, item_path)

    def _observe(self, path: str, parent: Optional[str], value: Any) -> None:
        entry = self.fields.setdefault(
            path, {"present": 0, "null": 0, "types": {}, "string_formats": {}},
        )
        self.parents.setdefault(path, parent)
        entry["present"] += 1
        if value is None:
            entry["null"] += 1
        _bump(entry["types"], _json_type(value))
        if isinstance(value, str):
            _bump(entry["string_formats"], _string_format(value))

    def report(self) -> Dict[str, Dict[str, Any]]:
        """Return the value-free field table, sorted by path."""
        table: Dict[str, Dict[str, Any]] = {}
        for path in sorted(self.fields):
            entry = self.fields[path]
            row: Dict[str, Any] = {"present": entry["present"]}
            parent = self.parents.get(path)
            if parent is not None:
                row["absent"] = self.objects.get(parent, 0) - entry["present"]
            row["null"] = entry["null"]
            row["types"] = dict(sorted(entry["types"].items()))
            if entry["string_formats"]:
                row["string_formats"] = dict(sorted(entry["string_formats"].items()))
            table[path] = row
        return table


def _alias_keys(info: Any) -> List[str]:
    """Return the JSON keys a pydantic field accepts through its aliases."""
    alias = info.validation_alias if info.validation_alias is not None else info.alias
    if alias is None:
        return []
    choices = alias.choices if isinstance(alias, AliasChoices) else [alias]
    keys: List[str] = []
    for choice in choices:
        if isinstance(choice, str):
            keys.append(choice)
        elif isinstance(choice, AliasPath) and choice.path and isinstance(choice.path[0], str):
            keys.append(choice.path[0])
    return keys


def _nested_model(annotation: Any) -> Optional[Type[BaseModel]]:
    """Return the model a field (or its list items / Optional) parses into."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation):
        found = _nested_model(arg)
        if found is not None:
            return found
    return None


def _expected_json_types(annotation: Any) -> Optional[FrozenSet[str]]:
    """
    Return the JSON types a field annotation accepts without coercion.

    Args:
        annotation: A pydantic field annotation.

    Returns:
        JSON type names as produced by ``_json_type`` (``float`` also takes
        ``integer``; ``Optional`` adds ``null``), or None when the annotation
        is not one this check knows, in which case it is not compared.
    """
    if annotation is type(None):
        return frozenset({"null"})
    origin = get_origin(annotation)
    if origin is Literal:
        return frozenset(_json_type(arg) for arg in get_args(annotation))
    if origin is Union or (_UNION_TYPE is not None and origin is _UNION_TYPE):
        found: Set[str] = set()
        for arg in get_args(annotation):
            part = _expected_json_types(arg)
            if part is None:
                return None
            found |= part
        return frozenset(found)
    kind = origin if origin is not None else annotation
    if not isinstance(kind, type):
        return None
    if issubclass(kind, (list, tuple, set, frozenset)):
        return frozenset({"array"})
    if issubclass(kind, (dict, BaseModel)):
        return frozenset({"object"})
    if origin is not None:
        return None
    for python_type, json_types in _SCALAR_JSON_TYPES:
        if issubclass(kind, python_type):
            return json_types
    return None


@functools.lru_cache(maxsize=None)
def _model_fields(
    model: Type[BaseModel],
) -> Tuple[
    Tuple[str, Tuple[str, ...], Optional[Type[BaseModel]], Optional[FrozenSet[str]]], ...
]:
    """
    Describe each declared field of ``model``.

    Returns:
        ``(field name, accepted JSON keys, nested model, expected JSON types)``
        per field.
    """
    config: Mapping[str, Any] = model.model_config
    by_name = bool(config.get("populate_by_name") or config.get("validate_by_name"))
    fields = []
    for name, info in model.model_fields.items():
        aliases = _alias_keys(info)
        keys = list(aliases)
        if not aliases or by_name:
            keys.insert(0, name)
        fields.append((
            name,
            tuple(dict.fromkeys(keys)),
            _nested_model(info.annotation),
            _expected_json_types(info.annotation),
        ))
    return tuple(fields)


def _walk_model(
    value: Any,
    model: Type[BaseModel],
    path: str,
    dropped: Dict[str, int],
    declared: Dict[str, int],
    mismatches: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    """
    Compare raw JSON with the model that parses it.

    Args:
        value: Decoded JSON (object, or list of objects).
        model: Model that parses ``value`` (or each of its items).
        path: Field path of ``value``.
        dropped: Receives a count per path of keys the model ignores.
        declared: Receives a count per declared field path of objects that
            carried the field (0 if the field was never present).
        mismatches: If given, receives per field path the JSON types seen
            that the declared type does not accept without coercion, e.g.
            a string for an ``int`` field: ``{"expected": [...], "types":
            {"string": 3}}``.
    """
    if isinstance(value, list):
        for item in value:
            _walk_model(item, model, f"{path}[]", dropped, declared, mismatches)
        return
    if not isinstance(value, dict):
        return
    known: Dict[str, Tuple[Optional[Type[BaseModel]], Optional[FrozenSet[str]]]] = {}
    for name, keys, nested, expected in _model_fields(model):
        field_path = _join(path, name)
        declared.setdefault(field_path, 0)
        if any(key in value for key in keys):
            declared[field_path] += 1
        for key in keys:
            known[key] = (nested, expected)
    config: Mapping[str, Any] = model.model_config
    ignores_extra = config.get("extra") in (None, "ignore")
    for key, child in value.items():
        child_path = _join(path, _safe_key(key))
        if key in known:
            nested, expected = known[key]
            seen = _json_type(child)
            if mismatches is not None and expected is not None and seen not in expected:
                found = mismatches.setdefault(
                    child_path, {"expected": sorted(expected), "types": {}},
                )
                _bump(found["types"], seen)
            if nested is not None and child is not None:
                _walk_model(child, nested, child_path, dropped, declared, mismatches)
        elif ignores_extra:
            _bump(dropped, child_path)


def _normalise_loc(loc: Sequence[Any]) -> str:
    """Turn a pydantic error location into a field path without indices."""
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += "[]"
        else:
            path = _join(path, _safe_key(part))
    return path


def _next_token_state(doc: Any) -> str:
    """Describe a page's next_token without keeping it."""
    if not isinstance(doc, dict) or "next_token" not in doc:
        return "absent"
    token = doc["next_token"]
    if token is None:
        return "null"
    if token == "":
        return "empty_string"
    return "string" if isinstance(token, str) else _json_type(token)


def _exception_note(exc: BaseException) -> str:
    """Describe an SDK exception without its message (which may hold IDs)."""
    name = type(exc).__name__
    if isinstance(exc, ReadOnlyViolation):
        return "blocked a non-GET request"
    if isinstance(exc, RequestLimitReached):
        return str(exc)
    if isinstance(exc, ValidationError):
        return "SDK raised ValidationError"
    status = getattr(exc, "status_code", None)
    if isinstance(exc, WhoopError) and status is not None:
        return f"HTTP {status} ({name})"
    return f"{name} raised"


def analyse_check(
    check: EndpointCheck, recorder: Recorder,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Build one endpoint's shape-report entry and its private error details.

    Args:
        check: Endpoint that was run (or skipped).
        recorder: Recorder holding its raw responses.

    Returns:
        ``(entry, private)``: ``entry`` holds only field names, types, counts
        and value-free notes; ``private`` holds full error messages and
        locations and is written to the raw directory only.
    """
    entry: Dict[str, Any] = {
        "sdk_call": f"WhoopClient.{check.sdk_call}",
        "http": check.http,
        "model": check.model.__name__,
    }
    private: Dict[str, Any] = {"endpoint": check.name}
    entry["required"] = check.required
    if check.skip_reason is not None:
        # A required endpoint that was never called has not been verified.
        notes = list(check.notes)
        if check.required:
            entry["status"] = STATUS_FAIL
            notes.insert(0, f"not verified: {check.skip_reason}")
        else:
            entry["status"] = STATUS_SKIPPED
        entry["skip_reason"] = check.skip_reason
        entry["notes"] = notes
        return entry, private

    exchanges = recorder.for_label(check.name)
    docs = [ex.body for ex in exchanges if ex.ok]
    statuses: Dict[str, int] = {}
    for ex in exchanges:
        _bump(statuses, str(ex.status))
    non_json = sum(1 for ex in exchanges if 200 <= ex.status < 300 and not ex.is_json)

    shape = _ShapeStats()
    dropped: Dict[str, int] = {}
    declared: Dict[str, int] = {}
    mismatches: Dict[str, Dict[str, Any]] = {}
    grouped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    private_errors: List[Dict[str, Any]] = []
    invalid_records: Set[Tuple[int, int]] = set()
    invalid_docs = 0
    record_count = 0
    record_keys: List[str] = []

    for index, doc in enumerate(docs):
        shape.add(doc)
        _walk_model(doc, check.model, "", dropped, declared, mismatches)
        try:
            check.model.model_validate(doc)
            errors: List[Any] = []
        except ValidationError as exc:
            errors = list(exc.errors(include_url=False))
        if errors:
            invalid_docs += 1
        for error in errors:
            loc = tuple(error.get("loc", ()))
            error_type = str(error.get("type", "unknown"))
            input_type = "absent" if error_type == "missing" else _json_type(error.get("input"))
            key = (_normalise_loc(loc), error_type, input_type)
            group = grouped.setdefault(key, {
                "path": key[0], "type": error_type, "input_type": input_type, "count": 0,
            })
            group["count"] += 1
            if error_type in _SAFE_MESSAGE_ERROR_TYPES:
                group.setdefault("message", str(error.get("msg", "")))
            private_errors.append({
                "document": index, "loc": list(loc), "type": error_type,
                "msg": str(error.get("msg", "")),
            })
            if (
                check.collection and len(loc) >= 2 and loc[0] == "records"
                and isinstance(loc[1], int)
            ):
                invalid_records.add((index, loc[1]))
        if check.collection:
            items = doc.get("records") if isinstance(doc, dict) else None
            if isinstance(items, list):
                record_count += len(items)
                if check.record_key is not None:
                    record_keys.extend(
                        str(item[check.record_key]) for item in items
                        if isinstance(item, dict) and item.get(check.record_key) is not None
                    )

    notes = list(check.notes)
    if check.sdk_exception is not None:
        notes.insert(0, _exception_note(check.sdk_exception))
        private["sdk_exception"] = {
            "type": type(check.sdk_exception).__name__,
            "message": str(check.sdk_exception),
        }
    if statuses.get("429"):
        notes.append(f"rate limited {statuses['429']}x (SDK waited and retried)")
    if non_json:
        notes.append(f"{non_json} 2xx response(s) without a JSON body")

    entry["requests"] = len(exchanges)
    entry["http_statuses"] = dict(sorted(statuses.items()))
    entry["documents"] = len(docs)
    if check.collection:
        entry["records"] = record_count
        entry["records_invalid"] = len(invalid_records)
        entry["records_valid"] = record_count - len(invalid_records)
    else:
        entry["records"] = len(docs)
        entry["records_invalid"] = invalid_docs
        entry["records_valid"] = len(docs) - invalid_docs
    if invalid_records:
        notes.append(f"{len(invalid_records)} invalid record(s)")

    validation_errors = sorted(grouped.values(), key=lambda g: (g["path"], g["type"]))
    entry["sdk_exception"] = (
        type(check.sdk_exception).__name__ if check.sdk_exception is not None else None
    )
    status_code = getattr(check.sdk_exception, "status_code", None)
    if isinstance(check.sdk_exception, WhoopError) and status_code is not None:
        entry["http_error_status"] = str(status_code)
    entry["validation_errors"] = validation_errors
    for group in validation_errors[:2]:
        notes.append(f"{group['path'] or '<document>'}: {group['type']}")
    if len(validation_errors) > 2:
        notes.append(f"+{len(validation_errors) - 2} more validation error path(s)")

    # Types the model accepted only by coercing them (paths that failed
    # validation are already reported above).
    error_paths = {group["path"] for group in validation_errors}
    entry["type_mismatches"] = [
        {
            "path": path,
            "expected": found["expected"],
            "types": dict(sorted(found["types"].items())),
        }
        for path, found in sorted(mismatches.items())
        if path not in error_paths
    ]
    for item in entry["type_mismatches"][:2]:
        notes.append(f"{item['path']} sent as {'/'.join(item['types'])}")
    if len(entry["type_mismatches"]) > 2:
        notes.append(f"+{len(entry['type_mismatches']) - 2} more type mismatch path(s)")

    field_table = shape.report()
    entry["dropped_fields"] = [
        {
            "path": path,
            "count": count,
            "types": field_table.get(path, {}).get("types", {}),
        }
        for path, count in sorted(dropped.items())
    ]
    # A top-level token key the model ignores means the SDK never sees the
    # API's next page, so it stops after page 1 without any error.
    ignored_pagination = [
        path for path in sorted(dropped)
        if check.collection and "." not in path and "[]" not in path
        and "token" in path.lower()
    ]
    entry["ignored_pagination_keys"] = ignored_pagination
    for path in ignored_pagination:
        notes.append(f"pagination key '{path}' is not read by the SDK, so it stops after page 1")
    entry["declared_never_present"] = sorted(
        path for path, count in declared.items() if count == 0
    )

    if check.collection:
        states = [_next_token_state(doc) for doc in docs]
        query_params: Set[str] = set()
        for ex in exchanges:
            query_params.update(ex.query.keys())
        tokens = [token for token in (_next_token(doc) for doc in docs) if token]
        pagination: Dict[str, Any] = {
            "pages": len(docs),
            "next_token_last_page": states[-1] if states else None,
            "next_token_other_pages": sorted(set(states[:-1])),
            "query_params": sorted(query_params),
            "repeated_next_token": len(tokens) != len(set(tokens)),
        }
        entry["pagination"] = pagination
        entry["duplicate_record_keys"] = len(record_keys) - len(set(record_keys))
        if states:
            notes.append(f"{len(docs)} page(s), last next_token {states[-1]}")
        if pagination["repeated_next_token"]:
            notes.append("API repeated a next_token")
        if entry["duplicate_record_keys"]:
            notes.append(f"{entry['duplicate_record_keys']} duplicate record(s) across pages")

    rate_limit: Dict[str, str] = {}
    for ex in exchanges:
        if ex.rate_limit:
            rate_limit = dict(ex.rate_limit)
    entry["rate_limit_headers"] = rate_limit
    entry["fields"] = field_table

    failed = (
        check.sdk_exception is not None
        or bool(validation_errors)
        or not docs
        or non_json > 0
        or bool(ignored_pagination)
    )
    entry["status"] = STATUS_FAIL if failed else STATUS_OK
    entry["notes"] = notes
    private["validation_errors"] = private_errors
    return entry, private


def build_reports(
    checks: Sequence[EndpointCheck], recorder: Recorder, days: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Build the shareable shape report and the private error details.

    Args:
        checks: Endpoint checks returned by ``run_checks``.
        recorder: Recorder holding the raw responses.
        days: Window size that was requested.

    Returns:
        ``(shape_report, private_errors)``.
    """
    endpoints: Dict[str, Any] = {}
    private: Dict[str, Any] = {}
    anomalies: List[str] = []
    for check in checks:
        entry, details = analyse_check(check, recorder)
        endpoints[check.name] = entry
        private[check.name] = details
        anomalies.extend(_anomalies(check.name, entry))

    counts = {STATUS_OK: 0, STATUS_FAIL: 0, STATUS_SKIPPED: 0}
    for entry in endpoints.values():
        counts[entry["status"]] += 1
    exit_code = EXIT_FAILED if counts[STATUS_FAIL] else EXIT_OK
    report: Dict[str, Any] = {
        "report": "whoopyy live check: response shapes",
        "schema_version": SHAPE_REPORT_VERSION,
        "privacy": (
            "Field names, JSON types, counts and value-free notes only. "
            "No IDs, names, timestamps or measurements from the account."
        ),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "whoopyy_version": whoopyy.__version__,
        "python_version": platform.python_version(),
        "window_days": days,
        "summary": {
            "endpoints": len(endpoints),
            "ok": counts[STATUS_OK],
            "fail": counts[STATUS_FAIL],
            "skipped": counts[STATUS_SKIPPED],
            "exit_code": exit_code,
        },
        "blocked_non_get_requests": len(recorder.blocked_methods),
        "anomalies": anomalies,
        "endpoints": endpoints,
    }
    return report, private


def _anomalies(name: str, entry: Mapping[str, Any]) -> List[str]:
    """Return the value-free anomaly lines for one endpoint entry."""
    if entry["status"] == STATUS_SKIPPED:
        return []
    if "skip_reason" in entry:
        return [f"{name}: not verified, {entry['skip_reason']}"]
    found: List[str] = []
    if entry.get("sdk_exception"):
        found.append(f"{name}: SDK call raised {entry['sdk_exception']}")
    for group in entry.get("validation_errors", []):
        found.append(
            f"{name}: {group['path'] or '<document>'} failed validation "
            f"({group['type']}, got {group['input_type']}) x{group['count']}"
        )
    ignored_pagination = entry.get("ignored_pagination_keys", [])
    for dropped in entry.get("dropped_fields", []):
        if dropped["path"] in ignored_pagination:
            found.append(
                f"{name}: pagination key {dropped['path']} is ignored by the SDK; "
                f"pages after the first are never fetched"
            )
            continue
        found.append(
            f"{name}: {dropped['path']} is not declared by {entry['model']} "
            f"and is dropped (x{dropped['count']})"
        )
    for item in entry.get("type_mismatches", []):
        seen = ", ".join(f"{kind} x{count}" for kind, count in item["types"].items())
        found.append(
            f"{name}: {item['path']} is declared {'/'.join(item['expected'])} but the "
            f"JSON had {seen} (accepted only by pydantic coercion)"
        )
    pagination = entry.get("pagination")
    if pagination:
        last = pagination.get("next_token_last_page")
        if last not in (None, "absent"):
            found.append(f"{name}: next_token on the last page is {last}")
        if pagination.get("repeated_next_token"):
            found.append(f"{name}: the API repeated a next_token")
    if entry.get("duplicate_record_keys"):
        found.append(f"{name}: {entry['duplicate_record_keys']} duplicate record(s)")
    for note in entry.get("notes", []):
        if "differs from the requested" in note or "without a JSON body" in note:
            found.append(f"{name}: {note}")
    return found


# =============================================================================
# Output
# =============================================================================

def _write_json(path: Path, payload: Any, mode: int) -> None:
    """
    Write JSON to a new file with an exact mode, refusing to overwrite.

    Args:
        path: File to create (must not exist).
        payload: JSON-serialisable data.
        mode: Permission bits, applied regardless of the umask.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags, mode)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, mode)
        else:  # pragma: no cover - Windows
            os.chmod(str(path), mode)
        handle = os.fdopen(fd, "w", encoding="utf-8")
    except BaseException:
        os.close(fd)
        raise
    with handle:
        json.dump(payload, handle, indent=2, default=str)
        handle.write("\n")


def write_outputs(
    out_dir: Path,
    raw_dir: Path,
    report: Mapping[str, Any],
    private: Mapping[str, Any],
    recorder: Recorder,
) -> None:
    """
    Write the shape report and the private raw responses.

    Args:
        out_dir: Output directory (already created, mode 0700).
        raw_dir: Raw directory inside it (already created, mode 0700).
        report: Shape report from ``build_reports``.
        private: Private error details from ``build_reports``.
        recorder: Recorder holding the raw responses.
    """
    for ex in recorder.exchanges:
        response: Dict[str, Any] = {"status": ex.status, "headers": ex.headers}
        if ex.is_json:
            response["json"] = ex.body
        else:
            response["text"] = ex.text
        _write_json(
            raw_dir / f"{ex.seq:03d}-{ex.label}.json",
            {
                "endpoint": ex.label,
                "request": {"method": ex.method, "path": ex.path, "query": ex.query},
                "response": response,
            },
            0o600,
        )
    _write_json(raw_dir / "errors.json", private, 0o600)
    _write_json(out_dir / SHAPE_REPORT_NAME, report, 0o644)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]], right: Set[int]) -> List[str]:
    """Render a plain-text table; columns in ``right`` are right-aligned."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row[:-1]):
            widths[i] = max(widths[i], len(cell))

    def fmt(row: Sequence[str]) -> str:
        cells = []
        for i, cell in enumerate(row):
            if i == len(row) - 1:
                cells.append(cell)
            elif i in right:
                cells.append(cell.rjust(widths[i]))
            else:
                cells.append(cell.ljust(widths[i]))
        return "  ".join(cells).rstrip()

    lines = [fmt(headers), fmt(["-" * w for w in widths[:-1]] + ["-" * len(headers[-1])])]
    lines.extend(fmt(row) for row in rows)
    return lines


def format_summary(report: Mapping[str, Any]) -> str:
    """
    Render the human summary table (value-free, like the shape report).

    Args:
        report: Shape report from ``build_reports``.

    Returns:
        Multi-line summary text.
    """
    rows: List[List[str]] = []
    last_rate_limit: Dict[str, str] = {}
    for name, entry in report["endpoints"].items():
        if "skip_reason" in entry:
            result = "skipped" if entry["status"] == STATUS_SKIPPED else "FAIL"
            notes_text = "; ".join(entry.get("notes", [])) or entry["skip_reason"]
            rows.append([name, "-", result, "-", notes_text])
            continue
        dropped = [d["path"] for d in entry.get("dropped_fields", [])]
        dropped_text = ", ".join(dropped[:3]) if dropped else "-"
        if len(dropped) > 3:
            dropped_text += f" (+{len(dropped) - 3} more)"
        rows.append([
            name,
            str(entry.get("records", 0)),
            "ok" if entry["status"] == STATUS_OK else "FAIL",
            dropped_text,
            "; ".join(entry.get("notes", [])) or "-",
        ])
        if entry.get("rate_limit_headers"):
            last_rate_limit = entry["rate_limit_headers"]

    lines = _table(["ENDPOINT", "RECORDS", "RESULT", "DROPPED FIELDS", "NOTES"], rows, {1})
    lines.append("")
    if last_rate_limit:
        lines.append("Rate limit headers (last response):")
        lines.extend(f"  {name}: {value}" for name, value in last_rate_limit.items())
    else:
        lines.append("Rate limit headers: none seen")
    summary = report["summary"]
    lines.append(
        f"Endpoints: {summary['ok']} ok, {summary['fail']} failed, "
        f"{summary['skipped']} skipped"
    )
    return "\n".join(lines)


# =============================================================================
# Setup: credentials, paths, tokens
# =============================================================================

def _credentials_help(redirect_uri: str) -> str:
    """Explain how to create a WHOOP developer app for this check."""
    scopes = ", ".join(SCOPES)
    return f"""\
WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET must be set.

This check signs in to YOUR WHOOP account through YOUR OWN WHOOP developer app:

  1. Open https://developer.whoop.com, sign in with your WHOOP account and go
     to the Developer Dashboard. Create a team if asked, then create an app.
  2. Redirect URL: register exactly
         {redirect_uri}
     (use --port to change the port, or set WHOOP_REDIRECT_URI to the exact
     http://localhost:<port>/... URL you registered).
  3. Scopes: select {scopes}.
  4. Copy the app's Client ID and Client Secret, then run:
         export WHOOP_CLIENT_ID=<client id>
         export WHOOP_CLIENT_SECRET=<client secret>
         python scripts/live_check.py

The check only reads (GET). It never revokes access or writes anything."""


def _resolve_redirect_uri(env_value: Optional[str], port: Optional[int]) -> str:
    """
    Pick the OAuth redirect URI from ``WHOOP_REDIRECT_URI`` or ``--port``.

    Args:
        env_value: ``WHOOP_REDIRECT_URI`` if set.
        port: ``--port`` if given.

    Returns:
        The redirect URI to use.

    Raises:
        _SetupError: If the URI cannot work with the SDK's local callback server.
    """
    if not env_value:
        return f"http://localhost:{port or DEFAULT_PORT}/callback"
    parsed = urlparse(env_value)
    if parsed.scheme != "http" or parsed.hostname not in _LOCAL_HOSTS:
        raise _SetupError(
            "WHOOP_REDIRECT_URI must be an http://localhost:<port>/... URL; the SDK "
            "receives the OAuth callback on a local plain-HTTP server."
        )
    if parsed.port is None:
        raise _SetupError("WHOOP_REDIRECT_URI must include an explicit port.")
    if port is not None and port != parsed.port:
        raise _SetupError(
            f"--port {port} does not match the port in WHOOP_REDIRECT_URI ({parsed.port})."
        )
    return env_value


def _git_worktree_root(path: Path) -> Optional[Path]:
    """Return the nearest directory at or above ``path`` that contains ``.git``."""
    for candidate in [path, *path.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def check_private_path(path: Path, what: str) -> Path:
    """
    Resolve a path for personal data and refuse locations inside a git tree.

    Args:
        path: Requested path (``~`` and relative paths are allowed).
        what: Option name for the error message, e.g. ``"--out"``.

    Returns:
        The resolved absolute path.

    Raises:
        _SetupError: If the path is inside this repository or any git
            working tree.
    """
    resolved = path.expanduser().resolve()
    repo = REPO_ROOT.resolve()
    if resolved == repo or repo in resolved.parents:
        raise _SetupError(
            f"refusing {what} inside the whoopyy repository ({repo}): it would hold "
            "personal health data. Choose a directory outside the repository."
        )
    root = _git_worktree_root(resolved)
    if root is not None:
        raise _SetupError(
            f"refusing {what} inside a git working tree ({root}): it would hold "
            "personal health data. Choose a directory outside any repository."
        )
    return resolved


def default_out_dir(now: Optional[datetime] = None) -> Path:
    """Return ``~/Projects/whoop-research/live-check-<YYYYmmdd-HHMMSS>``."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUT_PARENT.expanduser() / f"live-check-{stamp}"


def _create_out_dirs(out_dir: Path) -> Path:
    """
    Create ``out_dir`` (0700) and its ``raw`` directory (0700).

    Args:
        out_dir: Resolved output directory; may exist only if empty.

    Returns:
        The raw directory.

    Raises:
        _SetupError: If ``out_dir`` exists and is not an empty directory.
    """
    if out_dir.exists():
        if not out_dir.is_dir() or any(out_dir.iterdir()):
            raise _SetupError(f"--out {out_dir} already exists and is not empty.")
    else:
        out_dir.parent.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(mode=0o700)
    os.chmod(str(out_dir), 0o700)
    raw_dir = out_dir / RAW_DIR_NAME
    raw_dir.mkdir(mode=0o700)
    os.chmod(str(raw_dir), 0o700)
    return raw_dir


def _remove_empty_dirs(*paths: Path) -> None:
    """Remove each directory if it exists and is empty."""
    for path in paths:
        try:
            path.rmdir()
        except OSError:
            pass


def _finish_tokens(token_path: Path, token_dir: Optional[Path], keep: bool) -> str:
    """
    Delete or keep the token file at the end of the run.

    Args:
        token_path: Token file the client used.
        token_dir: Temporary directory holding it, or None for ``--token-file``.
        keep: Whether ``--keep-token`` was passed.

    Returns:
        A line describing what happened to the token file (no token values).
    """
    if token_dir is None:
        if token_path.exists():
            os.chmod(str(token_path), 0o600)
            return f"Token file left in place (--token-file, mode 0600): {token_path}"
        return f"No token file was written to {token_path}"
    if keep and token_path.exists():
        os.chmod(str(token_path), 0o600)
        return (
            f"Token file kept (--keep-token, mode 0600): {token_path}\n"
            f"  Reuse it with --token-file {token_path} and delete it when done."
        )
    shutil.rmtree(str(token_dir), ignore_errors=True)
    return "Temporary token file deleted."


@contextmanager
def _sdk_log_level(level: int) -> Iterator[None]:
    """Temporarily set every ``whoopyy`` logger to ``level``."""
    loggers = [
        logger for name, logger in logging.Logger.manager.loggerDict.items()
        if isinstance(logger, logging.Logger)
        and (name == "whoopyy" or name.startswith("whoopyy."))
    ]
    saved = [(logger, logger.level) for logger in loggers]
    for logger in loggers:
        logger.setLevel(level)
    try:
        yield
    finally:
        for logger, previous in saved:
            logger.setLevel(previous)


def _raise_terminated(signum: int, frame: Any) -> None:
    """Signal handler: turn SIGTERM/SIGHUP into ``_Terminated`` so cleanup runs."""
    raise _Terminated(signum)


def _set_handlers(names: Sequence[str], handler: Any) -> Dict[int, Any]:
    """
    Install ``handler`` for the named signals that exist on this platform.

    Does nothing outside the main thread, where Python cannot set handlers.

    Args:
        names: Signal names such as ``"SIGTERM"``.
        handler: Handler, ``signal.SIG_IGN`` or ``signal.SIG_DFL``.

    Returns:
        The previous handler per signal number, for ``_restore_handlers``.
    """
    previous: Dict[int, Any] = {}
    if threading.current_thread() is not threading.main_thread():
        return previous
    for name in names:
        signum = getattr(signal, name, None)
        if signum is not None:
            previous[signum] = signal.signal(signum, handler)
    return previous


def _restore_handlers(previous: Mapping[int, Any]) -> None:
    """Put back the handlers returned by ``_set_handlers``."""
    for signum, handler in previous.items():
        signal.signal(signum, handler if handler is not None else signal.SIG_DFL)


@contextmanager
def _interrupt_on_termination() -> Iterator[None]:
    """
    Treat SIGTERM and SIGHUP like Ctrl-C while the check runs.

    Python's default action for both ends the process without running
    ``finally`` blocks, which would leave the temporary token file (and its
    refresh token) behind, e.g. when the terminal window is closed.
    """
    previous = _set_handlers(_TERMINATION_SIGNALS, _raise_terminated)
    try:
        yield
    finally:
        _restore_handlers(previous)


@contextmanager
def _interrupts_ignored() -> Iterator[None]:
    """Ignore Ctrl-C, SIGTERM and SIGHUP so a second one cannot cut cleanup short."""
    previous = _set_handlers(_INTERRUPT_SIGNALS, signal.SIG_IGN)
    try:
        yield
    finally:
        _restore_handlers(previous)


def _browser_sign_in(client: WhoopClient) -> None:
    """Sign in through the SDK's OAuth flow in the user's own browser."""
    client.authenticate(auto_open_browser=True)


def _positive_int(text: str) -> int:
    """argparse type: an integer >= 1."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}")
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="live_check.py",
        description=(
            "Read-only check of whoopyy against your own WHOOP account. Signs in "
            "in your browser, GETs every read endpoint once and validates each raw "
            "response against its whoopyy model. Needs WHOOP_CLIENT_ID and "
            "WHOOP_CLIENT_SECRET (optional WHOOP_REDIRECT_URI)."
        ),
    )
    parser.add_argument(
        "--days", type=_positive_int, default=DEFAULT_DAYS,
        help=f"collection window in days, ending now (default {DEFAULT_DAYS}, max {MAX_DAYS})",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help=(
            "output directory, outside any git repository (default "
            "~/Projects/whoop-research/live-check-<YYYYmmdd-HHMMSS>)"
        ),
    )
    parser.add_argument(
        "--token-file", type=Path, default=None,
        help=(
            "token file to use and keep (e.g. one kept by an earlier --keep-token "
            "run); default is a temporary file deleted at exit"
        ),
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help=f"port of the local OAuth callback http://localhost:PORT/callback "
             f"(default {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--keep-token", action="store_true",
        help="keep the temporary token file (mode 0600) and print its path",
    )
    return parser


# =============================================================================
# Entry point
# =============================================================================

def main(
    argv: Optional[Sequence[str]] = None,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    authenticate: Optional[Callable[[WhoopClient], None]] = None,
) -> int:
    """
    Run the live check.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).
        transport: For tests: transport for API requests instead of the network.
        authenticate: For tests: replaces the browser sign-in. Receives the
            client and must leave it with usable tokens.

    Returns:
        Process exit code: 0 if every endpoint was called and validated
        (only the optional workout and activity-mapping checks may be
        skipped), 1 if any failed or sign-in failed, 2 if the check could
        not run, and 128 + the signal number (130, 143, 129) after Ctrl-C,
        SIGTERM or SIGHUP.
    """
    args = _build_parser().parse_args(argv)
    try:
        if args.days > MAX_DAYS:
            raise _SetupError(f"--days must be at most {MAX_DAYS}.")
        if args.port is not None and not 1 <= args.port <= 65535:
            raise _SetupError("--port must be between 1 and 65535.")
        out_dir = check_private_path(args.out or default_out_dir(), "--out")
        user_token_path = (
            check_private_path(args.token_file, "--token-file")
            if args.token_file is not None else None
        )
        redirect_uri = _resolve_redirect_uri(os.environ.get("WHOOP_REDIRECT_URI"), args.port)
        client_id = os.environ.get("WHOOP_CLIENT_ID", "").strip()
        client_secret = os.environ.get("WHOOP_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret or client_id.startswith("your_"):
            print(_credentials_help(redirect_uri), file=sys.stderr)
            return EXIT_NOT_RUN
        raw_dir = _create_out_dirs(out_dir)
    except _SetupError as exc:
        print(f"live_check: {exc}", file=sys.stderr)
        return EXIT_NOT_RUN

    token_dir: Optional[Path] = None
    token_path: Optional[Path] = user_token_path
    client: Optional[WhoopClient] = None
    with _interrupt_on_termination(), _sdk_log_level(logging.WARNING):
        try:
            if token_path is None:
                token_dir = Path(tempfile.mkdtemp(prefix="whoopyy-live-check-"))
                token_path = token_dir / "tokens.json"

            package_dir = Path(whoopyy.__file__).resolve().parent
            print("whoopyy live check (read-only)")
            print(f"  whoopyy {whoopyy.__version__} from {package_dir}")
            if REPO_ROOT.resolve() not in package_dir.parents:
                print("  note: this is not the whoopyy checkout the script lives in")
            print(f"  window: last {args.days} day(s); output: {out_dir}")

            client = WhoopClient(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                token_file=str(token_path),
            )
            recorder = Recorder()
            install_recorder(client, recorder, transport)

            if user_token_path is not None and user_token_path.exists():
                print("\nSigning in with the tokens in --token-file (the browser opens "
                      "only if they cannot be used).")
            else:
                print(
                    f"\nSigning in: your browser opens the WHOOP consent page. Approve "
                    f"access; the SDK waits up to 120 s for {redirect_uri}."
                )
            try:
                (authenticate or _browser_sign_in)(client)
            except Exception as exc:  # report sign-in problems without a traceback
                print(f"Sign-in failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                _remove_empty_dirs(raw_dir, out_dir)
                return EXIT_FAILED
            print("Signed in. Calling every read endpoint once (GET only)...\n")

            checks = run_checks(client, recorder, args.days)
            report, private = build_reports(checks, recorder, args.days)
            write_outputs(out_dir, raw_dir, report, private, recorder)

            print(format_summary(report))
            for line in report["anomalies"]:
                print(f"  anomaly: {line}")
            print(
                f"\nShape report (no personal values, safe to share): "
                f"{out_dir / SHAPE_REPORT_NAME}"
            )
            print(
                f"Raw responses (PERSONAL HEALTH DATA, 0600 files in a 0700 directory; "
                f"do not share or commit): {raw_dir}"
            )
            exit_code = int(report["summary"]["exit_code"])
            print(f"Exit code: {exit_code}")
            return exit_code
        except KeyboardInterrupt as exc:
            if isinstance(exc, _Terminated):
                print(f"\nStopped by {signal.Signals(exc.signum).name}.", file=sys.stderr)
                code = 128 + exc.signum
            else:
                print("\nInterrupted.", file=sys.stderr)
                code = 128 + int(signal.SIGINT)
            _remove_empty_dirs(raw_dir, out_dir)
            return code
        finally:
            with _interrupts_ignored():
                try:
                    if client is not None:
                        client.close()
                finally:
                    if token_path is not None:
                        print(_finish_tokens(token_path, token_dir, args.keep_token))


if __name__ == "__main__":
    sys.exit(main())
