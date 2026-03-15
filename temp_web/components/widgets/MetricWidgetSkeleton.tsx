// components/widgets/MetricWidgetSkeleton.tsx
import { Skeleton } from '@/components/ui/skeleton'

/**
 * Skeleton loader for MetricWidget to prevent layout shift
 */
export function MetricWidgetSkeleton() {
    return (
        <div className="rounded-xl border border-border/50 bg-card p-5 space-y-4">
            {/* Label */}
            <div className="flex justify-center">
                <Skeleton className="h-3 w-24" />
            </div>

            {/* Value */}
            <div className="flex justify-center items-baseline gap-1">
                <Skeleton className="h-9 w-16" />
                <Skeleton className="h-4 w-6" />
            </div>

            {/* Optional sub-grid (footer) */}
            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border/50">
                <div className="space-y-1">
                    <Skeleton className="h-3 w-10 mx-auto" />
                    <Skeleton className="h-4 w-12 mx-auto" />
                </div>
                <div className="space-y-1">
                    <Skeleton className="h-3 w-10 mx-auto" />
                    <Skeleton className="h-4 w-12 mx-auto" />
                </div>
            </div>
        </div>
    )
}
