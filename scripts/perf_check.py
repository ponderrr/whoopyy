"""Quick perf sanity check — not a benchmark, just verifies optimizations don't regress."""

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone

from whoopyy import AsyncWhoopClient
from whoopyy.auth import OAuthHandler


async def main() -> None:
    auth = OAuthHandler(
        client_id=os.environ["WHOOP_CLIENT_ID"],
        client_secret=os.environ["WHOOP_CLIENT_SECRET"],
    )
    auth._tokens = {
        "access_token": os.environ["WHOOP_ACCESS_TOKEN"],
        "refresh_token": os.environ["WHOOP_REFRESH_TOKEN"],
        "expires_in": 3600,
        "expires_at": time.time() + 3600,
        "token_type": "Bearer",
        "scope": "offline",
    }

    async with AsyncWhoopClient(
        client_id=os.environ["WHOOP_CLIENT_ID"],
        client_secret=os.environ["WHOOP_CLIENT_SECRET"],
    ) as client:
        client.auth = auth
        client._authenticated = True

        # Parallel fetch
        start = time.perf_counter()
        data = await client.fetch_all(limit=5)
        elapsed = time.perf_counter() - start
        print(f"fetch_all() parallel: {elapsed:.2f}s")
        for key, val in data.items():
            count = len(val.records) if val and hasattr(val, "records") else 0
            print(f"  {key}: {count} records")

        # Dashboard fetch
        start = time.perf_counter()
        dash = await client.fetch_dashboard()
        elapsed = time.perf_counter() - start
        print(f"fetch_dashboard(): {elapsed:.2f}s")
        for key, val in dash.items():
            print(f"  {key}: {type(val).__name__ if val else 'None'}")


if __name__ == "__main__":
    asyncio.run(main())
