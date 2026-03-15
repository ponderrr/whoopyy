// components/charts/ChartLegend.tsx
import { cn } from '@/lib/utils/cn'

interface LegendItem {
    label: string
    color: string
    visible?: boolean
    onToggle?: () => void
}

interface ChartLegendProps {
    items: LegendItem[]
    className?: string
}

export function ChartLegend({
    items,
    className,
}: ChartLegendProps) {
    return (
        <div className={cn(
            "flex items-center justify-center gap-4 flex-wrap",
            className
        )}>
            {items.map((item, index) => (
                <button
                    key={index}
                    onClick={item.onToggle}
                    className={cn(
                        "flex items-center gap-2 text-sm transition-opacity",
                        item.visible === false && "opacity-40",
                        item.onToggle && "cursor-pointer hover:opacity-100"
                    )}
                    disabled={!item.onToggle}
                >
                    <div
                        className="w-3 h-3 rounded-sm"
                        style={{ backgroundColor: item.color }}
                    />
                    <span className="text-muted-foreground font-medium">
                        {item.label}
                    </span>
                </button>
            ))}
        </div>
    )
}
