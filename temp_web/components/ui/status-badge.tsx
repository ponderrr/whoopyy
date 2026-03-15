import { cn } from '@/lib/utils/cn'
import type { RecoveryStatus } from '@/types/whoop'

interface StatusBadgeProps {
    status: RecoveryStatus
    label?: string
    className?: string
}

const statusStyles: Record<RecoveryStatus, string> = {
    success: 'bg-chart-recovery/10 text-chart-recovery border-chart-recovery/20',
    warning: 'bg-chart-strain/10 text-chart-strain border-chart-strain/20',
    error: 'bg-destructive/10 text-destructive border-destructive/20',
}

const statusLabels: Record<RecoveryStatus, string> = {
    success: 'Optimal',
    warning: 'Moderate',
    error: 'Low',
}

export function StatusBadge({ status, label, className }: StatusBadgeProps) {
    const displayLabel = label || statusLabels[status]

    return (
        <span
            className={cn(
                "inline-flex items-center px-2.5 py-0.5 rounded-md border text-xs font-medium",
                statusStyles[status],
                className
            )}
        >
            {displayLabel}
        </span>
    )
}
