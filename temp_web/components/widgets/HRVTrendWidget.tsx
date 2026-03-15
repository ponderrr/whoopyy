// components/widgets/HRVTrendWidget.tsx
import { cn } from '@/lib/utils/cn'

interface HRVTrendWidgetProps {
    current: number
    average: number
    trend: 'up' | 'down' | 'stable'
    className?: string
}

const trendIcons = {
    up: '↑',
    down: '↓',
    stable: '→',
}

const trendColors = {
    up: 'text-chart-recovery',
    down: 'text-destructive',
    stable: 'text-muted-foreground',
}

export function HRVTrendWidget({
    current,
    average,
    trend,
    className,
}: HRVTrendWidgetProps) {
    const difference = current - average
    const percentChange = ((difference / average) * 100).toFixed(1)

    return (
        <div className={cn(
            "rounded-xl border border-border/50 bg-card p-5",
            className
        )}>
            {/* Label */}
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground text-center mb-3">
                HRV Trend (7-Day)
            </p>

            {/* Current value */}
            <div className="flex items-baseline justify-center mb-2">
                <h2 className="text-3xl font-semibold tabular-nums">
                    {current}
                </h2>
                <span className="text-sm font-medium text-muted-foreground ml-1">
                    ms
                </span>
            </div>

            {/* Trend indicator */}
            <div className="flex items-center justify-center gap-2 mb-4">
                <span className={cn(
                    "text-lg font-semibold",
                    trendColors[trend]
                )}>
                    {trendIcons[trend]}
                </span>
                <span className={cn(
                    "text-sm font-medium",
                    trendColors[trend]
                )}>
                    {difference > 0 ? '+' : ''}{percentChange}%
                </span>
            </div>

            {/* Average */}
            <div className="pt-4 border-t border-border/50 text-center">
                <p className="text-xs text-muted-foreground mb-1">7-Day Average</p>
                <p className="text-sm font-semibold tabular-nums">
                    {average} <span className="text-xs text-muted-foreground">ms</span>
                </p>
            </div>
        </div>
    )
}
