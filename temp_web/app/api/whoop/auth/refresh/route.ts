// app/api/whoop/auth/refresh/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { getRefreshToken, setTokens } from '@/lib/api/tokens'
import { successResponse, errorResponse } from '@/lib/api/response'
import { AuthError } from '@/lib/api/errors'

const WHOOP_TOKEN_URL = 'https://api.prod.whoop.com/oauth/oauth2/token'

export async function POST(request: NextRequest) {
    try {
        const refreshToken = await getRefreshToken()

        if (!refreshToken) {
            throw new AuthError('No refresh token available')
        }

        // Request new access token from WHOOP with retry on 5xx
        const fetchOptions = {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                grant_type: 'refresh_token',
                refresh_token: refreshToken,
                client_id: process.env.WHOOP_CLIENT_ID!,
                client_secret: process.env.WHOOP_CLIENT_SECRET!,
            }),
        }

        let refreshData: any = null;
        for (let attempt = 0; attempt < 3; attempt++) {
            const resp = await fetch(WHOOP_TOKEN_URL, fetchOptions);
            if (resp.ok) {
                refreshData = await resp.json();
                break;
            }
            if (resp.status >= 500 && attempt < 2) {
                await new Promise(r => setTimeout(r, 1000 * Math.pow(2, attempt)));
                continue;
            }
            return NextResponse.json({ error: "Token refresh failed" }, { status: 401 });
        }

        const tokens = refreshData

        const expiresIn = tokens.expires_in ?? 3600

        // Calculate new expiration time
        const expires_at = Math.floor(Date.now() / 1000) + expiresIn

        // Store new tokens in secure cookies
        await setTokens({
            access_token: tokens.access_token,
            refresh_token: tokens.refresh_token || refreshToken, // Use old if not rotated
            expires_at,
        }, expiresIn)

        return successResponse({ message: 'Token refreshed successfully' }, 200)

    } catch (error: any) {
        if (error instanceof AuthError) {
            return errorResponse(error.message, error.statusCode, error.code)
        }
        console.error('Token refresh error:', error)
        return errorResponse('Failed to refresh token', 500)
    }
}
