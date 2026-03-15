// components/auth/AuthLoadingScreen.tsx
import { Spinner } from '@/components/ui/spinner'

/**
 * Full-page loading state for authentication verification
 */
export function AuthLoadingScreen() {
    return (
        <div className="flex min-h-screen items-center justify-center bg-background">
            <div className="text-center space-y-4">
                <Spinner size="lg" />
                <div className="space-y-2">
                    <h2 className="text-xl font-semibold">
                        Verifying Session
                    </h2>
                    <p className="text-sm text-muted-foreground">
                        Please wait while we secure your connection...
                    </p>
                </div>
            </div>
        </div>
    )
}
