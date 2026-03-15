// app/(auth)/login/page.tsx
import Link from 'next/link'
import { redirect } from 'next/navigation'
import { getAccessToken } from '@/lib/api/tokens'
import { API_ROUTES } from '@/lib/constants'

export const metadata = {
    title: 'Login',
    description: 'Sign in with your WHOOP account',
}

export default async function LoginPage() {
    // If already authenticated, redirect to dashboard
    const token = await getAccessToken()
    if (token) {
        redirect('/dashboard')
    }

    return (
        <div className="flex min-h-screen items-center justify-center bg-background px-6">
            <div className="w-full max-w-md space-y-8">
                {/* Logo/Title */}
                <div className="text-center">
                    <h1 className="text-3xl font-semibold mb-2">
                        WHOOP Insights
                    </h1>
                    <p className="text-sm text-muted-foreground">
                        Track your recovery, sleep, and strain metrics
                    </p>
                </div>

                {/* Login Card */}
                <div className="rounded-xl border border-border/50 bg-card p-8">
                    <div className="space-y-6">
                        {/* Header */}
                        <div className="space-y-2 text-center">
                            <h2 className="text-xl font-semibold">
                                Sign In
                            </h2>
                            <p className="text-sm text-muted-foreground">
                                Connect your WHOOP account to get started
                            </p>
                        </div>

                        {/* Login Button */}
                        <Link
                            href={API_ROUTES.WHOOP_LOGIN}
                            className="flex w-full items-center justify-center gap-3 rounded-lg bg-[#0047BB] px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-[#0047BB]/90"
                        >
                            <svg
                                className="h-5 w-5"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                            >
                                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                                <polyline points="10 17 15 12 10 7" />
                                <line x1="15" y1="12" x2="3" y2="12" />
                            </svg>
                            Login with WHOOP
                        </Link>

                        {/* Info */}
                        <div className="space-y-2 rounded-lg bg-secondary/50 p-4 text-xs text-muted-foreground">
                            <p className="font-medium text-foreground">
                                What you'll need:
                            </p>
                            <ul className="space-y-1 list-disc list-inside">
                                <li>Active WHOOP membership</li>
                                <li>WHOOP account credentials</li>
                            </ul>
                        </div>

                        {/* Privacy */}
                        <p className="text-center text-xs text-muted-foreground">
                            By signing in, you agree to share your WHOOP data with this app.
                            <br />
                            You can revoke access at any time.
                        </p>
                    </div>
                </div>

                {/* Footer Links */}
                <div className="text-center text-sm text-muted-foreground">
                    <p>
                        Don't have a WHOOP account?{' '}
                        <a
                            href="https://join.whoop.com"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary hover:underline"
                        >
                            Join WHOOP
                        </a>
                    </p>
                </div>
            </div>
        </div>
    )
}
