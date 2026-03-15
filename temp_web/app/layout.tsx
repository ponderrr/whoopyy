import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import { APP_NAME, APP_DESCRIPTION } from "@/lib/constants"
import { AuthProvider } from "@/lib/auth/context"
import { SessionRefreshToast } from "@/components/auth/SessionRefreshToast"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: {
    default: APP_NAME,
    template: `%s | ${APP_NAME}`,
  },
  description: APP_DESCRIPTION,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <AuthProvider>
          {children}
          <SessionRefreshToast />
        </AuthProvider>
      </body>
    </html>
  )
}
