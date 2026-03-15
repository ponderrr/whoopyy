// app/api/whoop/profile/route.ts
import { NextRequest } from 'next/server'
import { getAccessToken, isTokenExpired } from '@/lib/api/tokens'
import { successResponse, errorResponse } from '@/lib/api/response'
import { AuthError, WhoopAPIError } from '@/lib/api/errors'
import { CACHE_DURATIONS } from '@/lib/constants'

const WHOOP_API_URL = 'https://api.prod.whoop.com/developer/v1'

export async function GET(request: NextRequest) {
    try {
        const accessToken = await getAccessToken()
        if (!accessToken) {
            throw new AuthError()
        }

        if (await isTokenExpired()) {
            throw new AuthError('Token expired - please refresh')
        }

        // Fetch both profile and body measurements in parallel
        const [profileResponse, bodyResponse] = await Promise.all([
            fetch(`${WHOOP_API_URL}/user/profile/basic`, {
                headers: { Authorization: `Bearer ${accessToken}` },
                next: { revalidate: CACHE_DURATIONS.PROFILE },
            }),
            fetch(`${WHOOP_API_URL}/user/body_measurement`, {
                headers: { Authorization: `Bearer ${accessToken}` },
                next: { revalidate: CACHE_DURATIONS.PROFILE },
            }),
        ])

        if (!profileResponse.ok) {
            throw new WhoopAPIError(
                'Failed to fetch profile',
                profileResponse.status
            )
        }

        const profile = await profileResponse.json()
        const body = bodyResponse.ok ? await bodyResponse.json() : null

        return successResponse({ profile, body }, 200)

    } catch (error: any) {
        if (error instanceof AuthError) {
            return errorResponse(error.message, error.statusCode, error.code)
        }
        if (error instanceof WhoopAPIError) {
            return errorResponse(error.message, error.statusCode, error.code)
        }
        console.error('Profile API error:', error)
        return errorResponse('Internal server error', 500)
    }
}
