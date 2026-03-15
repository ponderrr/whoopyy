import { cn } from '@/lib/utils/cn'

interface PageHeaderProps {
    title: string
    subtitle?: string
    className?: string
}

export function PageHeader({ title, subtitle, className }: PageHeaderProps) {
    return (
        <div className={cn("mb-6 text-center", className)}>
            <h1 className="text-2xl font-semibold mb-1">
                {title}
            </h1>
            {subtitle && (
                <p className="text-sm text-muted-foreground">
                    {subtitle}
                </p>
            )}
        </div>
    )
}
