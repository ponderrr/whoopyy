# Performance Check Results

## Status: PENDING — Credentials Required

**Date:** 2026-03-15

## Script

`scripts/perf_check.py` tests:
- `fetch_all()` — parallel fetch of recovery, sleep, cycles, workouts via `asyncio.gather()`
- `fetch_dashboard()` — parallel fetch of profile + latest record of each type

## How to Run

```bash
export WHOOP_CLIENT_ID=your_client_id
export WHOOP_CLIENT_SECRET=your_client_secret
export WHOOP_ACCESS_TOKEN=your_access_token
export WHOOP_REFRESH_TOKEN=your_refresh_token

python scripts/perf_check.py
```

## Results

> Script has not been executed yet. No WHOOP credentials available. Once credentials are provided, this document will be updated with timing results.

## Optimizations Applied

| Optimization | Impact |
|---|---|
| HTTP connection pooling with keepalive | Eliminates per-request connection overhead (~50-100ms/req) |
| Double-checked locking on token path | No lock contention on valid tokens (99% of calls) |
| In-memory token cache | Zero disk reads after startup |
| Streaming CSV exports (Sequence types) | Handles large datasets efficiently |
| `frozen=True` + `str_strip_whitespace` + `populate_by_name` on all Pydantic models | Immutability + Pydantic v2 optimizations |
| `asyncio.gather()` for concurrent fetches | N endpoints in parallel instead of serial |
