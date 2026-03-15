import { cn } from '@/lib/utils/cn'
import type { MetricZone } from '@/types/whoop'

interface MetricWidgetProps {
    label: string
    value: string | number
    unit?: string
    zone?: MetricZone
    className?: string
    sublabel?: string
}

const zoneColors: Record<MetricZone, string> = {
    green: 'text-chart-recovery',
    yellow: 'text-chart-strain',
    red: 'text-destructive',
    neutral: 'text-foreground',
}

export function MetricWidget({
    label,
    value,
    unit,
    zone = 'neutral',
    className,
    sublabel,
}: MetricWidgetProps) {
    return (
        <div
            className={cn(
                "rounded-xl border border-border/50 bg-card p-5",
                "flex flex-col items-center justify-center",
                className
            )}
        >
            {/* Label - uppercase, centered */}
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground text-center mb-3">
                {label}
            </p>

            {/* Value - large, centered, colored by zone */}
            <div className="flex items-baseline justify-center">
                <h2 className={cn(
                    "text-3xl font-semibold tabular-nums",
                    zoneColors[zone]
                )}>
                    {value}
                </h2>
                {unit && (
                    <span className="text-sm font-medium text-muted-foreground ml-1">
                        {unit}
                    </span>
                )}
            </div>

            {/* Optional sublabel */}
            {sublabel && (
                <p className="text-xs text-muted-foreground mt-2 opacity-70 text-center">
                    {sublabel}
                </p>
            )}
        </div>
    )
}
