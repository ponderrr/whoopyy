// app/api/whoop/cycles/route.ts
import { NextRequest } from 'next/server'
import { getAccessToken, isTokenExpired } from '@/lib/api/tokens'
import { successResponse, errorResponse } from '@/lib/api/response'
import { AuthError, RateLimitError, WhoopAPIError } from '@/lib/api/errors'
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

        const searchParams = request.nextUrl.searchParams
        const limit = searchParams.get('limit') || '7'

        const response = await fetch(
            `${WHOOP_API_URL}/cycle?limit=${limit}`,
            {
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                },
                next: {
                    revalidate: CACHE_DURATIONS.CYCLES, // 1 hour cache
                    tags: ['cycles'],
                },
            }
        )

        if (response.status === 429) {
            const retryAfter = parseInt(
                response.headers.get('X-RateLimit-Reset') || '60'
            )
            throw new RateLimitError('Rate limit exceeded', retryAfter)
        }

        if (!response.ok) {
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
            return errorResponse(error.message, error.statusCode, error.code)
        }
        if (error instanceof WhoopAPIError) {
            return errorResponse(error.message, error.statusCode, error.code)
        }
        console.error('Cycles API error:', error)
        return errorResponse('Internal server error', 500)
    }
}
