import Link from 'next/link'
import { ROUTES } from '@/lib/constants'

export default function NotFound() {
    return (
        <div className="flex min-h-screen flex-col items-center justify-center">
            <h2 className="text-2xl font-semibold mb-2">404 - Page Not Found</h2>
            <p className="text-muted-foreground mb-4">
                The page you're looking for doesn't exist.
            </p>
            <Link
                href={ROUTES.DASHBOARD}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90"
            >
                Go to Dashboard
            </Link>
        </div>
    )
}
