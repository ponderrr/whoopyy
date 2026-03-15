/**
 * WHOOP API Response Types
 * Based on WHOOP Developer API v2
 */

// ============================================================================
// RECOVERY TYPES
// ============================================================================

export interface RecoveryScore {
    recovery_score: number              // 0-100
    resting_heart_rate: number         // bpm
    hrv_rmssd_milli: number            // HRV in milliseconds
    spo2_percentage?: number           // SpO2 percentage
    skin_temp_celsius?: number         // Skin temperature in Celsius
    user_calibrating?: boolean         // True if user is calibrating
}

export interface WhoopRecovery {
    recovery_id: string
    user_id: string
    created_at: string                 // ISO datetime
    updated_at: string                 // ISO datetime
    score_state: 'SCORED' | 'PENDING_SCORE' | 'UNSCORABLE'
    score?: RecoveryScore
}

export interface RecoveryCollection {
    records: WhoopRecovery[]
    next_token?: string
}

// ============================================================================
// SLEEP TYPES
// ============================================================================

export interface SleepStage {
    stage_summary: {
        total_light_sleep_time_milli: number
        total_slow_wave_sleep_time_milli: number
        total_rem_sleep_time_milli: number
        total_awake_time_milli: number
    }
}

export interface SleepNeeded {
    baseline_milli: number
    need_from_sleep_debt_milli: number
    need_from_recent_strain_milli: number
    need_from_recent_nap_milli: number
}

export interface SleepScore {
    stage_summary?: SleepStage['stage_summary']
    sleep_needed?: SleepNeeded
    respiratory_rate?: number
    sleep_performance_percentage?: number
    sleep_consistency_percentage?: number
    sleep_efficiency_percentage?: number
}

export interface WhoopSleep {
    sleep_id: string
    user_id: string
    created_at: string
    updated_at: string
    start: string
    end: string
    timezone_offset: string
    nap: boolean
    score_state: 'SCORED' | 'PENDING_SCORE' | 'UNSCORABLE'
    score?: SleepScore
}

export interface SleepCollection {
    records: WhoopSleep[]
    next_token?: string
}

// ============================================================================
// CYCLE TYPES (DAILY STRAIN)
// ============================================================================

export interface CycleScore {
    strain: number                     // 0-21
    kilojoule: number
    average_heart_rate: number
    max_heart_rate: number
}

export interface WhoopCycle {
    cycle_id: string
    user_id: string
    created_at: string
    updated_at: string
    start: string
    end?: string                       // Optional if current cycle
    timezone_offset: string
    score_state: 'SCORED' | 'PENDING_SCORE' | 'UNSCORABLE'
    score?: CycleScore
}

export interface CycleCollection {
    records: WhoopCycle[]
    next_token?: string
}

// ============================================================================
// WORKOUT TYPES
// ============================================================================

export interface WorkoutScore {
    strain: number
    average_heart_rate: number
    max_heart_rate: number
    kilojoule: number
    percent_recorded?: number
    distance_meter?: number
    altitude_gain_meter?: number
    altitude_change_meter?: number
    zone_duration?: {
        zone_zero_milli: number
        zone_one_milli: number
        zone_two_milli: number
        zone_three_milli: number
        zone_four_milli: number
        zone_five_milli: number
    }
}

export interface WhoopWorkout {
    workout_id: string
    user_id: string
    created_at: string
    updated_at: string
    start: string
    end: string
    timezone_offset: string
    sport_id: number
    sport_name: string
    score_state: 'SCORED' | 'PENDING_SCORE' | 'UNSCORABLE'
    score?: WorkoutScore
}

export interface WorkoutCollection {
    records: WhoopWorkout[]
    next_token?: string
}

// ============================================================================
// USER PROFILE TYPES
// ============================================================================

export interface UserProfile {
    user_id: string
    email: string
    first_name: string
    last_name: string
}

export interface BodyMeasurement {
    height_meter?: number
    weight_kilogram?: number
    max_heart_rate?: number
}

// ============================================================================
// UTILITY TYPES
// ============================================================================

export type MetricZone = 'green' | 'yellow' | 'red' | 'neutral'

export type RecoveryStatus = 'success' | 'warning' | 'error'

export interface MetricValue {
    value: number
    unit?: string
    zone?: MetricZone
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

export function getRecoveryZone(score: number): MetricZone {
    if (score >= 67) return 'green'
    if (score >= 34) return 'yellow'
    return 'red'
}

export function getRecoveryStatus(score: number): RecoveryStatus {
    if (score >= 67) return 'success'
    if (score >= 34) return 'warning'
    return 'error'
}

export function getSleepPerformanceZone(percentage: number): MetricZone {
    if (percentage >= 85) return 'green'
    if (percentage >= 70) return 'yellow'
    return 'red'
}

export function getStrainZone(strain: number): MetricZone {
    if (strain >= 14) return 'red'      // High strain
    if (strain >= 10) return 'yellow'   // Moderate strain
    if (strain >= 0) return 'green'     // Low strain
    return 'neutral'
}

// Convert milliseconds to hours
export function millisToHours(millis: number): number {
    return millis / (1000 * 60 * 60)
}

// Format sleep duration
export function formatSleepDuration(millis: number): string {
    const hours = Math.floor(millis / (1000 * 60 * 60))
    const minutes = Math.round((millis % (1000 * 60 * 60)) / (1000 * 60))
    return `${hours}h ${minutes}m`
}
