import { TopNav } from '@/components/layout/TopNav'
import { requireAuth } from '@/lib/auth/server'

export default async function DashboardLayout({
    children,
}: {
    children: React.ReactNode
}) {
    // Server-side auth check
    await requireAuth()

    return (
        <>
            <TopNav />
            {children}
        </>
    )
}
