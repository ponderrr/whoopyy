// app/api/whoop/auth/login/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { errorResponse } from '@/lib/api/response'

const WHOOP_OAUTH_URL = 'https://api.prod.whoop.com/oauth/oauth2/auth'

export async function GET(request: NextRequest) {
    try {
        const clientId = process.env.WHOOP_CLIENT_ID
        const redirectUri = process.env.WHOOP_REDIRECT_URI

        if (!clientId || !redirectUri) {
            return errorResponse('OAuth configuration missing', 500)
        }

        // Generate random state for CSRF protection
        const state = crypto.randomUUID()

        // Build OAuth URL
        const authUrl = new URL(WHOOP_OAUTH_URL)
        authUrl.searchParams.set('client_id', clientId)
        authUrl.searchParams.set('redirect_uri', redirectUri)
        authUrl.searchParams.set('response_type', 'code')
        authUrl.searchParams.set('state', state)
        authUrl.searchParams.set('scope', [
            'read:profile',
            'read:body_measurement',
            'read:cycles',
            'read:recovery',
            'read:sleep',
            'read:workout',
            'offline', // For refresh token
        ].join(' '))

        // Create response that redirects to WHOOP
        const response = NextResponse.redirect(authUrl.toString())

        // Store state in cookie for verification on callback
        response.cookies.set('oauth_state', state, {
            httpOnly: true,
            secure: true,
            sameSite: 'lax',
            maxAge: 600, // 10 minutes
            path: '/',
        })

        return response

    } catch (error) {
        console.error('OAuth login error:', error)
        return errorResponse('Failed to initiate OAuth flow', 500)
    }
}
