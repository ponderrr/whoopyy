// components/shared/Skeleton.tsx
import { cn } from '@/lib/utils/cn'

interface SkeletonProps {
    className?: string
}

export function Skeleton({ className }: SkeletonProps) {
    return (
        <div
            className={cn(
                "animate-pulse rounded-md bg-secondary",
                className
            )}
        />
    )
}

// Predefined skeleton layouts
export function MetricWidgetSkeleton() {
    return (
        <div className="rounded-xl border border-border/50 bg-card p-5 space-y-3">
            <Skeleton className="h-3 w-24 mx-auto" />
            <Skeleton className="h-8 w-16 mx-auto" />
        </div>
    )
}

export function ChartSkeleton() {
    return (
        <div className="rounded-xl border border-border/50 bg-card p-6 space-y-4">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-64 w-full" />
        </div>
    )
}
