// components/charts/SleepChart.tsx
'use client'

import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend,
} from 'recharts'
import { CHART_COLORS, CHART_THEME, CHART_MARGINS } from '@/lib/charts/config'

interface SleepDataPoint {
    date: string
    hours: number
    performance: number
}

interface SleepChartProps {
    data: SleepDataPoint[]
    height?: number
}

export function SleepChart({
    data,
    height = 300,
}: SleepChartProps) {
    return (
        <div className="rounded-xl border border-border/50 bg-card p-6">
            <h3 className="text-lg font-semibold mb-4 text-center">
                Sleep Duration & Performance
            </h3>

            <ResponsiveContainer width="100%" height={height}>
                <BarChart data={data} margin={CHART_MARGINS.withLegend}>
                    <CartesianGrid
                        stroke={CHART_THEME.grid.stroke}
                        strokeDasharray={CHART_THEME.grid.strokeDasharray}
                    />

                    <XAxis
                        dataKey="date"
                        stroke={CHART_THEME.axis.stroke}
                        style={{
                            fontSize: CHART_THEME.axis.fontSize,
                            fontWeight: CHART_THEME.axis.fontWeight,
                        }}
                        tickLine={false}
                    />

                    <YAxis
                        yAxisId="left"
                        stroke={CHART_THEME.axis.stroke}
                        style={{
                            fontSize: CHART_THEME.axis.fontSize,
                            fontWeight: CHART_THEME.axis.fontWeight,
                        }}
                        tickLine={false}
                        label={{
                            value: 'Hours',
                            angle: -90,
                            position: 'insideLeft',
                            style: {
                                fontSize: CHART_THEME.axis.fontSize,
                                fill: CHART_THEME.axis.stroke,
                            },
                        }}
                    />

                    <YAxis
                        yAxisId="right"
                        orientation="right"
                        stroke={CHART_THEME.axis.stroke}
                        style={{
                            fontSize: CHART_THEME.axis.fontSize,
                            fontWeight: CHART_THEME.axis.fontWeight,
                        }}
                        tickLine={false}
                        label={{
                            value: 'Performance %',
                            angle: 90,
                            position: 'insideRight',
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
                    />

                    <Legend
                        wrapperStyle={{
                            fontSize: CHART_THEME.legend.fontSize,
                            fontWeight: CHART_THEME.legend.fontWeight,
                            color: CHART_THEME.legend.color,
                        }}
                    />

                    <Bar
                        yAxisId="left"
                        dataKey="hours"
                        name="Sleep Hours"
                        fill={CHART_COLORS.sleep}
                        radius={[4, 4, 0, 0]}
                    />

                    <Bar
                        yAxisId="right"
                        dataKey="performance"
                        name="Performance %"
                        fill={CHART_COLORS.recovery}
                        radius={[4, 4, 0, 0]}
                    />
                </BarChart>
            </ResponsiveContainer>
        </div>
    )
}
