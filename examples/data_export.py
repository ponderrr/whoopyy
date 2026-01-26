#!/usr/bin/env python3
"""
Data export and analysis example for WhoopYY SDK.

Demonstrates:
- Exporting data to CSV files
- Analyzing recovery, sleep, and training trends
- Generating summary reports

Prerequisites:
    Set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET environment variables.

Usage:
    python data_export.py
"""

import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from whoopyy import (
    WhoopClient,
    export_recovery_csv,
    export_sleep_csv,
    export_cycle_csv,
    export_workout_csv,
    analyze_recovery_trends,
    analyze_sleep_trends,
    analyze_training_load,
    generate_summary_report,
)


def export_to_csv(client: WhoopClient, output_dir: str = ".") -> None:
    """Export Whoop data to CSV files."""
    print("\n" + "-" * 60)
    print("EXPORTING DATA TO CSV")
    print("-" * 60)
    
    # Fetch data
    print("\nFetching data...")
    recoveries = client.get_all_recovery(max_records=30)
    sleeps = client.get_all_sleep(max_records=30)
    cycles = client.get_all_cycles(max_records=30)
    workouts = client.get_all_workouts(max_records=50)
    
    print(f"   Retrieved {len(recoveries)} recovery records")
    print(f"   Retrieved {len(sleeps)} sleep records")
    print(f"   Retrieved {len(cycles)} cycle records")
    print(f"   Retrieved {len(workouts)} workout records")
    
    # Export to CSV
    print("\nExporting to CSV files...")
    
    recovery_count = export_recovery_csv(
        recoveries, 
        f"{output_dir}/recovery_data.csv"
    )
    print(f"   ✓ recovery_data.csv ({recovery_count} records)")
    
    sleep_count = export_sleep_csv(
        sleeps, 
        f"{output_dir}/sleep_data.csv",
        include_naps=False
    )
    print(f"   ✓ sleep_data.csv ({sleep_count} records)")
    
    cycle_count = export_cycle_csv(
        cycles, 
        f"{output_dir}/cycle_data.csv"
    )
    print(f"   ✓ cycle_data.csv ({cycle_count} records)")
    
    workout_count = export_workout_csv(
        workouts, 
        f"{output_dir}/workout_data.csv"
    )
    print(f"   ✓ workout_data.csv ({workout_count} records)")
    
    return recoveries, sleeps, cycles, workouts


def analyze_trends(recoveries, sleeps, cycles, workouts) -> None:
    """Analyze trends in Whoop data."""
    print("\n" + "-" * 60)
    print("TREND ANALYSIS")
    print("-" * 60)
    
    # Recovery trends
    print("\n📊 RECOVERY TRENDS")
    try:
        recovery_trends = analyze_recovery_trends(recoveries)
        
        print(f"   Average Score: {recovery_trends.average_score:.1f}")
        print(f"   Range: {recovery_trends.min_score:.1f} - {recovery_trends.max_score:.1f}")
        print(f"   Average HRV: {recovery_trends.average_hrv:.1f} ms")
        print(f"   HRV Stability (CV): {recovery_trends.hrv_coefficient_of_variation:.1f}%")
        print(f"\n   Zone Distribution:")
        print(f"      Green (>=67): {recovery_trends.green_days} days")
        print(f"      Yellow (34-66): {recovery_trends.yellow_days} days")
        print(f"      Red (<34): {recovery_trends.red_days} days")
        
        if recovery_trends.recent_trend != 0:
            trend = "+" if recovery_trends.recent_trend > 0 else ""
            print(f"\n   Recent Trend: {trend}{recovery_trends.recent_trend:.1f}")
    except ValueError as e:
        print(f"   Could not analyze: {e}")
    
    # Sleep trends
    print("\n💤 SLEEP TRENDS")
    try:
        sleep_trends = analyze_sleep_trends(sleeps, include_naps=False)
        
        print(f"   Average Duration: {sleep_trends.average_duration_hours:.1f} hours")
        print(f"   Average Performance: {sleep_trends.average_performance:.0f}%")
        print(f"   Average Efficiency: {sleep_trends.average_efficiency:.0f}%")
        print(f"   Sleep Consistency: {sleep_trends.consistency_score:.0f}%")
        print(f"   Nights <7 hours: {sleep_trends.nights_below_7h}")
    except ValueError as e:
        print(f"   Could not analyze: {e}")
    
    # Training load trends
    print("\n🏋️ TRAINING LOAD TRENDS")
    try:
        load_trends = analyze_training_load(cycles, workouts)
        
        print(f"   Total Strain (period): {load_trends.total_strain:.1f}")
        print(f"   Average Daily Strain: {load_trends.average_daily_strain:.1f}")
        print(f"   Max Daily Strain: {load_trends.max_strain:.1f}")
        print(f"\n   Strain Distribution:")
        print(f"      Low (<10): {load_trends.low_strain_days} days")
        print(f"      Moderate (10-14): {load_trends.moderate_strain_days} days")
        print(f"      High (>=14): {load_trends.high_strain_days} days")
        print(f"\n   Workouts: {load_trends.workout_count}")
        print(f"   Total Workout Time: {load_trends.total_workout_minutes:.0f} minutes")
    except ValueError as e:
        print(f"   Could not analyze: {e}")


def create_report(recoveries, sleeps, cycles, workouts, output_dir: str = ".") -> None:
    """Generate a summary report."""
    print("\n" + "-" * 60)
    print("GENERATING SUMMARY REPORT")
    print("-" * 60)
    
    report_path = f"{output_dir}/whoop_report.txt"
    
    report = generate_summary_report(
        recoveries, 
        sleeps, 
        cycles, 
        workouts,
        output=report_path
    )
    
    print(f"\n✓ Report saved to: {report_path}")
    print("\nReport Preview:")
    print("-" * 40)
    
    # Show first 30 lines of report
    lines = report.split("\n")[:30]
    for line in lines:
        print(line)
    
    if len(report.split("\n")) > 30:
        print("...")
        print(f"(Full report in {report_path})")


def main() -> None:
    """Run data export example."""
    
    client_id = os.getenv("WHOOP_CLIENT_ID")
    client_secret = os.getenv("WHOOP_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print("Error: Please set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET")
        sys.exit(1)
    
    print("=" * 60)
    print("WhoopYY Data Export Example")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    with WhoopClient(
        client_id=client_id,
        client_secret=client_secret,
    ) as client:
        
        # Authenticate
        print("\nAuthenticating...")
        try:
            client.authenticate()
            print("✓ Authentication successful!")
        except Exception as e:
            print(f"Error: {e}")
            return
        
        # Export data
        recoveries, sleeps, cycles, workouts = export_to_csv(client)
        
        # Analyze trends
        analyze_trends(recoveries, sleeps, cycles, workouts)
        
        # Generate report
        create_report(recoveries, sleeps, cycles, workouts)
    
    print("\n" + "=" * 60)
    print("Export complete!")
    print("=" * 60)
    print("\nFiles created:")
    print("  • recovery_data.csv")
    print("  • sleep_data.csv")
    print("  • cycle_data.csv")
    print("  • workout_data.csv")
    print("  • whoop_report.txt")


if __name__ == "__main__":
    main()
