// components/charts/LineChartComponent.tsx
'use client'

import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend,
} from 'recharts'
import { CHART_COLORS, CHART_THEME, CHART_MARGINS } from '@/lib/charts/config'

interface DataPoint {
    date: string
    [key: string]: string | number | undefined
}

interface LineChartComponentProps {
    data: DataPoint[]
    lines: Array<{
        dataKey: string
        name: string
        color: string
        strokeWidth?: number
    }>
    height?: number
    showLegend?: boolean
    yAxisLabel?: string
}

export function LineChartComponent({
    data,
    lines,
    height = 300,
    showLegend = true,
    yAxisLabel,
}: LineChartComponentProps) {
    return (
        <ResponsiveContainer width="100%" height={height}>
            <LineChart
                data={data}
                margin={showLegend ? CHART_MARGINS.withLegend : CHART_MARGINS.default}
            >
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
                    stroke={CHART_THEME.axis.stroke}
                    style={{
                        fontSize: CHART_THEME.axis.fontSize,
                        fontWeight: CHART_THEME.axis.fontWeight,
                    }}
                    tickLine={false}
                    label={yAxisLabel ? {
                        value: yAxisLabel,
                        angle: -90,
                        position: 'insideLeft',
                        style: {
                            fontSize: CHART_THEME.axis.fontSize,
                            fill: CHART_THEME.axis.stroke,
                        },
                    } : undefined}
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

                {showLegend && (
                    <Legend
                        wrapperStyle={{
                            fontSize: CHART_THEME.legend.fontSize,
                            fontWeight: CHART_THEME.legend.fontWeight,
                            color: CHART_THEME.legend.color,
                        }}
                    />
                )}

                {lines.map((line) => (
                    <Line
                        key={line.dataKey}
                        type="monotone"
                        dataKey={line.dataKey}
                        name={line.name}
                        stroke={line.color}
                        strokeWidth={line.strokeWidth || 2}
                        dot={{ fill: line.color, r: 4 }}
                        activeDot={{ r: 6 }}
                    />
                ))}
            </LineChart>
        </ResponsiveContainer>
    )
}
