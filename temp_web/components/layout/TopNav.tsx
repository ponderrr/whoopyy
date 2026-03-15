'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils/cn'
import { ROUTES } from '@/lib/constants'

interface NavLinkProps {
    href: string
    children: React.ReactNode
    active?: boolean
}

function NavLink({ href, children, active }: NavLinkProps) {
    return (
        <Link
            href={href}
            className={cn(
                "text-sm font-medium transition-colors",
                active
                    ? "text-foreground"
                    : "text-muted-foreground hover:text-foreground"
            )}
        >
            {children}
        </Link>
    )
}

import { useAuth } from '@/lib/auth/context'

/**
 * Avatar - Text-only representation of user.
 * Design rule: No icons, no images in nav.
 */
function AvatarText({ initials }: { initials: string }) {
    return (
        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-secondary border border-border/50 text-[10px] font-semibold text-foreground tracking-tighter uppercase">
            {initials}
        </div>
    )
}

export function TopNav() {
    const pathname = usePathname()
    const { user, logout } = useAuth()

    const navLinks = [
        { href: ROUTES.DASHBOARD, label: 'Dashboard' },
        { href: ROUTES.RECOVERY, label: 'Recovery' },
        { href: ROUTES.SLEEP, label: 'Sleep' },
        { href: ROUTES.STRAIN, label: 'Strain' },
    ]

    const initials = user
        ? `${user.firstName.charAt(0)}${user.lastName.charAt(0)}`
        : '??'

    return (
        <nav className="border-b border-border bg-background px-6 py-4">
            <div className="flex items-center justify-between max-w-7xl mx-auto">
                {/* Left side - Navigation links (text only, NO icons, NO logo) */}
                <div className="flex items-center gap-8">
                    {navLinks.map((link) => {
                        // Rule: NO "Dashboard" redundant link if on dashboard page
                        if (link.href === ROUTES.DASHBOARD && pathname === ROUTES.DASHBOARD) {
                            return null
                        }

                        return (
                            <NavLink
                                key={link.href}
                                href={link.href}
                                active={pathname === link.href}
                            >
                                {link.label}
                            </NavLink>
                        )
                    })}
                </div>

                {/* Right side - User menu */}
                <div className="flex items-center gap-6">
                    <Link
                        href={ROUTES.SETTINGS}
                        className={cn(
                            "text-sm font-medium transition-colors",
                            pathname === ROUTES.SETTINGS
                                ? "text-foreground"
                                : "text-muted-foreground hover:text-foreground"
                        )}
                    >
                        Settings
                    </Link>

                    {user && (
                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => logout()}
                                className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                            >
                                Logout
                            </button>
                            <AvatarText initials={initials} />
                        </div>
                    )}
                </div>
            </div>
        </nav>
    )
}
