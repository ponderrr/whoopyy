#!/usr/bin/env python3
"""
Async usage example for WhoopYY SDK.

Demonstrates:
- Using AsyncWhoopClient for concurrent requests
- Fetching multiple data types simultaneously
- Async iteration over records

Prerequisites:
    Set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET environment variables.

Usage:
    python async_example.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from whoopyy import AsyncWhoopClient


async def fetch_all_data_concurrently(client: AsyncWhoopClient) -> None:
    """
    Fetch multiple data types concurrently.
    
    This demonstrates the main advantage of the async client -
    fetching different data types in parallel.
    """
    print("\n2. Fetching data concurrently...")
    
    # Fetch profile, recovery, sleep, and workouts all at once
    profile_task = client.get_profile_basic()
    recovery_task = client.get_recovery_collection(limit=7)
    sleep_task = client.get_sleep_collection(limit=7)
    workout_task = client.get_workout_collection(limit=5)
    
    # Wait for all requests to complete
    profile, recoveries, sleeps, workouts = await asyncio.gather(
        profile_task,
        recovery_task,
        sleep_task,
        workout_task,
    )
    
    print(f"   ✓ Fetched all data concurrently!")
    print(f"   - Profile: {profile.first_name} {profile.last_name}")
    print(f"   - Recoveries: {len(recoveries.records)} records")
    print(f"   - Sleeps: {len(sleeps.records)} records")
    print(f"   - Workouts: {len(workouts.records)} records")
    
    return profile, recoveries, sleeps, workouts


async def demonstrate_async_iteration(client: AsyncWhoopClient) -> None:
    """
    Demonstrate async iteration over records.
    
    Useful for processing large datasets without loading
    everything into memory at once.
    """
    print("\n3. Async iteration over recovery records...")
    
    count = 0
    async for recovery in client.iter_recovery():
        if recovery.score:
            print(f"   {recovery.created_at.date()}: "
                  f"{recovery.score.recovery_score:.0f}%")
        count += 1
        
        # Limit for demo purposes
        if count >= 5:
            print("   (showing first 5 records)")
            break


async def main() -> None:
    """Run async example."""
    
    client_id = os.getenv("WHOOP_CLIENT_ID")
    client_secret = os.getenv("WHOOP_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print("Error: Please set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET")
        sys.exit(1)
    
    print("=" * 60)
    print("WhoopYY Async Usage Example")
    print("=" * 60)
    
    # Use async context manager
    async with AsyncWhoopClient(
        client_id=client_id,
        client_secret=client_secret,
    ) as client:
        
        # Authentication is still synchronous (requires browser)
        print("\n1. Authenticating...")
        try:
            client.authenticate()
            print("   ✓ Authentication successful!")
        except Exception as e:
            print(f"   Error: {e}")
            return
        
        # Demonstrate concurrent fetching
        await fetch_all_data_concurrently(client)
        
        # Demonstrate async iteration
        await demonstrate_async_iteration(client)
    
    print("\n" + "=" * 60)
    print("Async example complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
