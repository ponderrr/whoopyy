// components/layout/WidgetGrid.tsx
import { cn } from '@/lib/utils/cn'

interface WidgetGridProps {
    children: React.ReactNode
    columns?: 1 | 2 | 3 | 4
    className?: string
}

export function WidgetGrid({
    children,
    columns = 3,
    className,
}: WidgetGridProps) {
    const gridCols = {
        1: 'grid-cols-1',
        2: 'grid-cols-1 md:grid-cols-2',
        3: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3',
        4: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-4',
    }

    return (
        <div className={cn(
            "grid gap-4",
            gridCols[columns],
            className
        )}>
            {children}
        </div>
    )
}
