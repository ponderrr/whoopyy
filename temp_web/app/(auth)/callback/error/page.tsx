// app/(auth)/callback/error/page.tsx
import Link from 'next/link'

interface ErrorPageProps {
    searchParams: Promise<{ message?: string }>
}

export default async function CallbackErrorPage({
    searchParams,
}: ErrorPageProps) {
    const params = await searchParams
    const errorMessage = params.message || 'Authentication failed'

    return (
        <div className="flex min-h-screen items-center justify-center bg-background px-6">
            <div className="w-full max-w-md space-y-6">
                {/* Error Card */}
                <div className="rounded-xl border border-destructive/50 bg-destructive/10 p-8">
                    <div className="space-y-4 text-center">
                        {/* Error Icon */}
                        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-destructive/20">
                            <svg
                                className="h-6 w-6 text-destructive"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                            >
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M6 18L18 6M6 6l12 12"
                                />
                            </svg>
                        </div>

                        {/* Error Message */}
                        <div className="space-y-2">
                            <h2 className="text-xl font-semibold">
                                Authentication Failed
                            </h2>
                            <p className="text-sm text-muted-foreground">
                                {errorMessage}
                            </p>
                        </div>

                        {/* Try Again Button */}
                        <Link
                            href="/login"
                            className="inline-flex items-center justify-center rounded-lg bg-primary px-6 py-2 text-sm font-medium text-white hover:bg-primary/90"
                        >
                            Try Again
                        </Link>
                    </div>
                </div>

                {/* Help Text */}
                <div className="rounded-lg bg-secondary/50 p-4 text-xs text-muted-foreground">
                    <p className="font-medium text-foreground mb-2">
                        Common issues:
                    </p>
                    <ul className="space-y-1 list-disc list-inside">
                        <li>WHOOP account credentials incorrect</li>
                        <li>WHOOP membership expired</li>
                        <li>Network connection interrupted</li>
                    </ul>
                </div>
            </div>
        </div>
    )
}
