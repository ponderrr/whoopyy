import { cn } from '@/lib/utils/cn'
import type { MetricZone } from '@/types/whoop'
import { getStrainZone } from '@/types/whoop'

interface StrainWidgetProps {
    strain: number
    calories: number
    workouts?: number
    className?: string
}

const zoneColors: Record<MetricZone, string> = {
    green: 'text-chart-recovery',
    yellow: 'text-chart-strain',
    red: 'text-destructive',
    neutral: 'text-foreground',
}

export function StrainWidget({
    strain,
    calories,
    workouts = 0,
    className,
}: StrainWidgetProps) {
    const zone = getStrainZone(strain)

    return (
        <div className={cn(
            "rounded-xl border border-border/50 bg-card p-5",
            className
        )}>
            {/* Label */}
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground text-center mb-3">
                Daily Strain
            </p>

            {/* Main strain value */}
            <div className="flex items-baseline justify-center mb-6">
                <h2 className={cn(
                    "text-3xl font-semibold tabular-nums",
                    zoneColors[zone]
                )}>
                    {strain.toFixed(1)}
                </h2>
            </div>

            {/* Secondary metrics */}
            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border/50">
                <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">Calories</p>
                    <p className="text-sm font-semibold tabular-nums">
                        {calories.toLocaleString()}
                    </p>
                </div>
                <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">Workouts</p>
                    <p className="text-sm font-semibold tabular-nums">
                        {workouts}
                    </p>
                </div>
            </div>
        </div>
    )
}
