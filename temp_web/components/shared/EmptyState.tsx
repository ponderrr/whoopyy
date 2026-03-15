// components/shared/EmptyState.tsx
import { cn } from '@/lib/utils/cn'

interface EmptyStateProps {
    title: string
    description?: string
    className?: string
    icon?: React.ReactNode
}

export function EmptyState({
    title,
    description,
    className,
    icon,
}: EmptyStateProps) {
    return (
        <div
            className={cn(
                "flex flex-col items-center justify-center py-12 text-center",
                className
            )}
        >
            {icon && (
                <div className="mb-4 text-muted-foreground opacity-50">
                    {icon}
                </div>
            )}

            <p className="text-lg font-medium mb-2">{title}</p>

            {description && (
                <p className="text-sm text-muted-foreground max-w-md">
                    {description}
                </p>
            )}
        </div>
    )
}
