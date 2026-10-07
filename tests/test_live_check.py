"""
Tests for scripts/live_check.py, the read-only live check.

The script runs end-to-end against an ``httpx.MockTransport`` that serves
WHOOP v2 spec-shaped fake data. Sign-in is stubbed; no network, browser,
real credentials or ``~/.whoop_tokens.json`` are touched.

The fake data deliberately includes an undeclared field (top level and
nested), a null ``spo2_percentage``, a collection whose last page has no
``next_token`` key, one whose last page has ``next_token: null``, and one
invalid workout record. Options add an empty window, int64 IDs sent as
strings, unscored records ahead of scored ones, and a pagination key the
SDK does not read.
"""

import importlib.util
import json
import logging
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Literal, Optional, Set

import httpx
import pytest

import strapkit
from strapkit.client import WhoopClient
from strapkit.constants import DEFAULT_TOKEN_FILE
from strapkit.utils import save_tokens

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "live_check.py"


def _load_script() -> Any:
    """Import scripts/live_check.py as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("strapkit_live_check", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


live_check = _load_script()

# =============================================================================
# Fake WHOOP account (every value is distinctive so leaks are detectable)
# =============================================================================

USER_ID = 48151623
EMAIL = "janelle.testerson@example.org"
FIRST_NAME = "Janelle"
LAST_NAME = "Testerson"
CYCLE_IDS = (731902841, 731902842, 731902843)
SLEEP_IDS = (
    "5f0c2b1e-8a1d-4c3e-9b7a-1d2e3f4a5b6c",
    "6a1d3c2f-9b2e-4d4f-8c8b-2e3f4a5b6c7d",
)
WORKOUT_IDS = (
    "7b2e4d3a-0c3f-4e5a-9d9c-3f4a5b6c7d8e",
    "8c3f5e4b-1d4a-4f6b-8e0d-4a5b6c7d8e9f",
    "9d4a6f5c-2e5b-4a7c-9f1e-5b6c7d8e9fa0",
)
SLEEP_V1_ID = 55667788
PENDING_CYCLE_ID = 731902844
PENDING_SLEEP_ID = "ab5b7a6d-3f6c-4b8d-8a2f-6c7d8e9fa0b1"
UNSCORABLE_WORKOUT_ID = "bc6c8b7e-4a7d-4c9e-9b3a-7d8e9fa0b1c2"
NEXT_TOKEN = "cGFnZS10d28tc2VjcmV0LXRva2Vu"
WORKOUT_NEXT_TOKEN = "d29ya291dC1wYWdlLXR3by10b2tlbg"
INVALID_STRAIN = "not-a-number-strain"
ACCESS_TOKEN = "fake-access-token-3b9c6d1e"
REFRESH_TOKEN = "fake-refresh-token-8f2a7c4b"
SCORE_STATES = {"SCORED", "PENDING_SCORE", "UNSCORABLE"}

EXPECTED_ENDPOINTS = [
    "profile",
    "body_measurement",
    "cycle_collection",
    "cycle",
    "recovery_collection",
    "recovery_for_cycle",
    "sleep_collection",
    "sleep",
    "sleep_for_cycle",
    "workout_collection",
    "workout",
    "activity_mapping",
]

COUNT_KEYS = {
    "schema_version", "window_days", "endpoints", "ok", "fail", "skipped", "exit_code",
    "blocked_non_get_requests", "requests", "documents", "records", "records_valid",
    "records_invalid", "count", "present", "absent", "null", "pages",
    "duplicate_record_keys",
}
"""Keys under which the shape report may hold a number (all of them are counts)."""

COUNT_MAPS = {"types", "string_formats", "http_statuses"}
"""Keys whose values map names to counts."""


def _cycle(cycle_id: int, *, extra: bool = False) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "id": cycle_id,
        "user_id": USER_ID,
        "created_at": "2026-09-29T07:41:12.345Z",
        "updated_at": "2026-09-30T05:12:43.210Z",
        "start": "2026-09-29T03:17:29.111Z",
        "end": "2026-09-30T02:58:47.222Z",
        "timezone_offset": "-05:00",
        "score_state": "SCORED",
        "score": {
            "strain": 13.371337,
            "kilojoule": 9876.54321,
            "average_heart_rate": 73,
            "max_heart_rate": 187,
        },
        "step_count": 12345,
    }
    if extra:
        record["undeclared_cycle_field"] = "brand-new-api-value"
    return record


def _recovery(cycle_id: int, sleep_id: str, spo2: Optional[float]) -> Dict[str, Any]:
    return {
        "cycle_id": cycle_id,
        "sleep_id": sleep_id,
        "user_id": USER_ID,
        "created_at": "2026-09-30T06:01:02.303Z",
        "updated_at": "2026-09-30T06:04:05.606Z",
        "score_state": "SCORED",
        "score": {
            "user_calibrating": False,
            "recovery_score": 61.5,
            "resting_heart_rate": 51.25,
            "hrv_rmssd_milli": 83.718281,
            "spo2_percentage": spo2,
            "skin_temp_celsius": 33.6789,
            "undeclared_metric": 4.2424,
        },
    }


def _sleep(sleep_id: str, cycle_id: int, v1_id: Optional[int]) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "id": sleep_id,
        "cycle_id": cycle_id,
        "user_id": USER_ID,
        "created_at": "2026-09-30T06:07:08.909Z",
        "updated_at": "2026-09-30T06:10:11.112Z",
        "start": "2026-09-29T22:47:13.131Z",
        "end": "2026-09-30T05:59:14.141Z",
        "timezone_offset": "-05:00",
        "nap": False,
        "score_state": "SCORED",
        "score": {
            "stage_summary": {
                "total_in_bed_time_milli": 25921001,
                "total_awake_time_milli": 1402003,
                "total_no_data_time_milli": 1004,
                "total_light_sleep_time_milli": 12903005,
                "total_slow_wave_sleep_time_milli": 6204006,
                "total_rem_sleep_time_milli": 5405007,
                "sleep_cycle_count": 5,
                "disturbance_count": 11,
            },
            "sleep_needed": {
                "baseline_milli": 27395716,
                "need_from_sleep_debt_milli": 352230,
                "need_from_recent_strain_milli": 208595,
                "need_from_recent_nap_milli": -12312,
            },
            "respiratory_rate": 15.8765,
            "sleep_performance_percentage": 91.234,
            "sleep_consistency_percentage": 77.345,
            "sleep_efficiency_percentage": 88.456,
        },
    }
    if v1_id is not None:
        record["v1_id"] = v1_id
    return record


def _open_cycle(cycle_id: int) -> Dict[str, Any]:
    """The current cycle: no end, no score yet."""
    record = _cycle(cycle_id)
    for key in ("end", "score", "step_count"):
        del record[key]
    record["score_state"] = "PENDING_SCORE"
    return record


def _pending_recovery(cycle_id: int, sleep_id: str) -> Dict[str, Any]:
    record = _recovery(cycle_id, sleep_id, spo2=None)
    del record["score"]
    record["score_state"] = "PENDING_SCORE"
    return record


def _pending_nap(sleep_id: str, cycle_id: int) -> Dict[str, Any]:
    record = _sleep(sleep_id, cycle_id, None)
    del record["score"]
    record["nap"] = True
    record["score_state"] = "PENDING_SCORE"
    return record


def _unscorable_workout(workout_id: str) -> Dict[str, Any]:
    record = _workout(workout_id)
    del record["score"]
    record["score_state"] = "UNSCORABLE"
    return record


def _workout(workout_id: str, strain: Any = 11.7243) -> Dict[str, Any]:
    return {
        "id": workout_id,
        "user_id": USER_ID,
        "created_at": "2026-09-28T18:20:21.222Z",
        "updated_at": "2026-09-28T19:23:24.252Z",
        "start": "2026-09-28T17:26:27.282Z",
        "end": "2026-09-28T18:29:30.313Z",
        "timezone_offset": "-05:00",
        "sport_name": "rowing",
        "sport_id": 48,
        "score_state": "SCORED",
        "score": {
            "strain": strain,
            "average_heart_rate": 142,
            "max_heart_rate": 176,
            "kilojoule": 2345.6789,
            "percent_recorded": 99.5,
            "distance_meter": 5432.1,
            "altitude_gain_meter": 12.75,
            "altitude_change_meter": -3.25,
            "zone_durations": {
                "zone_zero_milli": 301001,
                "zone_one_milli": 602002,
                "zone_two_milli": 903003,
                "zone_three_milli": 904004,
                "zone_four_milli": 605005,
                "zone_five_milli": 306006,
            },
        },
    }


class FakeWhoop:
    """In-memory WHOOP v2 API served through httpx.MockTransport."""

    def __init__(
        self,
        *,
        invalid_workout: bool = True,
        workouts: bool = True,
        v1_ids: bool = True,
        fail_path: Optional[str] = None,
        empty_window: bool = False,
        string_ids: bool = False,
        pending_first: bool = False,
        camel_next_token: bool = False,
    ) -> None:
        """
        Build the fake account.

        Args:
            invalid_workout: Give the second workout a non-numeric strain.
            workouts: Serve any workouts at all.
            v1_ids: Give the first sleep a legacy v1_id.
            fail_path: URL path that answers HTTP 500.
            empty_window: Serve no cycles, recoveries, sleeps or workouts.
            string_ids: Send cycle IDs (and cycle_id references) as digit strings.
            pending_first: Put an open cycle and unscored records first.
            camel_next_token: Send the cycle page token as ``nextToken``.
        """
        self.requests: List[httpx.Request] = []
        self.fail_path = fail_path
        self.profile = {
            "user_id": USER_ID,
            "email": EMAIL,
            "first_name": FIRST_NAME,
            "last_name": LAST_NAME,
        }
        self.body = {"height_meter": 1.7821, "weight_kilogram": 68.4213, "max_heart_rate": 193}
        cycles = [_cycle(CYCLE_IDS[0], extra=True), _cycle(CYCLE_IDS[1]), _cycle(CYCLE_IDS[2])]
        recoveries = [
            _recovery(CYCLE_IDS[0], SLEEP_IDS[0], spo2=96.4321),
            _recovery(CYCLE_IDS[1], SLEEP_IDS[1], spo2=None),  # null spo2
        ]
        sleeps = [
            _sleep(SLEEP_IDS[0], CYCLE_IDS[0], SLEEP_V1_ID if v1_ids else None),
            _sleep(SLEEP_IDS[1], CYCLE_IDS[1], None),
        ]
        if workouts:
            second = _workout(WORKOUT_IDS[1], INVALID_STRAIN if invalid_workout else 9.8765)
            workout_list = [_workout(WORKOUT_IDS[0]), second, _workout(WORKOUT_IDS[2])]
        else:
            workout_list = []
        if pending_first:  # the API lists the newest first: the open, unscored cycle
            cycles.insert(0, _open_cycle(PENDING_CYCLE_ID))
            recoveries.insert(0, _pending_recovery(PENDING_CYCLE_ID, PENDING_SLEEP_ID))
            sleeps.insert(0, _pending_nap(PENDING_SLEEP_ID, PENDING_CYCLE_ID))
            if workout_list:
                workout_list.insert(0, _unscorable_workout(UNSCORABLE_WORKOUT_ID))
        if empty_window:
            cycles, recoveries, sleeps, workout_list = [], [], [], []
        if string_ids:
            for cycle in cycles:
                cycle["id"] = str(cycle["id"])
            for item in recoveries + sleeps:
                item["cycle_id"] = str(item["cycle_id"])

        self.cycles = {int(c["id"]): c for c in cycles}
        self.cycle_pages: List[Dict[str, Any]] = [
            {"records": cycles[:2], "next_token": NEXT_TOKEN},
            {"records": cycles[2:]},  # last page: next_token key absent
        ] if len(cycles) > 2 else [{"records": cycles}]
        if camel_next_token:
            self.cycle_pages[0]["nextToken"] = self.cycle_pages[0].pop("next_token")
        self.recoveries = {int(r["cycle_id"]): r for r in recoveries}
        self.recovery_page = {"records": recoveries, "next_token": None}
        self.sleeps = {s["id"]: s for s in sleeps}
        self.sleeps_by_cycle = {int(s["cycle_id"]): s for s in sleeps if not s["nap"]}
        self.sleep_page = {"records": sleeps}
        self.workouts = {w["id"]: w for w in workout_list}
        self.workout_pages = [
            {"records": workout_list[:2], "next_token": WORKOUT_NEXT_TOKEN},
            {"records": workout_list[2:]},
        ] if len(workout_list) > 2 else [{"records": workout_list}]
        self.mappings = {SLEEP_V1_ID: {"v2_activity_id": SLEEP_IDS[0]}}

    def paths(self) -> List[str]:
        """Return the URL paths requested so far."""
        return [request.url.path for request in self.requests]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method != "GET":
            return httpx.Response(204)
        assert request.headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"
        path = request.url.path
        if path == self.fail_path:
            return self._json(500, {"error": "internal"})
        token = request.url.params.get("nextToken")
        parts = path.split("/")
        payload: Any = None
        if path == "/developer/v2/user/profile/basic":
            payload = self.profile
        elif path == "/developer/v2/user/measurement/body":
            payload = self.body
        elif path == "/developer/v2/cycle":
            payload = self.cycle_pages[1] if token == NEXT_TOKEN else self.cycle_pages[0]
        elif path == "/developer/v2/recovery":
            payload = self.recovery_page
        elif path == "/developer/v2/activity/sleep":
            payload = self.sleep_page
        elif path == "/developer/v2/activity/workout":
            pages = self.workout_pages
            payload = pages[1] if token == WORKOUT_NEXT_TOKEN and len(pages) > 1 else pages[0]
        elif path.startswith("/developer/v2/cycle/") and len(parts) == 5:
            payload = self.cycles.get(int(parts[4]))
        elif path.startswith("/developer/v2/cycle/") and parts[-1] == "recovery":
            payload = self.recoveries.get(int(parts[4]))
        elif path.startswith("/developer/v2/cycle/") and parts[-1] == "sleep":
            payload = self.sleeps_by_cycle.get(int(parts[4]))
        elif path.startswith("/developer/v2/activity/sleep/"):
            payload = self.sleeps.get(parts[-1])
        elif path.startswith("/developer/v2/activity/workout/"):
            payload = self.workouts.get(parts[-1])
        elif path.startswith("/developer/v1/activity-mapping/"):
            payload = self.mappings.get(int(parts[-1]))
        if payload is None:
            return self._json(404, {"message": "not found"})
        return self._json(200, payload)

    def _json(self, status: int, payload: Any) -> httpx.Response:
        return httpx.Response(
            status,
            json=payload,
            headers={
                "X-RateLimit-Limit": "100, 100;window=60, 10000;window=86400",
                "X-RateLimit-Remaining": str(100 - len(self.requests)),
                "X-RateLimit-Reset": "42",
            },
        )

    def personal_values(self) -> Set[Any]:
        """Every scalar the fake account serves (minus booleans and enum values)."""
        found: Set[Any] = {NEXT_TOKEN, WORKOUT_NEXT_TOKEN}

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, bool) or value is None:
                return
            elif isinstance(value, str) and value in SCORE_STATES:
                return
            else:
                found.add(value)

        walk([
            self.profile, self.body, self.cycle_pages, self.recovery_page,
            self.sleep_page, self.workout_pages, list(self.mappings.values()),
        ])
        return found


_SIGNAL_CHILD = """
import importlib.util
import os
import signal
import sys

import httpx

test_path, out, signame, when = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("live_check_tests", test_path)
tests = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tests
spec.loader.exec_module(tests)


def no_network(self, request):
    raise AssertionError("real network request attempted")


httpx.HTTPTransport.handle_request = no_network
signum = getattr(signal, signame)
fake = tests.FakeWhoop()
sign_in = tests._fake_sign_in({})


def handler(request):
    if when == "request" and len(fake.requests) == 2:
        os.kill(os.getpid(), signum)
    return fake.handler(request)


def authenticate(client):
    sign_in(client)  # the token file now holds a refresh token
    if when == "sign-in":
        os.kill(os.getpid(), signum)


sys.exit(tests.live_check.main(
    ["--out", out], transport=httpx.MockTransport(handler), authenticate=authenticate,
))
"""
"""Child process for the signal tests: SIGTERM/SIGHUP itself mid-run."""


# =============================================================================
# Fixtures and helpers
# =============================================================================

@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake app credentials; no redirect URI override from the caller's shell."""
    monkeypatch.setenv("WHOOP_CLIENT_ID", "fake-client-id-1234")
    monkeypatch.setenv("WHOOP_CLIENT_SECRET", "fake-client-secret-5678")
    monkeypatch.delenv("WHOOP_REDIRECT_URI", raising=False)


@pytest.fixture
def guards(monkeypatch: pytest.MonkeyPatch) -> Dict[str, List[Any]]:
    """Fail on real network, browser or OAuth use; record any revoke call."""
    calls: Dict[str, List[Any]] = {"revoke": []}

    def no_network(self: Any, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"real network request attempted: {request.method}")

    def no_browser(*args: Any, **kwargs: Any) -> bool:
        raise AssertionError("browser must not be opened")

    def no_oauth(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("real OAuth flow must not run")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setattr("webbrowser.open", no_browser)
    monkeypatch.setattr("strapkit.auth.OAuthHandler.authorize", no_oauth)
    monkeypatch.setattr(
        WhoopClient, "revoke_access", lambda self: calls["revoke"].append(True),
    )
    return calls


def _fake_sign_in(state: Dict[str, Any]) -> Any:
    """Stand-in for the browser sign-in: write fake tokens to the client's file."""

    def sign_in(client: WhoopClient) -> None:
        token_file = str(client.auth.token_file)
        state["token_file"] = token_file
        state["token_existed_before"] = os.path.exists(token_file)
        tokens = {
            "access_token": ACCESS_TOKEN,
            "refresh_token": REFRESH_TOKEN,
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
            "token_type": "Bearer",
            "scope": "offline read:profile",
        }
        save_tokens(tokens, token_file)  # type: ignore[arg-type]
        client.auth._tokens = tokens  # type: ignore[assignment]
        client._authenticated = True

    return sign_in


def _run(fake: FakeWhoop, out: Path, *args: str) -> Dict[str, Any]:
    """Run main() against ``fake``; return exit code, sign-in state and report."""
    state: Dict[str, Any] = {}
    code = live_check.main(
        ["--out", str(out), "--days", "14", *args],
        transport=httpx.MockTransport(fake.handler),
        authenticate=_fake_sign_in(state),
    )
    report_path = out / "shape_report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else None
    return {"code": code, "state": state, "report": report}


def _numeric_leaves(
    value: Any, key: Optional[str] = None, parent: Optional[str] = None,
) -> Iterator[Any]:
    """Yield ``(key, parent, number)`` for every number in a JSON document."""
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _numeric_leaves(child, str(child_key), key)
    elif isinstance(value, list):
        for child in value:
            yield from _numeric_leaves(child, key, parent)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield key, parent, value


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# =============================================================================
# End-to-end
# =============================================================================

class TestEndToEnd:
    """The script against the fake account, with one invalid workout."""

    def test_reports_every_endpoint_and_fails_on_the_invalid_record(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        result = _run(FakeWhoop(), tmp_path / "out")
        report = result["report"]

        assert result["code"] == 1
        assert list(report["endpoints"]) == EXPECTED_ENDPOINTS
        statuses = {name: e["status"] for name, e in report["endpoints"].items()}
        assert statuses.pop("workout_collection") == "fail"
        assert set(statuses.values()) == {"ok"}
        assert report["summary"] == {
            "endpoints": 12, "ok": 11, "fail": 1, "skipped": 0, "exit_code": 1,
        }
        assert report["strapkit_version"] == strapkit.__version__

    def test_records_validation_error_path_and_type(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        workouts = _run(FakeWhoop(), tmp_path / "out")["report"]["endpoints"]["workout_collection"]

        assert workouts["records"] == 3
        assert workouts["records_invalid"] == 1
        assert workouts["records_valid"] == 2
        assert workouts["sdk_exception"] == "ValidationError"
        (error,) = workouts["validation_errors"]
        assert error["path"] == "records[].score.strain"
        assert error["type"] == "float_parsing"
        assert error["input_type"] == "string"
        assert error["count"] == 1
        assert "valid number" in error["message"]
        # The SDK raised on page 1; page 2 was still fetched and checked.
        assert workouts["pagination"]["pages"] == 2
        assert any("fetched raw after the SDK error" in note for note in workouts["notes"])

    def test_records_dropped_fields_nulls_types_and_next_token(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        report = _run(FakeWhoop(), tmp_path / "out")["report"]
        cycles = report["endpoints"]["cycle_collection"]
        recoveries = report["endpoints"]["recovery_collection"]

        assert cycles["records"] == 3
        assert [d["path"] for d in cycles["dropped_fields"]] == ["records[].undeclared_cycle_field"]
        assert cycles["dropped_fields"][0]["types"] == {"string": 1}
        assert cycles["pagination"]["pages"] == 2
        assert cycles["pagination"]["next_token_last_page"] == "absent"
        assert cycles["pagination"]["next_token_other_pages"] == ["string"]
        assert "nextToken" in cycles["pagination"]["query_params"]
        assert cycles["fields"]["records[].id"]["types"] == {"integer": 3}
        assert cycles["fields"]["records[].start"]["string_formats"] == {"date-time(Z)": 3}
        assert cycles["fields"]["next_token"]["absent"] == 1

        spo2 = recoveries["fields"]["records[].score.spo2_percentage"]
        assert spo2["null"] == 1
        assert spo2["types"] == {"null": 1, "number": 1}
        assert [d["path"] for d in recoveries["dropped_fields"]] == [
            "records[].score.undeclared_metric"
        ]
        assert recoveries["pagination"]["next_token_last_page"] == "null"
        assert any("next_token on the last page is null" in a for a in report["anomalies"])

        sleep = report["endpoints"]["sleep"]
        assert sleep["status"] == "ok"
        assert sleep["dropped_fields"] == []
        assert report["endpoints"]["activity_mapping"]["status"] == "ok"
        assert report["endpoints"]["activity_mapping"]["notes"] == []

    def test_records_rate_limit_headers(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        profile = _run(FakeWhoop(), tmp_path / "out")["report"]["endpoints"]["profile"]

        headers = profile["rate_limit_headers"]
        assert headers["X-RateLimit-Limit"] == "100, 100;window=60, 10000;window=86400"
        assert headers["X-RateLimit-Reset"] == "42"
        assert "X-RateLimit-Remaining" in headers

    def test_shape_report_and_stdout_hold_no_personal_values(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        fake = FakeWhoop()
        out = tmp_path / "out"
        report = _run(fake, out)["report"]
        report_text = (out / "shape_report.json").read_text()
        captured = capsys.readouterr()
        console = captured.out + captured.err

        for value in fake.personal_values():
            if isinstance(value, str):
                assert value not in report_text, f"string value leaked: {value!r}"
                assert value not in console, f"string value leaked to stdout: {value!r}"
            elif len(str(value)) >= 4:
                assert str(value) not in report_text, f"number leaked: {value!r}"
                assert str(value) not in console, f"number leaked to stdout: {value!r}"
        for secret in (ACCESS_TOKEN, REFRESH_TOKEN, "fake-client-secret-5678"):
            assert secret not in report_text
            assert secret not in console

        # Every number in the report is a count.
        for key, parent, _ in _numeric_leaves(report):
            assert key in COUNT_KEYS or parent in COUNT_MAPS, (key, parent)

    def test_stdout_has_summary_table(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = tmp_path / "out"
        _run(FakeWhoop(), out)
        stdout = capsys.readouterr().out

        assert "ENDPOINT" in stdout and "DROPPED FIELDS" in stdout and "NOTES" in stdout
        assert "records[].undeclared_cycle_field" in stdout
        assert "FAIL" in stdout
        assert str(out / "shape_report.json") in stdout
        assert "PERSONAL HEALTH DATA" in stdout
        assert "Exit code: 1" in stdout


class TestEveryEndpointIsExercised:
    """The check cannot pass without really validating each endpoint."""

    def test_scored_records_are_preferred_over_the_open_cycle(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        fake = FakeWhoop(invalid_workout=False, pending_first=True)
        result = _run(fake, tmp_path / "out")
        endpoints = result["report"]["endpoints"]
        paths = fake.paths()

        assert result["code"] == 0
        assert f"/developer/v2/cycle/{PENDING_CYCLE_ID}" not in paths
        assert f"/developer/v2/cycle/{PENDING_CYCLE_ID}/recovery" not in paths
        assert f"/developer/v2/activity/sleep/{PENDING_SLEEP_ID}" not in paths
        assert f"/developer/v2/activity/workout/{UNSCORABLE_WORKOUT_ID}" not in paths
        for name in ("cycle", "recovery_for_cycle", "sleep", "sleep_for_cycle", "workout"):
            assert "score" not in endpoints[name]["declared_never_present"], name
            assert not any("no scored record" in note for note in endpoints[name]["notes"])
        assert "end" not in endpoints["cycle"]["declared_never_present"]

    def test_int64_ids_sent_as_strings_are_still_exercised(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        fake = FakeWhoop(invalid_workout=False, string_ids=True)
        result = _run(fake, tmp_path / "out")
        report = result["report"]
        endpoints = report["endpoints"]

        assert result["code"] == 0
        assert f"/developer/v2/cycle/{CYCLE_IDS[0]}" in fake.paths()
        for name in ("cycle", "recovery_for_cycle", "sleep_for_cycle"):
            assert endpoints[name]["status"] == "ok", name
            assert not any("differs" in note for note in endpoints[name]["notes"]), name
        assert endpoints["cycle_collection"]["type_mismatches"] == [
            {"path": "records[].id", "expected": ["integer"], "types": {"string": 3}},
        ]
        assert endpoints["cycle"]["type_mismatches"] == [
            {"path": "id", "expected": ["integer"], "types": {"string": 1}},
        ]
        assert (
            "cycle_collection: records[].id is declared integer but the JSON had string x3 "
            "(accepted only by pydantic coercion)"
        ) in report["anomalies"]

    def test_pagination_key_the_sdk_ignores_fails_the_collection(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        result = _run(FakeWhoop(invalid_workout=False, camel_next_token=True), tmp_path / "out")
        cycles = result["report"]["endpoints"]["cycle_collection"]

        assert result["code"] == 1
        assert cycles["status"] == "fail"
        assert cycles["ignored_pagination_keys"] == ["nextToken"]
        assert cycles["pagination"]["pages"] == 1
        assert cycles["records"] == 2
        assert any(
            "pagination key nextToken is ignored by the SDK" in line
            for line in result["report"]["anomalies"]
        )

    def test_required_endpoints_without_data_fail(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = _run(FakeWhoop(empty_window=True), tmp_path / "out")
        report = result["report"]
        endpoints = report["endpoints"]

        assert result["code"] == 1
        assert report["summary"] == {
            "endpoints": 12, "ok": 6, "fail": 4, "skipped": 2, "exit_code": 1,
        }
        for name in ("cycle", "recovery_for_cycle", "sleep", "sleep_for_cycle"):
            assert endpoints[name]["status"] == "fail", name
            assert endpoints[name]["required"] is True
            assert endpoints[name]["notes"][0].startswith("not verified: no "), name
            assert endpoints[name]["skip_reason"].endswith("try a larger --days"), name
        assert endpoints["workout"]["status"] == "skipped"
        assert endpoints["activity_mapping"]["status"] == "skipped"
        assert (
            "cycle: not verified, no cycle in the window; try a larger --days"
            in report["anomalies"]
        )
        stdout = capsys.readouterr().out
        assert "Endpoints: 6 ok, 4 failed, 2 skipped" in stdout
        assert "Exit code: 1" in stdout

    def test_failed_collection_explains_the_unverified_endpoint(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        fake = FakeWhoop(invalid_workout=False, fail_path="/developer/v2/cycle")
        result = _run(fake, tmp_path / "out")
        cycle = result["report"]["endpoints"]["cycle"]

        assert result["code"] == 1
        assert cycle["status"] == "fail"
        assert cycle["skip_reason"] == "cycle_collection failed, so there was no cycle to request"


class TestPrivacyOfOutputs:
    """Raw responses are private; tokens never reach disk outside the token file."""

    def test_raw_files_are_0600_in_a_0700_directory(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        out = tmp_path / "out"
        _run(FakeWhoop(), out)
        raw = out / "raw"

        assert _mode(out) == 0o700
        assert _mode(raw) == 0o700
        files = sorted(raw.iterdir())
        assert len(files) >= 12
        for path in files:
            assert _mode(path) == 0o600, path.name
        # The raw responses are the real data, so they hold the personal values,
        # and errors.json keeps the full validation messages.
        raw_text = "".join(path.read_text() for path in files)
        assert EMAIL in raw_text
        errors = json.loads((raw / "errors.json").read_text())
        (detail,) = errors["workout_collection"]["validation_errors"]
        assert detail["loc"] == ["records", 1, "score", "strain"]
        assert detail["type"] == "float_parsing"

    def test_tokens_are_not_written_to_the_output(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        out = tmp_path / "out"
        _run(FakeWhoop(), out)

        for path in out.rglob("*"):
            if path.is_file():
                text = path.read_text()
                assert ACCESS_TOKEN not in text, path.name
                assert REFRESH_TOKEN not in text, path.name
                assert "Bearer" not in text, path.name


class TestTokenFile:
    """The token file is temporary and removed unless --keep-token is passed."""

    def test_token_file_is_temporary_and_deleted(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = _run(FakeWhoop(), tmp_path / "out")
        token_file = Path(result["state"]["token_file"])

        assert result["state"]["token_existed_before"] is False
        assert token_file != Path(DEFAULT_TOKEN_FILE)
        assert Path(tempfile.gettempdir()).resolve() in token_file.resolve().parents
        assert not token_file.exists()
        assert not token_file.parent.exists()
        assert "Temporary token file deleted." in capsys.readouterr().out

    def test_keep_token_keeps_a_0600_file_and_prints_its_path(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = _run(FakeWhoop(), tmp_path / "out", "--keep-token")
        token_file = Path(result["state"]["token_file"])
        try:
            assert token_file.exists()
            assert _mode(token_file) == 0o600
            stdout = capsys.readouterr().out
            assert str(token_file) in stdout
            assert ACCESS_TOKEN not in stdout
        finally:
            shutil.rmtree(str(token_file.parent), ignore_errors=True)

    def test_explicit_token_file_is_used_and_kept(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        token_file = tmp_path / "tokens" / "kept.json"
        token_file.parent.mkdir()
        result = _run(FakeWhoop(), tmp_path / "out", "--token-file", str(token_file))

        assert Path(result["state"]["token_file"]) == token_file.resolve()
        assert token_file.exists()
        assert _mode(token_file) == 0o600

    @pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="needs POSIX signals")
    @pytest.mark.parametrize(
        "signame, when",
        [("SIGTERM", "request"), ("SIGHUP", "request"), ("SIGTERM", "sign-in")],
    )
    def test_termination_signal_still_deletes_the_token_file(
        self, tmp_path: Path, signame: str, when: str,
    ) -> None:
        temp_root = tmp_path / "tmp"
        temp_root.mkdir()
        out = tmp_path / "out"
        child_env = dict(
            os.environ,
            TMPDIR=str(temp_root),
            WHOOP_CLIENT_ID="fake-client-id-1234",
            WHOOP_CLIENT_SECRET="fake-client-secret-5678",
        )
        child_env.pop("WHOOP_REDIRECT_URI", None)

        proc = subprocess.run(
            [sys.executable, "-c", _SIGNAL_CHILD, __file__, str(out), signame, when],
            env=child_env, capture_output=True, text=True, timeout=120,
        )

        assert proc.returncode == 128 + int(getattr(signal, signame)), proc.stderr
        assert f"Stopped by {signame}." in proc.stderr
        assert "Temporary token file deleted." in proc.stdout
        assert list(temp_root.iterdir()) == []
        assert not out.exists()
        assert REFRESH_TOKEN not in proc.stdout + proc.stderr

    def test_signal_handlers_are_restored(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        names = [name for name in ("SIGINT", "SIGTERM", "SIGHUP") if hasattr(signal, name)]
        before = {name: signal.getsignal(getattr(signal, name)) for name in names}
        _run(FakeWhoop(), tmp_path / "out")
        assert {name: signal.getsignal(getattr(signal, name)) for name in names} == before


class TestReadOnly:
    """Nothing but GET ever reaches the API, and revoke_access() is never called."""

    def test_only_get_requests_are_sent(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        fake = FakeWhoop()
        report = _run(fake, tmp_path / "out")["report"]

        assert fake.requests
        assert {request.method for request in fake.requests} == {"GET"}
        assert not any(r.url.path.endswith("/user/access") for r in fake.requests)
        assert guards["revoke"] == []
        assert report["blocked_non_get_requests"] == 0

    def test_recorder_blocks_delete_before_it_is_sent(self, tmp_path: Path) -> None:
        sent: List[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(request)
            return httpx.Response(204)

        client = WhoopClient(
            client_id="fake-client-id-1234",
            client_secret="fake-client-secret-5678",
            token_file=str(tmp_path / "tokens.json"),
        )
        try:
            client.auth._tokens = {  # type: ignore[assignment]
                "access_token": ACCESS_TOKEN,
                "refresh_token": REFRESH_TOKEN,
                "expires_in": 3600,
                "expires_at": time.time() + 3600,
                "token_type": "Bearer",
                "scope": "offline",
            }
            recorder = live_check.Recorder()
            live_check.install_recorder(client, recorder, httpx.MockTransport(handler))

            with pytest.raises(live_check.ReadOnlyViolation):
                client.revoke_access()
        finally:
            client.close()

        assert sent == []
        assert recorder.blocked_methods == ["DELETE"]

    def test_request_limit_stops_a_next_token_loop(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"records": [], "next_token": "same-token"})

        client = WhoopClient(
            client_id="fake-client-id-1234",
            client_secret="fake-client-secret-5678",
            token_file=str(tmp_path / "tokens.json"),
        )
        try:
            client.auth._tokens = {  # type: ignore[assignment]
                "access_token": ACCESS_TOKEN,
                "refresh_token": REFRESH_TOKEN,
                "expires_in": 3600,
                "expires_at": time.time() + 3600,
                "token_type": "Bearer",
                "scope": "offline",
            }
            recorder = live_check.Recorder(max_requests_per_label=5)
            live_check.install_recorder(client, recorder, httpx.MockTransport(handler))
            check = live_check.EndpointCheck(
                "cycle_collection", "iter_cycles()", "GET /developer/v2/cycle",
                live_check.CycleCollection, collection=True, record_key="id",
            )
            live_check._collect(
                check, recorder, client, client.iter_cycles, "cycle_collection",
                datetime(2026, 9, 1),
            )
        finally:
            client.close()

        assert isinstance(check.sdk_exception, live_check.RequestLimitReached)
        assert recorder.page_count("cycle_collection") == 5
        entry, _ = live_check.analyse_check(check, recorder)
        assert entry["status"] == "fail"
        assert entry["pagination"]["repeated_next_token"] is True


class TestExitCodes:
    """0 when every endpoint validated, 1 when one failed, 2 when it cannot run."""

    def test_exit_zero_when_everything_validates(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        result = _run(FakeWhoop(invalid_workout=False), tmp_path / "out")

        assert result["code"] == 0
        assert result["report"]["summary"]["fail"] == 0
        assert result["report"]["summary"]["exit_code"] == 0
        # Spec-typed data produces no type-mismatch false positives.
        assert not any("coercion" in line for line in result["report"]["anomalies"])
        for entry in result["report"]["endpoints"].values():
            assert entry.get("type_mismatches", []) == []

    def test_exit_one_on_http_error(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        fake = FakeWhoop(
            invalid_workout=False,
            fail_path=f"/developer/v2/cycle/{CYCLE_IDS[0]}/recovery",
        )
        result = _run(fake, tmp_path / "out")
        recovery = result["report"]["endpoints"]["recovery_for_cycle"]

        assert result["code"] == 1
        assert recovery["status"] == "fail"
        assert recovery["http_error_status"] == "500"
        assert recovery["sdk_exception"] == "WhoopAPIError"
        assert recovery["notes"][0] == "HTTP 500 (WhoopAPIError)"

    def test_optional_endpoints_may_be_skipped(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        result = _run(FakeWhoop(workouts=False, v1_ids=False), tmp_path / "out")
        endpoints = result["report"]["endpoints"]

        assert result["code"] == 0
        assert endpoints["workout"]["status"] == "skipped"
        assert endpoints["workout"]["required"] is False
        assert endpoints["activity_mapping"]["status"] == "skipped"
        assert endpoints["activity_mapping"]["required"] is False
        assert endpoints["workout_collection"]["status"] == "ok"
        assert endpoints["workout_collection"]["records"] == 0

    def test_exit_one_when_sign_in_fails(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def failing_sign_in(client: WhoopClient) -> None:
            raise RuntimeError("consent denied")

        out = tmp_path / "out"
        code = live_check.main(
            ["--out", str(out)],
            transport=httpx.MockTransport(FakeWhoop().handler),
            authenticate=failing_sign_in,
        )

        assert code == 1
        assert not out.exists()
        assert "Sign-in failed" in capsys.readouterr().err

    @pytest.mark.parametrize("inside", ["repo", "repo-root", "other-git-tree"])
    def test_out_inside_a_git_working_tree_is_refused(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
        capsys: pytest.CaptureFixture[str], inside: str,
    ) -> None:
        if inside == "repo":
            out = REPO_ROOT / "live-check-must-not-exist"
        elif inside == "repo-root":
            out = REPO_ROOT
        else:
            (tmp_path / "project" / ".git").mkdir(parents=True)
            out = tmp_path / "project" / "data" / "live-check"

        code = live_check.main(
            ["--out", str(out)],
            transport=httpx.MockTransport(FakeWhoop().handler),
            authenticate=_fake_sign_in({}),
        )

        assert code == 2
        assert "refusing --out" in capsys.readouterr().err
        if inside != "repo-root":
            assert not out.exists()

    def test_token_file_inside_the_repo_is_refused(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        code = live_check.main(
            ["--out", str(tmp_path / "out"), "--token-file", str(REPO_ROOT / "tokens.json")],
            transport=httpx.MockTransport(FakeWhoop().handler),
            authenticate=_fake_sign_in({}),
        )

        assert code == 2
        assert "refusing --token-file" in capsys.readouterr().err
        assert not (tmp_path / "out").exists()

    def test_non_empty_out_is_refused(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        out = tmp_path / "out"
        out.mkdir()
        (out / "existing.txt").write_text("keep me")

        assert _run(FakeWhoop(), out)["code"] == 2
        assert sorted(p.name for p in out.iterdir()) == ["existing.txt"]

    @pytest.mark.parametrize("port", [None, 9123])
    def test_missing_credentials_print_setup_instructions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        guards: Dict[str, List[Any]], capsys: pytest.CaptureFixture[str],
        port: Optional[int],
    ) -> None:
        monkeypatch.delenv("WHOOP_CLIENT_ID", raising=False)
        monkeypatch.delenv("WHOOP_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("WHOOP_REDIRECT_URI", raising=False)
        argv = ["--out", str(tmp_path / "out")]
        if port is not None:
            argv += ["--port", str(port)]

        code = live_check.main(argv, authenticate=_fake_sign_in({}))
        err = capsys.readouterr().err

        assert code == 2
        assert "https://developer.whoop.com" in err
        assert f"http://localhost:{port or 8080}/callback" in err
        for scope in ("offline", "read:profile", "read:recovery", "read:workout"):
            assert scope in err
        assert not (tmp_path / "out").exists()

    @pytest.mark.parametrize(
        "redirect_uri, port",
        [
            ("https://example.com/callback", None),
            ("http://localhost/callback", None),
            ("http://localhost:8080/callback", 9000),
        ],
    )
    def test_unusable_redirect_uri_is_refused(
        self, tmp_path: Path, env: None, monkeypatch: pytest.MonkeyPatch,
        guards: Dict[str, List[Any]], redirect_uri: str, port: Optional[int],
    ) -> None:
        monkeypatch.setenv("WHOOP_REDIRECT_URI", redirect_uri)
        argv = ["--out", str(tmp_path / "out")]
        if port is not None:
            argv += ["--port", str(port)]

        assert live_check.main(argv, authenticate=_fake_sign_in({})) == 2
        assert not (tmp_path / "out").exists()


class TestHelpers:
    """Smaller pieces of the script."""

    def test_default_out_dir(self) -> None:
        path = live_check.default_out_dir(datetime(2026, 10, 6, 19, 5, 7))
        assert path == Path.home() / "Projects" / "whoop-research" / "live-check-20261006-190507"

    def test_sdk_log_levels_are_restored(
        self, tmp_path: Path, env: None, guards: Dict[str, List[Any]],
    ) -> None:
        logger = logging.getLogger("strapkit.client")
        before = logger.level
        _run(FakeWhoop(), tmp_path / "out")
        assert logger.level == before

    def test_legacy_alias_key_is_not_reported_as_dropped(self) -> None:
        workout = _workout(WORKOUT_IDS[0])
        workout["score"]["zone_duration"] = workout["score"].pop("zone_durations")
        dropped: Dict[str, int] = {}
        declared: Dict[str, int] = {}

        live_check._walk_model(workout, live_check.Workout, "", dropped, declared)

        assert dropped == {}
        assert declared["score.zone_durations"] == 1

    def test_value_like_keys_are_masked_in_paths(self) -> None:
        raw = {
            "v2_activity_id": SLEEP_IDS[0],
            SLEEP_IDS[1]: {"2026-09-30": 1},
            "2026-09-30T06:01:02.303Z": True,
            EMAIL: 1,
            "12345678": 2,
            "has spaces": 3,
        }
        dropped: Dict[str, int] = {}
        stats = live_check._ShapeStats()

        live_check._walk_model(raw, live_check.ActivityIdMapping, "", dropped, {})
        stats.add(raw)

        expected = {"<uuid>", "<date-time(Z)>", "<email>", "<integer-string>", "<key>"}
        assert set(dropped) == expected
        assert set(stats.report()) == expected | {"v2_activity_id", "<uuid>.<date>"}

    @pytest.mark.parametrize(
        "value, expected",
        [
            (7, 7),
            ("731902841", 731902841),
            (" 42 ", 42),
            (0, None),
            (-3, None),
            ("-3", None),
            (True, None),
            ("abc", None),
            (None, None),
            (1.5, None),
        ],
    )
    def test_int_id(self, value: Any, expected: Optional[int]) -> None:
        assert live_check._int_id(value) == expected

    def test_pick_prefers_scored_closed_records_and_notes_unscored_ones(self) -> None:
        open_cycle = _open_cycle(PENDING_CYCLE_ID)
        scored = _cycle(CYCLE_IDS[0])
        prefs = (live_check._has_score, live_check._is_closed)

        assert live_check._pick([open_cycle, scored], "id", live_check._int_id, prefs) == (
            CYCLE_IDS[0], scored,
        )
        assert live_check._pick([open_cycle], "id", live_check._int_id, prefs) == (
            PENDING_CYCLE_ID, open_cycle,
        )
        assert live_check._pick([], "id", live_check._int_id, prefs) == (None, None)

        check = live_check.EndpointCheck(
            "cycle", "get_cycle(cycle_id)", "GET /developer/v2/cycle/{id}", live_check.Cycle,
        )
        live_check._note_unscored(check, scored)
        assert check.notes == []
        live_check._note_unscored(check, open_cycle)
        assert check.notes == ["no scored record in the window, so score was not checked"]

    @pytest.mark.parametrize(
        "annotation, expected",
        [
            (int, {"integer"}),
            (float, {"integer", "number"}),
            (bool, {"boolean"}),
            (str, {"string"}),
            (datetime, {"string"}),
            (Optional[int], {"integer", "null"}),
            (Literal["SCORED", "PENDING_SCORE"], {"string"}),
            (List[int], {"array"}),
            (Dict[str, int], {"object"}),
            (Optional[live_check.Cycle], {"object", "null"}),
            (Any, None),
        ],
    )
    def test_expected_json_types(self, annotation: Any, expected: Optional[Set[str]]) -> None:
        found = live_check._expected_json_types(annotation)
        assert (set(found) if found is not None else None) == expected

    def test_type_mismatches_flag_coercion_only(self) -> None:
        mismatches: Dict[str, Dict[str, Any]] = {}
        live_check._walk_model(
            {"height_meter": 2, "weight_kilogram": None, "max_heart_rate": "193"},
            live_check.BodyMeasurement, "", {}, {}, mismatches,
        )
        # An integer for a float field and null for an Optional field are fine.
        assert mismatches == {
            "max_heart_rate": {"expected": ["integer", "null"], "types": {"string": 1}},
        }

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("", "empty"),
            (SLEEP_IDS[0], "uuid"),
            ("2026-09-29T03:17:29.111Z", "date-time(Z)"),
            ("2026-09-29T03:17:29-05:00", "date-time(offset)"),
            ("-05:00", "tz-offset"),
            (EMAIL, "email"),
            ("12345", "integer-string"),
            ("SCORED", "enum-like"),
            ("rowing", "text"),
        ],
    )
    def test_string_format(self, value: str, expected: str) -> None:
        assert live_check._string_format(value) == expected
