// components/auth/SessionRefreshToast.tsx
'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth/context'

/**
 * Small notification toast that appears when the session is auto-refreshed
 */
export function SessionRefreshToast() {
    const { isAuthenticated } = useAuth()
    const [showToast, setShowToast] = useState(false)

    useEffect(() => {
        if (!isAuthenticated) return

        const handleRefreshed = () => {
            setShowToast(true)
            setTimeout(() => setShowToast(false), 5000)
        }

        window.addEventListener('whoop-session-refreshed', handleRefreshed)
        return () => window.removeEventListener('whoop-session-refreshed', handleRefreshed)
    }, [isAuthenticated])

    if (!showToast) return null

    return (
        <div className="fixed bottom-6 right-6 z-50 animate-in fade-in slide-in-from-bottom-4 duration-300">
            <div className="rounded-xl border border-border bg-card/80 backdrop-blur-md p-4 shadow-2xl max-w-sm flex items-start gap-4">
                <div className="flex-shrink-0 bg-success/10 p-2 rounded-lg">
                    <svg className="h-5 w-5 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                </div>
                <div className="space-y-1">
                    <p className="text-sm font-semibold text-foreground">Session Renewed</p>
                    <p className="text-xs text-muted-foreground">Your WHOOP connection has been automatically refreshed.</p>
                </div>
            </div>
        </div>
    )
}
