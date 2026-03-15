// components/charts/CustomTooltip.tsx
import { CHART_THEME } from '@/lib/charts/config'

interface CustomTooltipProps {
    active?: boolean
    payload?: any[]
    label?: any
    title?: string
}

export function CustomTooltip({
    active,
    payload,
    label,
    title,
}: CustomTooltipProps) {
    if (!active || !payload || payload.length === 0) {
        return null
    }

    return (
        <div
            style={{
                backgroundColor: CHART_THEME.tooltip.background,
                border: `1px solid ${CHART_THEME.tooltip.border}`,
                borderRadius: '0.5rem',
                padding: '0.75rem',
                fontSize: CHART_THEME.tooltip.fontSize,
            }}
        >
            {/* Date label */}
            <p
                style={{
                    color: CHART_THEME.tooltip.text,
                    marginBottom: '0.5rem',
                    fontWeight: 600,
                }}
            >
                {title || label}
            </p>

            {/* Data points */}
            {payload.map((entry, index) => (
                <div
                    key={index}
                    style={{
                        color: entry.color,
                        marginBottom: index < payload.length - 1 ? '0.25rem' : 0,
                    }}
                >
                    <span style={{ fontWeight: 500 }}>
                        {entry.name}:
                    </span>
                    {' '}
                    <span style={{ fontWeight: 600 }}>
                        {typeof entry.value === 'number'
                            ? entry.value.toFixed(1)
                            : entry.value}
                    </span>
                </div>
            ))}
        </div>
    )
}
