// app/api/whoop/auth/callback/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { setTokens } from '@/lib/api/tokens'
import { errorResponse } from '@/lib/api/response'

const WHOOP_TOKEN_URL = 'https://api.prod.whoop.com/oauth/oauth2/token'

export async function GET(request: NextRequest) {
    try {
        const searchParams = request.nextUrl.searchParams
        const code = searchParams.get('code')
        const state = searchParams.get('state')
        const storedState = request.cookies.get('oauth_state')?.value

        // Verify state (CSRF protection)
        if (!state || state !== storedState) {
            return errorResponse('Invalid state parameter', 400)
        }

        if (!code) {
            return errorResponse('Authorization code missing', 400)
        }

        // Exchange code for tokens
        const response = await fetch(WHOOP_TOKEN_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                grant_type: 'authorization_code',
                code,
                client_id: process.env.WHOOP_CLIENT_ID!,
                client_secret: process.env.WHOOP_CLIENT_SECRET!,
                redirect_uri: process.env.WHOOP_REDIRECT_URI!,
            }),
        })

        if (!response.ok) {
            const error = await response.text()
            console.error('Token exchange error:', error)
            return errorResponse('Failed to exchange authorization code', response.status)
        }

        const tokenData = await response.json()

        if (!tokenData.expires_in) {
            console.warn("[WHOOP] Token response missing expires_in; defaulting to 3600");
        }
        const expiresIn = tokenData.expires_in ?? 3600;

        // Calculate expiration time
        const expires_at = Math.floor(Date.now() / 1000) + expiresIn

        // Store tokens in HTTP-only cookies
        await setTokens({
            access_token: tokenData.access_token,
            refresh_token: tokenData.refresh_token,
            expires_at,
        }, expiresIn)

        // Clear state cookie and redirect to dashboard
        const successRedirect = NextResponse.redirect(
            new URL('/dashboard', request.url)
        )
        successRedirect.cookies.delete('oauth_state')

        return successRedirect

    } catch (error) {
        console.error('OAuth callback error:', error)
        return errorResponse('Authentication failed', 500)
    }
}
