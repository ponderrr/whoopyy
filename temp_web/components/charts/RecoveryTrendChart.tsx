// components/charts/RecoveryTrendChart.tsx
'use client'

import { LineChartComponent } from './LineChartComponent'
import { CHART_COLORS } from '@/lib/charts/config'

interface RecoveryDataPoint {
    date: string
    recovery: number
    hrv?: number
    [key: string]: string | number | undefined
}

interface RecoveryTrendChartProps {
    data: RecoveryDataPoint[]
    showHRV?: boolean
    height?: number
}

export function RecoveryTrendChart({
    data,
    showHRV = false,
    height = 300,
}: RecoveryTrendChartProps) {
    const lines = [
        {
            dataKey: 'recovery',
            name: 'Recovery Score',
            color: CHART_COLORS.recovery,
            strokeWidth: 2,
        },
    ]

    if (showHRV) {
        lines.push({
            dataKey: 'hrv',
            name: 'HRV (ms)',
            color: CHART_COLORS.hrv,
            strokeWidth: 2,
        })
    }

    return (
        <div className="rounded-xl border border-border/50 bg-card p-6">
            <h3 className="text-lg font-semibold mb-4 text-center">
                Recovery Trend
            </h3>

            <LineChartComponent
                data={data}
                lines={lines}
                height={height}
                showLegend={showHRV}
                yAxisLabel="Score"
            />
        </div>
    )
}
