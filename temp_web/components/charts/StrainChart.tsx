// components/charts/StrainChart.tsx
'use client'

import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend,
    ReferenceLine,
} from 'recharts'
import { CHART_COLORS, CHART_THEME, CHART_MARGINS } from '@/lib/charts/config'

interface StrainDataPoint {
    date: string
    strain: number
    calories: number
}

interface StrainChartProps {
    data: StrainDataPoint[]
    height?: number
}

export function StrainChart({
    data,
    height = 300,
}: StrainChartProps) {
    return (
        <div className="rounded-xl border border-border/50 bg-card p-6">
            <h3 className="text-lg font-semibold mb-4 text-center">
                Daily Strain & Calorie Burn
            </h3>

            <ResponsiveContainer width="100%" height={height}>
                <AreaChart data={data} margin={CHART_MARGINS.withLegend}>
                    <defs>
                        <linearGradient id="strainGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={CHART_COLORS.strain} stopOpacity={0.3} />
                            <stop offset="95%" stopColor={CHART_COLORS.strain} stopOpacity={0} />
                        </linearGradient>
                    </defs>

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
                            value: 'Strain',
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
                            value: 'Calories',
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

                    {/* Strain zones reference lines */}
                    <ReferenceLine
                        yAxisId="left"
                        y={10}
                        stroke={CHART_COLORS.recovery}
                        strokeDasharray="3 3"
                        label={{ value: 'Low', position: 'right', fontSize: 10, fill: CHART_COLORS.recovery }}
                    />
                    <ReferenceLine
                        yAxisId="left"
                        y={14}
                        stroke={CHART_COLORS.strain}
                        strokeDasharray="3 3"
                        label={{ value: 'Moderate', position: 'right', fontSize: 10, fill: CHART_COLORS.strain }}
                    />

                    <Area
                        yAxisId="left"
                        type="monotone"
                        dataKey="strain"
                        name="Strain"
                        stroke={CHART_COLORS.strain}
                        fill="url(#strainGradient)"
                        strokeWidth={2}
                    />

                    <Area
                        yAxisId="right"
                        type="monotone"
                        dataKey="calories"
                        name="Calories"
                        stroke={CHART_COLORS.calories}
                        fill="none"
                        strokeWidth={2}
                        strokeDasharray="5 5"
                    />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    )
}
