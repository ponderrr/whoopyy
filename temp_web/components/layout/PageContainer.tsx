import { cn } from '@/lib/utils/cn'

interface PageContainerProps {
    children: React.ReactNode
    className?: string
}

export function PageContainer({ children, className }: PageContainerProps) {
    return (
        <div className={cn(
            "min-h-screen bg-background px-6 py-6",
            className
        )}>
            {children}
        </div>
    )
}
