#!/usr/bin/env python3
"""
Basic usage example for WhoopYY SDK.

Demonstrates:
- Authentication with OAuth
- Fetching user profile
- Getting recovery, sleep, and workout data
- Using context managers for cleanup

Prerequisites:
    1. Create a .env file with your credentials:
       WHOOP_CLIENT_ID=your_client_id
       WHOOP_CLIENT_SECRET=your_client_secret
    
    2. Or set environment variables directly

Usage:
    python basic_usage.py
"""

import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import WhoopYY
from whoopyy import WhoopClient


def main() -> None:
    """Run basic usage example."""
    
    # Get credentials from environment
    client_id = os.getenv("WHOOP_CLIENT_ID")
    client_secret = os.getenv("WHOOP_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print("Error: Please set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET")
        print("You can create a .env file or set environment variables")
        sys.exit(1)
    
    print("=" * 60)
    print("WhoopYY Basic Usage Example")
    print("=" * 60)
    
    # Use context manager for automatic cleanup
    with WhoopClient(
        client_id=client_id,
        client_secret=client_secret,
    ) as client:
        
        # Authenticate (opens browser for OAuth flow)
        print("\n1. Authenticating...")
        try:
            client.authenticate()
            print("   ✓ Authentication successful!")
        except Exception as e:
            print(f"   Authentication error: {e}")
            print("   (If you have cached tokens, we'll try to use those)")
        
        # Get user profile
        print("\n2. Fetching user profile...")
        try:
            profile = client.get_profile_basic()
            print(f"   ✓ Hello, {profile.first_name} {profile.last_name}!")
            print(f"   User ID: {profile.user_id}")
            print(f"   Email: {profile.email}")
        except Exception as e:
            print(f"   Error: {e}")
            return
        
        # Get body measurements
        print("\n3. Fetching body measurements...")
        try:
            body = client.get_body_measurement()
            print(f"   Height: {body.height_meter:.2f}m ({body.height_feet:.1f}ft)")
            print(f"   Weight: {body.weight_kilogram:.1f}kg ({body.weight_pounds:.1f}lbs)")
            print(f"   Max HR: {body.max_heart_rate} bpm")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Get recent recovery data
        print("\n4. Fetching last 7 days of recovery...")
        try:
            recovery_collection = client.get_recovery_collection(limit=7)
            
            for recovery in recovery_collection.records:
                if recovery.score:
                    zone = recovery.score.recovery_zone.upper()
                    score = recovery.score.recovery_score
                    hrv = recovery.score.hrv_rmssd_milli
                    rhr = recovery.score.resting_heart_rate
                    
                    print(f"   {recovery.created_at.date()}: "
                          f"{score:.0f}% ({zone}) | "
                          f"HRV: {hrv:.1f}ms | RHR: {rhr}bpm")
                else:
                    print(f"   {recovery.created_at.date()}: Pending score")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Get recent sleep data
        print("\n5. Fetching last 7 days of sleep...")
        try:
            sleep_collection = client.get_sleep_collection(limit=7)
            
            for sleep in sleep_collection.records:
                if sleep.score and not sleep.nap:
                    duration = sleep.score.total_sleep_duration_hours
                    performance = sleep.score.sleep_performance_percentage
                    efficiency = sleep.score.sleep_efficiency_percentage
                    
                    print(f"   {sleep.start.date()}: "
                          f"{duration:.1f}h | "
                          f"Performance: {performance:.0f}% | "
                          f"Efficiency: {efficiency:.0f}%")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Get recent workouts
        print("\n6. Fetching recent workouts...")
        try:
            workout_collection = client.get_workout_collection(limit=5)
            
            if workout_collection.records:
                for workout in workout_collection.records:
                    if workout.score:
                        sport = workout.sport_name
                        strain = workout.score.strain
                        duration = workout.duration_minutes or 0
                        
                        print(f"   {workout.start.date()}: "
                              f"{sport} | "
                              f"{duration:.0f}min | "
                              f"Strain: {strain:.1f}")
            else:
                print("   No recent workouts found")
        except Exception as e:
            print(f"   Error: {e}")
    
    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
