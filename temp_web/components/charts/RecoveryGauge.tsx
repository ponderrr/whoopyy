// components/charts/RecoveryGauge.tsx
'use client'

import {
    RadialBarChart,
    RadialBar,
    PolarAngleAxis,
    ResponsiveContainer,
} from 'recharts'
import { CHART_COLORS } from '@/lib/charts/config'
import { getRecoveryZone } from '@/types/whoop'

interface RecoveryGaugeProps {
    score: number
    size?: number
}

export function RecoveryGauge({
    score,
    size = 200,
}: RecoveryGaugeProps) {
    const zone = getRecoveryZone(score)

    const colorMap: Record<string, string> = {
        green: CHART_COLORS.recovery,
        yellow: CHART_COLORS.strain,
        red: CHART_COLORS.rhr,
        'chart-recovery': CHART_COLORS.recovery,
        'chart-strain': CHART_COLORS.strain,
        neutral: 'hsl(240, 5%, 55%)',
    }

    const color = colorMap[zone] || CHART_COLORS.recovery

    const data = [
        {
            name: 'Recovery',
            value: score,
            fill: color,
        },
    ]

    return (
        <div className="rounded-xl border border-border/50 bg-card p-6 flex flex-col items-center relative">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground text-center mb-2">
                Recovery Gauge
            </p>

            <ResponsiveContainer width={size} height={size}>
                <RadialBarChart
                    cx="50%"
                    cy="50%"
                    innerRadius="70%"
                    outerRadius="100%"
                    data={data}
                    startAngle={90}
                    endAngle={-270}
                >
                    <PolarAngleAxis
                        type="number"
                        domain={[0, 100]}
                        angleAxisId={0}
                        tick={false}
                    />
                    <RadialBar
                        background={{ fill: 'hsl(240, 4%, 16%)' }}
                        dataKey="value"
                        cornerRadius={10}
                    />
                </RadialBarChart>
            </ResponsiveContainer>

            <div className="absolute" style={{ top: '50%', left: '50%', transform: 'translate(-50%, -50%)', marginTop: '10px' }}>
                <div className="text-center">
                    <p className="text-3xl font-semibold tabular-nums" style={{ color }}>
                        {score}
                    </p>
                    <p className="text-xs text-muted-foreground">%</p>
                </div>
            </div>
        </div>
    )
}
