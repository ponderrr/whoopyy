import { cn } from '@/lib/utils/cn'
import { StatusBadge } from '@/components/ui/status-badge'
import type { RecoveryStatus, MetricZone } from '@/types/whoop'
import { getSleepPerformanceZone } from '@/types/whoop'

interface SleepWidgetProps {
    hours: number
    performance: number
    efficiency?: number
    className?: string
}

const zoneColors: Record<MetricZone, string> = {
    green: 'text-chart-recovery',
    yellow: 'text-chart-strain',
    red: 'text-destructive',
    neutral: 'text-foreground',
}

export function SleepWidget({
    hours,
    performance,
    efficiency,
    className,
}: SleepWidgetProps) {
    const zone = getSleepPerformanceZone(performance)

    // Determine status based on performance
    const status: RecoveryStatus =
        performance >= 85 ? 'success' :
            performance >= 70 ? 'warning' : 'error'

    return (
        <div className={cn(
            "rounded-xl border border-border/50 bg-card p-5",
            className
        )}>
            {/* Label */}
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground text-center mb-3">
                Sleep Performance
            </p>

            {/* Main value - hours */}
            <div className="flex items-baseline justify-center mb-2">
                <h2 className={cn(
                    "text-3xl font-semibold tabular-nums",
                    zoneColors[zone]
                )}>
                    {hours.toFixed(1)}
                </h2>
                <span className="text-sm font-medium text-muted-foreground ml-1">
                    hours
                </span>
            </div>

            {/* Performance percentage */}
            <p className="text-center text-sm text-muted-foreground mb-4">
                {performance}% of need
            </p>

            {/* Status badge */}
            <div className="flex justify-center mb-6">
                <StatusBadge status={status} />
            </div>

            {/* Efficiency if provided */}
            {efficiency && (
                <div className="pt-4 border-t border-border/50 text-center">
                    <p className="text-xs text-muted-foreground mb-1">Efficiency</p>
                    <p className="text-sm font-semibold tabular-nums">
                        {efficiency}%
                    </p>
                </div>
            )}
        </div>
    )
}
