// components/charts/WorkoutDistributionChart.tsx
'use client'

import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Cell,
} from 'recharts'
import { CHART_COLORS, CHART_THEME, CHART_MARGINS } from '@/lib/charts/config'

interface WorkoutDistribution {
    sport: string
    count: number
    totalStrain: number
}

interface WorkoutDistributionChartProps {
    data: WorkoutDistribution[]
    height?: number
}

// Color map for different sports
const SPORT_COLORS: Record<string, string> = {
    'Running': CHART_COLORS.recovery,
    'Cycling': CHART_COLORS.sleep,
    'Weightlifting': CHART_COLORS.strain,
    'Functional Fitness': CHART_COLORS.hrv,
    'default': CHART_COLORS.workouts,
}

export function WorkoutDistributionChart({
    data,
    height = 300,
}: WorkoutDistributionChartProps) {
    return (
        <div className="rounded-xl border border-border/50 bg-card p-6">
            <h3 className="text-lg font-semibold mb-4 text-center">
                Workout Distribution
            </h3>

            <ResponsiveContainer width="100%" height={height}>
                <BarChart data={data} margin={CHART_MARGINS.default}>
                    <CartesianGrid
                        stroke={CHART_THEME.grid.stroke}
                        strokeDasharray={CHART_THEME.grid.strokeDasharray}
                    />

                    <XAxis
                        dataKey="sport"
                        stroke={CHART_THEME.axis.stroke}
                        style={{
                            fontSize: CHART_THEME.axis.fontSize,
                            fontWeight: CHART_THEME.axis.fontWeight,
                        }}
                        tickLine={false}
                        angle={-45}
                        textAnchor="end"
                        height={80}
                    />

                    <YAxis
                        stroke={CHART_THEME.axis.stroke}
                        style={{
                            fontSize: CHART_THEME.axis.fontSize,
                            fontWeight: CHART_THEME.axis.fontWeight,
                        }}
                        tickLine={false}
                        label={{
                            value: 'Workouts',
                            angle: -90,
                            position: 'insideLeft',
                            style: {
                                fontSize: CHART_THEME.axis.fontSize,
                                fill: CHART_THEME.axis.stroke,
                            },
                        }}
                    />

                    <Tooltip
                        contentStyle={{
                            backgroundColor: CHART_THEME.tooltip.background,
                            border: `1px solid ${CHART_THEME.tooltip.border}`,
                            borderRadius: '0.5rem',
                            fontSize: CHART_THEME.tooltip.fontSize,
                        }}
                        labelStyle={{
                            color: CHART_THEME.tooltip.text,
                            marginBottom: '0.5rem',
                        }}
                        itemStyle={{
                            color: CHART_THEME.tooltip.text,
                        }}
                        formatter={(value: number | undefined, name: string | undefined) => {
                            const val = value ?? 0
                            const n = name ?? ''
                            if (n === 'count') return [val, 'Workouts'] as [number, string]
                            if (n === 'totalStrain') return [val.toFixed(1), 'Total Strain'] as [string, string]
                            return [val, n] as [number, string]
                        }}
                    />

                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {data.map((entry, index) => (
                            <Cell
                                key={`cell-${index}`}
                                fill={SPORT_COLORS[entry.sport] || SPORT_COLORS.default}
                            />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    )
}
