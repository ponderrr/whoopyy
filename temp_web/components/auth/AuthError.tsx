// components/auth/AuthError.tsx
'use client'

import Link from 'next/link'

interface AuthErrorProps {
    error: {
        message: string
        code?: string
    }
    onRetry?: () => void
}

/**
 * Component to display auth-related errors with actions
 */
export function AuthError({ error, onRetry }: AuthErrorProps) {
    return (
        <div className="flex min-h-screen items-center justify-center bg-background px-6">
            <div className="w-full max-w-md space-y-6">
                <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-8 text-center space-y-6">
                    {/* Error Icon */}
                    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10">
                        <svg className="h-7 w-7 text-destructive" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                    </div>

                    <div className="space-y-2">
                        <h2 className="text-xl font-bold tracking-tight">
                            {error.code === 'SESSION_EXPIRED' ? 'Session Expired' : 'Auth Connection Failed'}
                        </h2>
                        <p className="text-sm text-muted-foreground leading-relaxed">
                            {error.message}
                        </p>
                    </div>

                    <div className="flex flex-col sm:flex-row gap-3">
                        {onRetry && (
                            <button
                                onClick={onRetry}
                                className="flex-1 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary/90 transition-colors"
                            >
                                Try Again
                            </button>
                        )}
                        <Link
                            href="/login"
                            className="flex-1 rounded-lg border border-border bg-secondary px-4 py-2.5 text-sm font-semibold hover:bg-secondary/80 transition-colors"
                        >
                            {onRetry ? 'Back to Login' : 'Relogin now'}
                        </Link>
                    </div>
                </div>

                <p className="text-center text-xs text-muted-foreground opacity-50">
                    Error Code: {error.code || 'UNKNOWN'}
                </p>
            </div>
        </div>
    )
}
