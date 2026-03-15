import { cn } from '@/lib/utils/cn'
import { StatusBadge } from '@/components/ui/status-badge'
import type { RecoveryStatus, MetricZone } from '@/types/whoop'
import { getRecoveryZone } from '@/types/whoop'

interface RecoveryWidgetProps {
    score: number
    hrv: number
    rhr: number
    status: RecoveryStatus
    className?: string
}

const zoneColors: Record<MetricZone, string> = {
    green: 'text-chart-recovery',
    yellow: 'text-chart-strain',
    red: 'text-destructive',
    neutral: 'text-foreground',
}

export function RecoveryWidget({
    score,
    hrv,
    rhr,
    status,
    className,
}: RecoveryWidgetProps) {
    const zone = getRecoveryZone(score)

    return (
        <div className={cn(
            "rounded-xl border border-border/50 bg-card p-5",
            className
        )}>
            {/* Label */}
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground text-center mb-3">
                Recovery Score
            </p>

            {/* Main score */}
            <div className="flex items-baseline justify-center mb-4">
                <h2 className={cn(
                    "text-3xl font-semibold tabular-nums",
                    zoneColors[zone]
                )}>
                    {score}
                </h2>
                <span className="text-sm font-medium text-muted-foreground ml-1">
                    %
                </span>
            </div>

            {/* Status badge */}
            <div className="flex justify-center mb-6">
                <StatusBadge status={status} />
            </div>

            {/* Secondary metrics */}
            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border/50">
                <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">HRV</p>
                    <p className="text-sm font-semibold tabular-nums">
                        {hrv} <span className="text-xs text-muted-foreground">ms</span>
                    </p>
                </div>
                <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">RHR</p>
                    <p className="text-sm font-semibold tabular-nums">
                        {rhr} <span className="text-xs text-muted-foreground">bpm</span>
                    </p>
                </div>
            </div>
        </div>
    )
}
