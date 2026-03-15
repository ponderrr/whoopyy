"""
Data export and analysis utilities for Whoop data.

This module provides tools for exporting Whoop data to various formats
and performing trend analysis on recovery, sleep, and workout metrics.

Features:
    - CSV export for recovery, sleep, cycle, and workout data
    - Trend analysis with moving averages
    - Recovery zone statistics
    - Training load analysis
    - Sleep quality metrics

Example:
    >>> from whoopyy import WhoopClient
    >>> from whoopyy.export import (
    ...     export_recovery_csv,
    ...     export_sleep_csv,
    ...     analyze_recovery_trends,
    ... )
    >>> 
    >>> with WhoopClient(...) as client:
    ...     client.authenticate()
    ...     recoveries = client.get_all_recovery(max_records=30)
    ...     
    ...     # Export to CSV
    ...     export_recovery_csv(recoveries, "recovery.csv")
    ...     
    ...     # Analyze trends
    ...     trends = analyze_recovery_trends(recoveries)
    ...     print(f"Average recovery: {trends['average_score']:.1f}")
"""

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO, Union

from .constants import (
    RECOVERY_GREEN_THRESHOLD,
    RECOVERY_YELLOW_THRESHOLD,
)
from .logger import get_logger
from .models import (
    Cycle,
    Recovery,
    Sleep,
    Workout,
)

logger = get_logger(__name__)


# =============================================================================
# Data Classes for Analysis Results
# =============================================================================

@dataclass
class RecoveryTrends:
    """
    Recovery trend analysis results.
    
    Attributes:
        average_score: Mean recovery score across all records.
        min_score: Minimum recovery score.
        max_score: Maximum recovery score.
        average_hrv: Mean HRV (RMSSD in milliseconds).
        average_resting_hr: Mean resting heart rate.
        green_days: Number of days in green zone (>=67).
        yellow_days: Number of days in yellow zone (34-66).
        red_days: Number of days in red zone (<34).
        hrv_coefficient_of_variation: HRV stability metric (lower is better).
        recent_trend: Comparison of recent vs older average.
        record_count: Total number of records analyzed.
    """
    
    average_score: float
    min_score: float
    max_score: float
    average_hrv: float
    average_resting_hr: float
    green_days: int
    yellow_days: int
    red_days: int
    hrv_coefficient_of_variation: float
    recent_trend: float
    record_count: int


@dataclass
class SleepTrends:
    """
    Sleep trend analysis results.
    
    Attributes:
        average_duration_hours: Mean total sleep duration.
        average_performance: Mean sleep performance percentage.
        average_efficiency: Mean sleep efficiency percentage.
        average_respiratory_rate: Mean respiratory rate.
        consistency_score: Sleep time consistency (0-100).
        nights_below_7h: Number of nights with <7 hours sleep.
        nap_count: Number of naps in the period.
        record_count: Total number of records analyzed.
    """
    
    average_duration_hours: float
    average_performance: float
    average_efficiency: float
    average_respiratory_rate: float
    consistency_score: float
    nights_below_7h: int
    nap_count: int
    record_count: int


@dataclass
class TrainingLoadTrends:
    """
    Training load trend analysis results.
    
    Attributes:
        total_strain: Sum of all strain scores.
        average_daily_strain: Mean daily strain.
        max_strain: Maximum single-day strain.
        low_strain_days: Days with strain <10.
        moderate_strain_days: Days with strain 10-14.
        high_strain_days: Days with strain >=14.
        workout_count: Total workout count.
        total_workout_minutes: Total workout duration.
        record_count: Total number of records analyzed.
    """
    
    total_strain: float
    average_daily_strain: float
    max_strain: float
    low_strain_days: int
    moderate_strain_days: int
    high_strain_days: int
    workout_count: int
    total_workout_minutes: float
    record_count: int


# =============================================================================
# CSV Export Functions
# =============================================================================

def export_recovery_csv(
    recoveries: List[Recovery],
    filepath: Union[str, Path],
    include_unscored: bool = False,
) -> int:
    """
    Export recovery data to CSV file.
    
    Args:
        recoveries: List of Recovery records to export.
        filepath: Output file path.
        include_unscored: Whether to include records without scores.
    
    Returns:
        Number of records exported.
    
    Example:
        >>> recoveries = client.get_all_recovery(max_records=30)
        >>> count = export_recovery_csv(recoveries, "recovery.csv")
        >>> print(f"Exported {count} records")
    """
    if not recoveries:
        logger.warning("No recovery records to export")
        return 0
    
    # Filter to scored if requested
    records = recoveries if include_unscored else [r for r in recoveries if r.score]
    
    if not records:
        logger.warning("No scored recovery records to export")
        return 0
    
    filepath = Path(filepath)
    
    logger.info(
        "Exporting recovery data to CSV",
        extra={"filepath": str(filepath), "record_count": len(records)}
    )
    
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Header row
        writer.writerow([
            "Date",
            "Recovery Score",
            "Recovery Zone",
            "HRV (ms)",
            "Resting HR (bpm)",
            "SpO2 (%)",
            "Skin Temp (°C)",
            "User Calibrating",
            "Cycle ID",
            "Sleep ID",
            "Score State",
        ])
        
        # Data rows
        for recovery in records:
            if recovery.score:
                writer.writerow([
                    recovery.created_at.date().isoformat(),
                    recovery.score.recovery_score,
                    recovery.score.recovery_zone,
                    recovery.score.hrv_rmssd_milli,
                    recovery.score.resting_heart_rate,
                    recovery.score.spo2_percentage or "",
                    recovery.score.skin_temp_celsius or "",
                    recovery.score.user_calibrating,
                    recovery.cycle_id,
                    recovery.sleep_id,
                    recovery.score_state,
                ])
            else:
                writer.writerow([
                    recovery.created_at.date().isoformat(),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    recovery.cycle_id,
                    recovery.sleep_id,
                    recovery.score_state,
                ])
    
    logger.info(f"Exported {len(records)} recovery records to {filepath}")
    return len(records)


def export_sleep_csv(
    sleeps: List[Sleep],
    filepath: Union[str, Path],
    include_unscored: bool = False,
    include_naps: bool = True,
) -> int:
    """
    Export sleep data to CSV file.
    
    Args:
        sleeps: List of Sleep records to export.
        filepath: Output file path.
        include_unscored: Whether to include records without scores.
        include_naps: Whether to include naps (default True).
    
    Returns:
        Number of records exported.
    
    Example:
        >>> sleeps = client.get_all_sleep(max_records=30)
        >>> count = export_sleep_csv(sleeps, "sleep.csv", include_naps=False)
    """
    if not sleeps:
        logger.warning("No sleep records to export")
        return 0
    
    # Filter records
    records = sleeps
    if not include_unscored:
        records = [s for s in records if s.score]
    if not include_naps:
        records = [s for s in records if not s.nap]
    
    if not records:
        logger.warning("No sleep records to export after filtering")
        return 0
    
    filepath = Path(filepath)
    
    logger.info(
        "Exporting sleep data to CSV",
        extra={"filepath": str(filepath), "record_count": len(records)}
    )
    
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Header row
        writer.writerow([
            "Date",
            "Start Time",
            "End Time",
            "Duration (hours)",
            "Total Sleep (hours)",
            "Sleep Performance (%)",
            "Sleep Efficiency (%)",
            "Respiratory Rate (bpm)",
            "Light Sleep (hours)",
            "SWS/Deep Sleep (hours)",
            "REM Sleep (hours)",
            "Awake Time (hours)",
            "Is Nap",
            "Score State",
        ])
        
        # Data rows
        for sleep in records:
            if sleep.score:
                stages = sleep.score.stage_summary
                ms_to_hours = 1 / (1000 * 60 * 60)

                light = (stages.total_light_sleep_time_milli or 0) * ms_to_hours if stages else 0
                deep = (stages.total_slow_wave_sleep_time_milli or 0) * ms_to_hours if stages else 0
                rem = (stages.total_rem_sleep_time_milli or 0) * ms_to_hours if stages else 0
                awake = (stages.total_awake_time_milli or 0) * ms_to_hours if stages else 0

                writer.writerow([
                    sleep.start.date().isoformat(),
                    sleep.start.time().isoformat(),
                    sleep.end.time().isoformat() if sleep.end else "",
                    f"{sleep.duration_hours:.2f}" if sleep.duration_hours else "",
                    f"{sleep.score.total_sleep_duration_hours:.2f}",
                    f"{sleep.score.sleep_performance_percentage:.1f}" if sleep.score.sleep_performance_percentage is not None else "",
                    f"{sleep.score.sleep_efficiency_percentage:.1f}" if sleep.score.sleep_efficiency_percentage is not None else "",
                    f"{sleep.score.respiratory_rate:.1f}" if sleep.score.respiratory_rate is not None else "",
                    f"{light:.2f}",
                    f"{deep:.2f}",
                    f"{rem:.2f}",
                    f"{awake:.2f}",
                    sleep.nap,
                    sleep.score_state,
                ])
            else:
                writer.writerow([
                    sleep.start.date().isoformat(),
                    sleep.start.time().isoformat(),
                    sleep.end.time().isoformat() if sleep.end else "",
                    f"{sleep.duration_hours:.2f}" if sleep.duration_hours else "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    sleep.nap,
                    sleep.score_state,
                ])
    
    logger.info(f"Exported {len(records)} sleep records to {filepath}")
    return len(records)


def export_cycle_csv(
    cycles: List[Cycle],
    filepath: Union[str, Path],
    include_unscored: bool = False,
) -> int:
    """
    Export cycle (strain) data to CSV file.
    
    Args:
        cycles: List of Cycle records to export.
        filepath: Output file path.
        include_unscored: Whether to include records without scores.
    
    Returns:
        Number of records exported.
    """
    if not cycles:
        logger.warning("No cycle records to export")
        return 0
    
    records = cycles if include_unscored else [c for c in cycles if c.score]
    
    if not records:
        logger.warning("No scored cycle records to export")
        return 0
    
    filepath = Path(filepath)
    
    logger.info(
        "Exporting cycle data to CSV",
        extra={"filepath": str(filepath), "record_count": len(records)}
    )
    
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Header row
        writer.writerow([
            "Date",
            "Start",
            "End",
            "Strain Score",
            "Average HR (bpm)",
            "Max HR (bpm)",
            "Kilojoules",
            "Score State",
        ])
        
        # Data rows
        for cycle in records:
            if cycle.score:
                writer.writerow([
                    cycle.start.date().isoformat(),
                    cycle.start.isoformat(),
                    cycle.end.isoformat() if cycle.end else "",
                    f"{cycle.score.strain:.1f}",
                    cycle.score.average_heart_rate,
                    cycle.score.max_heart_rate,
                    f"{cycle.score.kilojoule:.1f}",
                    cycle.score_state,
                ])
            else:
                writer.writerow([
                    cycle.start.date().isoformat(),
                    cycle.start.isoformat(),
                    cycle.end.isoformat() if cycle.end else "",
                    "",
                    "",
                    "",
                    "",
                    cycle.score_state,
                ])
    
    logger.info(f"Exported {len(records)} cycle records to {filepath}")
    return len(records)


def export_workout_csv(
    workouts: List[Workout],
    filepath: Union[str, Path],
    include_unscored: bool = False,
) -> int:
    """
    Export workout data to CSV file.
    
    Args:
        workouts: List of Workout records to export.
        filepath: Output file path.
        include_unscored: Whether to include records without scores.
    
    Returns:
        Number of records exported.
    
    Example:
        >>> workouts = client.get_all_workouts(max_records=100)
        >>> count = export_workout_csv(workouts, "workouts.csv")
    """
    if not workouts:
        logger.warning("No workout records to export")
        return 0
    
    records = workouts if include_unscored else [w for w in workouts if w.score]
    
    if not records:
        logger.warning("No scored workout records to export")
        return 0
    
    filepath = Path(filepath)
    
    logger.info(
        "Exporting workout data to CSV",
        extra={"filepath": str(filepath), "record_count": len(records)}
    )
    
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Header row
        writer.writerow([
            "Date",
            "Start Time",
            "End Time",
            "Sport",
            "Sport ID",
            "Duration (minutes)",
            "Strain",
            "Average HR (bpm)",
            "Max HR (bpm)",
            "Calories (kJ)",
            "Distance (m)",
            "Distance (km)",
            "Altitude Gain (m)",
            "Altitude Change (m)",
            "Score State",
        ])
        
        # Data rows
        for workout in records:
            if workout.score:
                distance_m = workout.score.distance_meter or 0
                distance_km = distance_m / 1000 if distance_m else ""
                
                writer.writerow([
                    workout.start.date().isoformat(),
                    workout.start.time().isoformat(),
                    workout.end.time().isoformat() if workout.end else "",
                    workout.sport_name,
                    workout.sport_id,
                    f"{workout.duration_minutes:.1f}" if workout.duration_minutes else "",
                    f"{workout.score.strain:.1f}",
                    workout.score.average_heart_rate,
                    workout.score.max_heart_rate,
                    f"{workout.score.kilojoule:.1f}",
                    distance_m or "",
                    f"{distance_km:.2f}" if distance_km else "",
                    workout.score.altitude_gain_meter or "",
                    workout.score.altitude_change_meter or "",
                    workout.score_state,
                ])
            else:
                writer.writerow([
                    workout.start.date().isoformat(),
                    workout.start.time().isoformat(),
                    workout.end.time().isoformat() if workout.end else "",
                    workout.sport_name,
                    workout.sport_id,
                    f"{workout.duration_minutes:.1f}" if workout.duration_minutes else "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    workout.score_state,
                ])
    
    logger.info(f"Exported {len(records)} workout records to {filepath}")
    return len(records)


# =============================================================================
# Trend Analysis Functions
# =============================================================================

def analyze_recovery_trends(
    recoveries: List[Recovery],
    recent_days: int = 7,
) -> RecoveryTrends:
    """
    Analyze recovery trends from a list of recovery records.
    
    Args:
        recoveries: List of Recovery records (newest first).
        recent_days: Number of recent days to compare against older data.
    
    Returns:
        RecoveryTrends dataclass with analysis results.
    
    Raises:
        ValueError: If no scored recovery records provided.
    
    Example:
        >>> recoveries = client.get_all_recovery(max_records=30)
        >>> trends = analyze_recovery_trends(recoveries)
        >>> print(f"Average: {trends.average_score:.1f}")
        >>> print(f"Green days: {trends.green_days}")
    """
    # Filter to scored records only
    scored = [r for r in recoveries if r.score is not None]
    
    if not scored:
        raise ValueError("No scored recovery records to analyze")
    
    # Extract scores (score is guaranteed non-None after filter)
    scores = [r.score.recovery_score for r in scored if r.score is not None]
    hrvs = [r.score.hrv_rmssd_milli for r in scored if r.score is not None]
    resting_hrs = [r.score.resting_heart_rate for r in scored if r.score is not None]
    
    # Basic statistics
    average_score = sum(scores) / len(scores)
    min_score = min(scores)
    max_score = max(scores)
    average_hrv = sum(hrvs) / len(hrvs)
    average_resting_hr = sum(resting_hrs) / len(resting_hrs)
    
    # Recovery zone distribution
    green_days = sum(1 for s in scores if s >= RECOVERY_GREEN_THRESHOLD)
    yellow_days = sum(
        1 for s in scores 
        if RECOVERY_YELLOW_THRESHOLD <= s < RECOVERY_GREEN_THRESHOLD
    )
    red_days = sum(1 for s in scores if s < RECOVERY_YELLOW_THRESHOLD)
    
    # HRV coefficient of variation (stability metric)
    if len(hrvs) >= 2:
        hrv_mean = sum(hrvs) / len(hrvs)
        hrv_variance = sum((x - hrv_mean) ** 2 for x in hrvs) / len(hrvs)
        hrv_std = hrv_variance ** 0.5
        hrv_cv = (hrv_std / hrv_mean) * 100 if hrv_mean > 0 else 0
    else:
        hrv_cv = 0
    
    # Recent trend (compare recent vs older)
    if len(scores) >= recent_days * 2:
        recent_avg = sum(scores[:recent_days]) / recent_days
        older_avg = sum(scores[-recent_days:]) / recent_days
        recent_trend = recent_avg - older_avg
    else:
        recent_trend = 0
    
    return RecoveryTrends(
        average_score=average_score,
        min_score=min_score,
        max_score=max_score,
        average_hrv=average_hrv,
        average_resting_hr=average_resting_hr,
        green_days=green_days,
        yellow_days=yellow_days,
        red_days=red_days,
        hrv_coefficient_of_variation=hrv_cv,
        recent_trend=recent_trend,
        record_count=len(scored),
    )


def analyze_sleep_trends(
    sleeps: List[Sleep],
    include_naps: bool = False,
) -> SleepTrends:
    """
    Analyze sleep trends from a list of sleep records.
    
    Args:
        sleeps: List of Sleep records (newest first).
        include_naps: Whether to include naps in analysis.
    
    Returns:
        SleepTrends dataclass with analysis results.
    
    Raises:
        ValueError: If no scored sleep records provided.
    
    Example:
        >>> sleeps = client.get_all_sleep(max_records=30)
        >>> trends = analyze_sleep_trends(sleeps, include_naps=False)
        >>> print(f"Avg sleep: {trends.average_duration_hours:.1f}h")
    """
    # Filter records
    scored = [s for s in sleeps if s.score is not None]
    nap_count = sum(1 for s in scored if s.nap)
    
    if not include_naps:
        scored = [s for s in scored if not s.nap]
    
    if not scored:
        raise ValueError("No scored sleep records to analyze")
    
    # Extract metrics (score is guaranteed non-None after filter)
    durations = [s.score.total_sleep_duration_hours for s in scored if s.score is not None]
    perf_values = [s.score.sleep_performance_percentage for s in scored
                   if s.score and s.score.sleep_performance_percentage is not None]
    eff_values = [s.score.sleep_efficiency_percentage for s in scored
                  if s.score and s.score.sleep_efficiency_percentage is not None]
    resp_values = [s.score.respiratory_rate for s in scored
                   if s.score and s.score.respiratory_rate is not None]

    # Basic statistics
    average_duration = sum(durations) / len(durations)
    average_performance = sum(perf_values) / len(perf_values) if perf_values else 0.0
    average_efficiency = sum(eff_values) / len(eff_values) if eff_values else 0.0
    average_respiratory = sum(resp_values) / len(resp_values) if resp_values else 0.0
    
    # Sleep below 7 hours
    nights_below_7h = sum(1 for d in durations if d < 7)
    
    # Consistency score (percentage of nights within 1 hour of average)
    within_threshold = sum(1 for d in durations if abs(d - average_duration) < 1)
    consistency_score = (within_threshold / len(durations)) * 100
    
    return SleepTrends(
        average_duration_hours=average_duration,
        average_performance=average_performance,
        average_efficiency=average_efficiency,
        average_respiratory_rate=average_respiratory,
        consistency_score=consistency_score,
        nights_below_7h=nights_below_7h,
        nap_count=nap_count,
        record_count=len(scored),
    )


def analyze_training_load(
    cycles: List[Cycle],
    workouts: Optional[List[Workout]] = None,
) -> TrainingLoadTrends:
    """
    Analyze training load from cycle and workout data.
    
    Args:
        cycles: List of Cycle records (newest first).
        workouts: Optional list of Workout records.
    
    Returns:
        TrainingLoadTrends dataclass with analysis results.
    
    Raises:
        ValueError: If no scored cycle records provided.
    
    Example:
        >>> cycles = client.get_all_cycles(max_records=30)
        >>> workouts = client.get_all_workouts(max_records=50)
        >>> trends = analyze_training_load(cycles, workouts)
        >>> print(f"Weekly strain: {trends.total_strain:.1f}")
    """
    # Filter to scored cycles
    scored_cycles = [c for c in cycles if c.score is not None]
    
    if not scored_cycles:
        raise ValueError("No scored cycle records to analyze")
    
    # Extract strain scores (score is guaranteed non-None after filter)
    strains = [c.score.strain for c in scored_cycles if c.score is not None]
    
    # Basic statistics
    total_strain = sum(strains)
    average_daily_strain = total_strain / len(strains)
    max_strain = max(strains)
    
    # Strain distribution
    low_strain_threshold = 10
    high_strain_threshold = 14
    
    low_strain_days = sum(1 for s in strains if s < low_strain_threshold)
    moderate_strain_days = sum(
        1 for s in strains 
        if low_strain_threshold <= s < high_strain_threshold
    )
    high_strain_days = sum(1 for s in strains if s >= high_strain_threshold)
    
    # Workout stats
    workout_count = 0
    total_workout_minutes = 0.0
    
    if workouts:
        scored_workouts = [w for w in workouts if w.score]
        workout_count = len(scored_workouts)
        total_workout_minutes = sum(
            w.duration_minutes or 0 for w in scored_workouts
        )
    
    return TrainingLoadTrends(
        total_strain=total_strain,
        average_daily_strain=average_daily_strain,
        max_strain=max_strain,
        low_strain_days=low_strain_days,
        moderate_strain_days=moderate_strain_days,
        high_strain_days=high_strain_days,
        workout_count=workout_count,
        total_workout_minutes=total_workout_minutes,
        record_count=len(scored_cycles),
    )


# =============================================================================
# Dashboard / Report Generation
# =============================================================================

def generate_summary_report(
    recoveries: List[Recovery],
    sleeps: List[Sleep],
    cycles: List[Cycle],
    workouts: Optional[List[Workout]] = None,
    output: Optional[Union[str, Path, TextIO]] = None,
) -> str:
    """
    Generate a text summary report of Whoop data.
    
    Args:
        recoveries: List of Recovery records.
        sleeps: List of Sleep records.
        cycles: List of Cycle records.
        workouts: Optional list of Workout records.
        output: Output file path or file-like object. If None, returns string.
    
    Returns:
        The generated report as a string.
    
    Example:
        >>> report = generate_summary_report(
        ...     recoveries, sleeps, cycles, workouts,
        ...     output="report.txt"
        ... )
    """
    lines: List[str] = []
    separator = "=" * 70
    subseparator = "-" * 70
    
    # Header
    lines.append(separator)
    lines.append(f"WHOOP DATA SUMMARY REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(separator)
    lines.append("")
    
    # Recovery Section
    scored_recoveries = [r for r in recoveries if r.score]
    if scored_recoveries:
        trends = analyze_recovery_trends(recoveries)
        
        lines.append("RECOVERY METRICS")
        lines.append(subseparator)
        lines.append(f"Records analyzed: {trends.record_count}")
        lines.append(f"Average Recovery: {trends.average_score:.1f}")
        lines.append(f"Range: {trends.min_score:.1f} - {trends.max_score:.1f}")
        lines.append(f"Average HRV: {trends.average_hrv:.1f} ms")
        lines.append(f"Average Resting HR: {trends.average_resting_hr:.0f} bpm")
        lines.append(f"HRV Stability (CV): {trends.hrv_coefficient_of_variation:.1f}%")
        lines.append("")
        lines.append("Recovery Zone Distribution:")
        lines.append(f"  Green (>=67): {trends.green_days} days")
        lines.append(f"  Yellow (34-66): {trends.yellow_days} days")
        lines.append(f"  Red (<34): {trends.red_days} days")
        
        if trends.recent_trend != 0:
            trend_dir = "+" if trends.recent_trend > 0 else ""
            lines.append(f"\nRecent Trend: {trend_dir}{trends.recent_trend:.1f}")
        
        lines.append("")
    
    # Sleep Section
    scored_sleeps = [s for s in sleeps if s.score]
    if scored_sleeps:
        sleep_trends = analyze_sleep_trends(sleeps, include_naps=False)
        
        lines.append("SLEEP METRICS")
        lines.append(subseparator)
        lines.append(f"Nights analyzed: {sleep_trends.record_count}")
        lines.append(f"Average Duration: {sleep_trends.average_duration_hours:.1f} hours")
        lines.append(f"Average Performance: {sleep_trends.average_performance:.0f}%")
        lines.append(f"Average Efficiency: {sleep_trends.average_efficiency:.0f}%")
        lines.append(f"Sleep Consistency: {sleep_trends.consistency_score:.0f}%")
        lines.append(f"Nights <7 hours: {sleep_trends.nights_below_7h}")
        lines.append(f"Naps taken: {sleep_trends.nap_count}")
        lines.append("")
    
    # Training Load Section
    scored_cycles = [c for c in cycles if c.score]
    if scored_cycles:
        load_trends = analyze_training_load(cycles, workouts)
        
        lines.append("TRAINING LOAD")
        lines.append(subseparator)
        lines.append(f"Days analyzed: {load_trends.record_count}")
        lines.append(f"Total Strain: {load_trends.total_strain:.1f}")
        lines.append(f"Average Daily Strain: {load_trends.average_daily_strain:.1f}")
        lines.append(f"Max Daily Strain: {load_trends.max_strain:.1f}")
        lines.append("")
        lines.append("Strain Distribution:")
        lines.append(f"  Low (<10): {load_trends.low_strain_days} days")
        lines.append(f"  Moderate (10-14): {load_trends.moderate_strain_days} days")
        lines.append(f"  High (>=14): {load_trends.high_strain_days} days")
        
        if load_trends.workout_count > 0:
            lines.append("")
            lines.append(f"Workouts: {load_trends.workout_count}")
            lines.append(f"Total Workout Time: {load_trends.total_workout_minutes:.0f} minutes")
        
        lines.append("")
    
    # Recommendations Section
    lines.append("RECOMMENDATIONS")
    lines.append(subseparator)
    
    if scored_recoveries and scored_sleeps:
        recent_recoveries = [r for r in scored_recoveries[:7] if r.score is not None]
        recovery_avg = sum(r.score.recovery_score for r in recent_recoveries if r.score is not None) / max(1, len(recent_recoveries))
        
        recent_sleeps = [s for s in scored_sleeps[:7] if s.score is not None and not s.nap]
        sleep_avg = sum(s.score.total_sleep_duration_hours for s in recent_sleeps if s.score is not None) / max(1, len(recent_sleeps))
        
        if recovery_avg >= RECOVERY_GREEN_THRESHOLD:
            lines.append("+ Recovery is in the GREEN zone")
            lines.append("  - Training capacity is high")
            lines.append("  - Can handle increased volume/intensity")
        elif recovery_avg >= RECOVERY_YELLOW_THRESHOLD:
            lines.append("~ Recovery is in the YELLOW zone")
            lines.append("  - Moderate training recommended")
            lines.append("  - Monitor fatigue levels")
        else:
            lines.append("! Recovery is in the RED zone")
            lines.append("  - Prioritize rest and recovery")
            lines.append("  - Consider deload or rest day")
        
        if sleep_avg < 7:
            lines.append("")
            lines.append("! Sleep is below 7 hours")
            lines.append("  - Prioritize earlier bedtime")
            lines.append("  - Insufficient sleep impacts recovery")
    
    lines.append("")
    lines.append(separator)
    lines.append("END OF REPORT")
    lines.append(separator)
    
    report = "\n".join(lines)
    
    # Output handling
    if output is not None:
        if isinstance(output, (str, Path)):
            with open(output, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"Report saved to {output}")
        else:
            output.write(report)
    
    return report


def calculate_moving_average(
    values: List[float],
    window: int = 7,
) -> List[Optional[float]]:
    """
    Calculate moving average for a list of values.
    
    Args:
        values: List of numeric values.
        window: Window size for moving average.
    
    Returns:
        List of moving averages (None for positions with insufficient data).
    
    Example:
        >>> scores = [65, 70, 55, 80, 75, 60, 85]
        >>> ma = calculate_moving_average(scores, window=3)
        >>> print(ma)  # [None, None, 63.33, 68.33, 70.0, 71.67, 73.33]
    """
    if not values:
        return []
    
    if window < 1:
        raise ValueError("Window must be at least 1")
    
    result: List[Optional[float]] = []
    
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            window_values = values[i - window + 1:i + 1]
            result.append(sum(window_values) / len(window_values))
    
    return result
