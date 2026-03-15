// app/api/whoop/auth/logout/route.ts
import { NextRequest } from 'next/server'
import { clearTokens } from '@/lib/api/tokens'
import { successResponse, errorResponse } from '@/lib/api/response'

/**
 * Endpoint to clear authentication cookies
 */
export async function POST(request: NextRequest) {
    try {
        // Clear all auth tokens from cookies
        await clearTokens()

        return successResponse({ message: 'Logged out successfully' }, 200)

    } catch (error) {
        console.error('Logout error:', error)
        return errorResponse('Logout failed', 500)
    }
}
