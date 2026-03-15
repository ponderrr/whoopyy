// components/auth/DashboardSkeleton.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { MetricWidgetSkeleton } from '@/components/widgets/MetricWidgetSkeleton'

/**
 * Full-page skeleton for the dashboard view
 */
export function DashboardSkeleton() {
    return (
        <div className="min-h-screen bg-background">
            {/* Header section skeleton */}
            <div className="mb-8 text-center space-y-3 pt-6">
                <Skeleton className="h-8 w-48 mx-auto" />
                <Skeleton className="h-4 w-64 mx-auto" />
            </div>

            {/* Widget grid skeleton */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 px-6">
                <MetricWidgetSkeleton />
                <MetricWidgetSkeleton />
                <MetricWidgetSkeleton />
            </div>

            {/* Large chart section skeleton */}
            <div className="mt-8 px-6">
                <div className="rounded-xl border border-border/50 bg-card p-6 space-y-4">
                    <Skeleton className="h-6 w-40 mx-auto mb-4" />
                    <Skeleton className="h-[300px] w-full" />
                </div>
            </div>
        </div>
    )
}
