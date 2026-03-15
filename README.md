<p align="center">
  <h1 align="center">WhoopYY</h1>
  <p align="center">
    <strong>The Complete Python SDK for the Whoop API</strong>
  </p>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+"></a>
  <a href="https://github.com/ponderrr/whoopyy/actions"><img src="https://img.shields.io/badge/build-passing-brightgreen.svg" alt="Build Status"></a>
  <a href="https://codecov.io/gh/ponderrr/whoopyy"><img src="https://img.shields.io/badge/coverage-95%25-brightgreen.svg" alt="Coverage"></a>
  <a href="https://github.com/ponderrr/whoopyy/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Proprietary-red.svg" alt="License: Proprietary"></a>
  <a href="https://pypi.org/project/whoopyy/"><img src="https://img.shields.io/badge/pypi-v0.1.0-blue.svg" alt="PyPI"></a>
  <a href="http://mypy-lang.org/"><img src="https://img.shields.io/badge/mypy-checked-blue.svg" alt="MyPy"></a>
</p>

<p align="center">
  <em>Type-safe • Async-ready • Production-tested • 360+ tests • Zero type errors</em>
</p>

---

**WhoopYY** is a robust, fully-typed Python SDK for the [Whoop API](https://developer.whoop.com). Built for developers who need reliable access to recovery, sleep, strain, and workout data.

```python
from whoopyy import WhoopClient

with WhoopClient(client_id="...", client_secret="...") as client:
    client.authenticate()
    recovery = client.get_recovery_collection(limit=7)
    
    for r in recovery.records:
        print(f"{r.created_at.date()}: {r.score.recovery_score:.0f}% ({r.score.recovery_zone})")
```

## Why WhoopYY?

| Feature | WhoopYY | Raw API |
|---------|---------|---------|
| Type Safety | Full Pydantic models | Manual parsing |
| Token Management | Automatic refresh | Manual handling |
| Pagination | Built-in iterators | Manual implementation |
| Error Handling | Typed exceptions | HTTP codes |
| Rate Limiting | Automatic detection | Manual checking |
| Async Support | Native async client | N/A |

## Installation

```bash
pip install whoopyy
```

**From source:**
```bash
git clone https://github.com/ponderrr/whoopyy.git
cd whoopyy
pip install -e .
```

**Dependencies:** Python 3.9+, [httpx](https://www.python-httpx.org/) (>=0.27.0), [pydantic](https://docs.pydantic.dev/) (>=2.5.0)

## Quick Start

### 1. Get API Credentials

1. Register at [developer.whoop.com](https://developer.whoop.com)
2. Create an application
3. Copy your `client_id` and `client_secret`
4. Set redirect URI to `http://localhost:8080/callback`

### 2. Authenticate

```python
from whoopyy import WhoopClient

client = WhoopClient(
    client_id="your_client_id",
    client_secret="your_client_secret"
)

# Opens browser for OAuth consent
client.authenticate()

# Tokens are cached - subsequent runs skip browser auth
```

### 3. Fetch Data

```python
# User profile
profile = client.get_profile_basic()
print(f"Hello, {profile.first_name}!")  # Hello, John!

# Recovery scores
recovery = client.get_recovery_collection(limit=7)
for r in recovery.records:
    if r.score:
        print(f"Recovery: {r.score.recovery_score:.0f}% | HRV: {r.score.hrv_rmssd_milli:.0f}ms")

# Sleep data
sleep = client.get_sleep_collection(limit=7)
for s in sleep.records:
    if s.score:
        print(f"Sleep: {s.score.total_sleep_duration_hours:.1f}h | Quality: {s.score.sleep_performance_percentage:.0f}%")

# Workouts
workouts = client.get_workout_collection(limit=5)
for w in workouts.records:
    if w.score:
        print(f"{w.sport_display_name}: {w.duration_minutes:.0f}min | Strain: {w.score.strain:.1f}")
```

## Features

### Complete API Coverage

| Endpoint | Methods |
|----------|---------|
| **User Profile** | `get_profile_basic()`, `get_body_measurement()` |
| **Recovery** | `get_recovery_for_cycle()`, `get_recovery_collection()`, `get_all_recovery()`, `iter_recovery()` |
| **Sleep** | `get_sleep()`, `get_sleep_collection()`, `get_all_sleep()`, `iter_sleep()` |
| **Cycles** | `get_cycle()`, `get_cycle_collection()`, `get_all_cycles()`, `iter_cycles()` |
| **Workouts** | `get_workout()`, `get_workout_collection()`, `get_all_workouts()`, `iter_workouts()` |
| **Access** | `revoke_access()` |

### Type-Safe Pydantic Models

Every API response is validated and typed:

```python
recovery = client.get_recovery_for_cycle(cycle_id=12345)

# Full IDE autocomplete and type checking
recovery.score.recovery_score      # float (0-100)
recovery.score.hrv_rmssd_milli     # float
recovery.score.resting_heart_rate  # float
recovery.score.recovery_zone       # str: "green" | "yellow" | "red"
recovery.score.spo2_percentage     # Optional[float]
```

### Automatic Pagination

Fetch all records without manual token handling:

```python
# Get all recovery records (handles pagination automatically)
all_recoveries = client.get_all_recovery(max_records=100)

# Or iterate efficiently with generators
for recovery in client.iter_recovery():
    process(recovery)  # Memory-efficient streaming
```

### Async Client

Concurrent requests for maximum performance:

```python
import asyncio
from whoopyy import AsyncWhoopClient

async def fetch_dashboard():
    async with AsyncWhoopClient(client_id="...", client_secret="...") as client:
        client.authenticate()  # Sync (browser interaction)
        
        # Fetch all data concurrently
        profile, recovery, sleep, workouts = await asyncio.gather(
            client.get_profile_basic(),
            client.get_recovery_collection(limit=7),
            client.get_sleep_collection(limit=7),
            client.get_workout_collection(limit=10),
        )
        
        return profile, recovery, sleep, workouts

data = asyncio.run(fetch_dashboard())
```

### Built-in Export & Analysis

```python
from whoopyy import (
    export_recovery_csv,
    analyze_recovery_trends,
    generate_summary_report,
)

# Export to CSV
recoveries = client.get_all_recovery(max_records=30)
export_recovery_csv(recoveries, "recovery_data.csv")

# Analyze trends
trends = analyze_recovery_trends(recoveries)
print(f"Average Recovery: {trends.average_score:.1f}")
print(f"HRV Stability (CV): {trends.hrv_coefficient_of_variation:.1f}%")
print(f"Green Days: {trends.green_days}/{trends.record_count}")

# Generate report
report = generate_summary_report(recoveries, sleeps, cycles, workouts, output="report.txt")
```

## API Reference

### Client Initialization

```python
from whoopyy import WhoopClient

client = WhoopClient(
    client_id: str,                          # Required - Whoop API client ID
    client_secret: str,                      # Required - Whoop API client secret
    redirect_uri: str = "http://localhost:8080/callback",  # OAuth callback
    scope: Optional[List[str]] = None,       # OAuth scopes (default: all)
    token_file: str = "~/.whoop_tokens.json", # Token cache location (absolute path)
    timeout: float = 30.0,                   # Request timeout (seconds)
)
```

### Recovery Methods

```python
# Single recovery by cycle ID
recovery = client.get_recovery_for_cycle(cycle_id: int) -> Recovery

# Paginated collection
collection = client.get_recovery_collection(
    start: Optional[datetime] = None,   # Filter start date
    end: Optional[datetime] = None,     # Filter end date
    limit: int = 25,                    # Records per page (max 25)
    next_token: Optional[str] = None,   # Pagination token
) -> RecoveryCollection

# All records with auto-pagination
all_records = client.get_all_recovery(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_records: Optional[int] = None,  # Limit total records
) -> List[Recovery]

# Memory-efficient generator
for recovery in client.iter_recovery(start=None, end=None):
    process(recovery)
```

### Sleep Methods

```python
sleep = client.get_sleep(sleep_id: str) -> Sleep

collection = client.get_sleep_collection(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 25,
    next_token: Optional[str] = None,
) -> SleepCollection

all_records = client.get_all_sleep(...) -> List[Sleep]

for sleep in client.iter_sleep(...):
    process(sleep)
```

### Cycle Methods

```python
cycle = client.get_cycle(cycle_id: int) -> Cycle

collection = client.get_cycle_collection(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 25,
    next_token: Optional[str] = None,
) -> CycleCollection

all_records = client.get_all_cycles(...) -> List[Cycle]

for cycle in client.iter_cycles(...):
    process(cycle)
```

### Workout Methods

```python
workout = client.get_workout(workout_id: str) -> Workout

collection = client.get_workout_collection(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 25,
    next_token: Optional[str] = None,
) -> WorkoutCollection

all_records = client.get_all_workouts(...) -> List[Workout]

for workout in client.iter_workouts(...):
    process(workout)
```

## Error Handling

WhoopYY provides a typed exception hierarchy:

```
WhoopError (base)
├── WhoopAuthError        # Authentication failures
│   └── WhoopTokenError   # Token-specific issues
├── WhoopAPIError         # API request failures
│   ├── WhoopNotFoundError     # Resource not found (404)
│   └── WhoopValidationError   # Invalid parameters (400)
├── WhoopRateLimitError   # Rate limited (429)
└── WhoopNetworkError     # Connection issues
```

**Example:**

```python
from whoopyy import WhoopClient
from whoopyy.exceptions import (
    WhoopRateLimitError,
    WhoopAuthError,
    WhoopAPIError,
    is_retryable_error,
)

try:
    data = client.get_recovery_collection()
    
except WhoopRateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after} seconds")
    time.sleep(e.retry_after)
    
except WhoopAuthError:
    print("Re-authentication required")
    client.authenticate()
    
except WhoopAPIError as e:
    if is_retryable_error(e):
        # Network issues, temporary failures
        retry_with_backoff()
    else:
        # Fatal errors
        raise
```

## Data Models

### Recovery

```python
class Recovery:
    cycle_id: int
    sleep_id: str                  # UUID string
    user_id: int
    created_at: datetime
    updated_at: datetime
    score_state: str  # "SCORED" | "PENDING_SCORE" | "UNSCORABLE"
    score: Optional[RecoveryScore]

class RecoveryScore:
    user_calibrating: bool
    recovery_score: float          # 0-100
    resting_heart_rate: float      # bpm
    hrv_rmssd_milli: float         # milliseconds
    spo2_percentage: Optional[float]
    skin_temp_celsius: Optional[float]

    @property
    def recovery_zone(self) -> str:  # "green" | "yellow" | "red"
```

### Sleep

```python
class Sleep:
    id: str                        # UUID string
    cycle_id: int
    user_id: int
    start: datetime
    end: datetime
    nap: bool
    score_state: str  # "SCORED" | "PENDING_SCORE" | "UNSCORABLE"
    score: Optional[SleepScore]

    @property
    def duration_hours(self) -> float

class SleepScore:
    stage_summary: Optional[StageSummary]
    sleep_needed: Optional[SleepNeeded]
    respiratory_rate: Optional[float]
    sleep_performance_percentage: Optional[float]
    sleep_efficiency_percentage: Optional[float]
    sleep_consistency_percentage: Optional[float]

    @property
    def total_sleep_duration_hours(self) -> float
```

### Cycle (Daily Strain)

```python
class Cycle:
    id: int
    user_id: int
    start: datetime
    end: Optional[datetime]
    score_state: str  # "SCORED" | "PENDING_SCORE" | "UNSCORABLE"
    score: Optional[CycleScore]

class CycleScore:
    strain: float              # 0-21 strain scale
    average_heart_rate: int
    max_heart_rate: int
    kilojoule: float

    @property
    def strain_level(self) -> str:  # "Light" | "Moderate" | "Strenuous" | "All Out"
```

### Workout

```python
class Workout:
    id: str                        # UUID string
    user_id: int
    sport_id: int                  # Primary identifier for sport type
    sport_name: Optional[str]      # Not returned by WHOOP API; use sport_id instead
    start: datetime
    end: datetime
    score_state: str  # "SCORED" | "PENDING_SCORE" | "UNSCORABLE"
    score: Optional[WorkoutScore]

    @property
    def sport_display_name(self) -> str  # Human-readable sport name from sport_id
    @property
    def duration_minutes(self) -> float

class WorkoutScore:
    strain: float                   # 0-21
    average_heart_rate: int
    max_heart_rate: int
    kilojoule: float
    percent_recorded: float
    distance_meter: Optional[float]
    altitude_gain_meter: Optional[float]
    zone_duration: Optional[WorkoutZoneDuration]
```

## Advanced Usage

### Environment Variables

```bash
# .env file
WHOOP_CLIENT_ID=your_client_id
WHOOP_CLIENT_SECRET=your_client_secret
```

```python
import os
from whoopyy import WhoopClient

client = WhoopClient(
    client_id=os.environ["WHOOP_CLIENT_ID"],
    client_secret=os.environ["WHOOP_CLIENT_SECRET"],
)
```

### Context Manager

```python
# Automatic resource cleanup
with WhoopClient(client_id="...", client_secret="...") as client:
    client.authenticate()
    data = client.get_recovery_collection()
# Client automatically closed
```

### Date Filtering

```python
from datetime import datetime, timedelta

# Last 30 days
end = datetime.now()
start = end - timedelta(days=30)

recoveries = client.get_recovery_collection(start=start, end=end)

# Also accepts date objects and ISO strings
recoveries = client.get_recovery_collection(
    start="2024-01-01",
    end="2024-01-31"
)
```

### Export Functions

```python
from whoopyy import (
    export_recovery_csv,
    export_sleep_csv,
    export_cycle_csv,
    export_workout_csv,
)

# Export all data types
export_recovery_csv(recoveries, "recovery.csv")
export_sleep_csv(sleeps, "sleep.csv", include_naps=False)
export_cycle_csv(cycles, "cycles.csv")
export_workout_csv(workouts, "workouts.csv")
```

### Trend Analysis

```python
from whoopyy import (
    analyze_recovery_trends,
    analyze_sleep_trends,
    analyze_training_load,
)

# Recovery analysis
recovery_trends = analyze_recovery_trends(recoveries)
print(f"Average: {recovery_trends.average_score:.1f}")
print(f"Green days: {recovery_trends.green_days}")
print(f"HRV CV: {recovery_trends.hrv_coefficient_of_variation:.1f}%")

# Sleep analysis
sleep_trends = analyze_sleep_trends(sleeps, include_naps=False)
print(f"Avg duration: {sleep_trends.average_duration_hours:.1f}h")
print(f"Consistency: {sleep_trends.consistency_score:.0f}%")

# Training load
load_trends = analyze_training_load(cycles, workouts)
print(f"Weekly strain: {load_trends.total_strain:.1f}")
print(f"High strain days: {load_trends.high_strain_days}")
```

## Testing

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# With coverage
pytest tests/ --cov=whoopyy --cov-report=html

# Type checking
mypy whoopyy/
```

**Test Statistics:**
- 360+ tests across 10+ modules
- 90%+ code coverage
- MyPy: 0 errors

## Examples

See the [`examples/`](examples/) directory:

| Example | Description |
|---------|-------------|
| [`basic_usage.py`](examples/basic_usage.py) | Authentication and basic data fetching |
| [`async_example.py`](examples/async_example.py) | Concurrent requests with AsyncWhoopClient |
| [`data_export.py`](examples/data_export.py) | CSV export and trend analysis |

## Security

Access tokens and refresh tokens are stored as plaintext JSON at `~/.whoop_tokens.json`. The SDK sets file permissions to `600` automatically. Do not commit this file. On multi-user systems, consider using a secrets manager.

## License

**Proprietary License** - All Rights Reserved. See [LICENSE](LICENSE) for details.

This software is provided for viewing purposes only. No use, copying, modification, distribution, or reference to this code is permitted without explicit written permission.

## Acknowledgments

- Powered by [httpx](https://www.python-httpx.org/) and [Pydantic](https://docs.pydantic.dev/)

---

<p align="center">
  <strong>WhoopYY</strong> — Professional Python SDK for Whoop API<br>
  <a href="https://developer.whoop.com">API Docs</a> •
  <a href="https://github.com/ponderrr/whoopyy/issues">Report Bug</a> •
  <a href="https://github.com/ponderrr/whoopyy/discussions">Discussions</a>
</p>

<p align="center">
  <sub>This is an unofficial SDK. WHOOP® is a registered trademark of WHOOP, Inc.</sub>
</p>
