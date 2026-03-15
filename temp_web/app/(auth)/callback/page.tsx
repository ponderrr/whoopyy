// app/(auth)/callback/page.tsx
import { Suspense } from 'react'
import { Spinner } from '@/components/ui/spinner'

function CallbackContent() {
    // The actual OAuth handling happens in the API route
    // This page just shows a loading state while redirecting
    return (
        <div className="flex min-h-screen items-center justify-center bg-background">
            <div className="text-center space-y-4">
                <Spinner size="lg" />
                <div className="space-y-2">
                    <h2 className="text-xl font-semibold">
                        Completing Sign In...
                    </h2>
                    <p className="text-sm text-muted-foreground">
                        Please wait while we connect your WHOOP account
                    </p>
                </div>
            </div>
        </div>
    )
}

export default function CallbackPage() {
    return (
        <Suspense fallback={<CallbackContent />}>
            <CallbackContent />
        </Suspense>
    )
}
