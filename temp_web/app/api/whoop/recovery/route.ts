// app/api/whoop/recovery/route.ts
import { NextRequest } from 'next/server'
import { getAccessToken, isTokenExpired } from '@/lib/api/tokens'
import { successResponse, errorResponse } from '@/lib/api/response'
import { AuthError, RateLimitError, WhoopAPIError } from '@/lib/api/errors'
import { CACHE_DURATIONS } from '@/lib/constants'

const WHOOP_API_URL = 'https://api.prod.whoop.com/developer/v1'

export async function GET(request: NextRequest) {
    try {
        // Check authentication
        const accessToken = await getAccessToken()
        if (!accessToken) {
            throw new AuthError()
        }

        // Check if token is expired
        if (await isTokenExpired()) {
            throw new AuthError('Token expired - please refresh')
        }

        // Get query parameters
        const searchParams = request.nextUrl.searchParams
        const limit = searchParams.get('limit') || '7'

        // Fetch from WHOOP API
        const response = await fetch(
            `${WHOOP_API_URL}/activity/recovery?limit=${limit}`,
            {
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                },
                next: {
                    revalidate: CACHE_DURATIONS.RECOVERY, // 1 hour cache from constants
                    tags: ['recovery'],
                },
            }
        )

        // Handle rate limiting
        if (response.status === 429) {
            const retryAfter = parseInt(
                response.headers.get('X-RateLimit-Reset') || '60'
            )
            throw new RateLimitError('Rate limit exceeded', retryAfter)
        }

        // Handle other errors
        if (!response.ok) {
            const errorText = await response.text()
            console.error('WHOOP API error:', errorText)
            throw new WhoopAPIError(
                `WHOOP API request failed: ${response.statusText}`,
                response.status
            )
        }

        const data = await response.json()

        return successResponse(data, 200)

    } catch (error: any) {
        if (error instanceof AuthError) {
            return errorResponse(error.message, error.statusCode, error.code)
        }

        if (error instanceof RateLimitError) {
            return errorResponse(
                error.message,
                error.statusCode,
                error.code
            )
        }

        if (error instanceof WhoopAPIError) {
            return errorResponse(error.message, error.statusCode, error.code)
        }

        console.error('Recovery API error:', error)
        return errorResponse('Internal server error', 500)
    }
}
