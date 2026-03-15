# Integration Test Results

## Status: PENDING — Credentials Required

**Date:** 2026-03-15

## Test Suite

The comprehensive integration test suite has been written in `tests/integration/test_real_api.py` with 17 test methods across 7 test classes:

| Class | Tests | Description |
|-------|-------|-------------|
| TestProfile | 2 | Profile basic + body measurement |
| TestRecovery | 3 | Collection, scored fields, recovery-for-cycle |
| TestCycles | 3 | Collection, scored fields, single cycle |
| TestSleep | 4 | Collection, scored fields, nap filtering, single sleep |
| TestWorkouts | 3 | Collection, scored fields, single workout |
| TestPagination | 2 | Next token cursor, multi-page get_all |
| TestExport | 3 | Cycle/sleep/workout CSV export |

## How to Run

```bash
export WHOOP_CLIENT_ID=your_client_id
export WHOOP_CLIENT_SECRET=your_client_secret
export WHOOP_ACCESS_TOKEN=your_access_token
export WHOOP_REFRESH_TOKEN=your_refresh_token

pytest tests/integration/ -v --tb=long
```

## Results

> Tests have not been executed yet. No `~/.whoop_tokens.json` file found and no WHOOP environment variables are set. Once credentials are provided, this document will be updated with full pass/fail results.

## Notes

- All tests are skipped by default when `WHOOP_REFRESH_TOKEN` is not set
- Workout tests use `pytest.skip()` if no workout data exists (legitimate skip, not error masking)
- If `WHOOP_ACCESS_TOKEN` is not provided, the client will attempt an automatic refresh using the refresh token
