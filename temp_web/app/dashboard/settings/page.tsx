import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'

export const metadata = {
    title: 'Settings',
}

export default function SettingsPage() {
    return (
        <PageContainer>
            <PageHeader
                title="Settings"
                subtitle="Manage your preferences"
            />

            {/* Placeholder content */}
            <div className="rounded-xl border border-border/50 bg-card p-8 text-center">
                <p className="text-muted-foreground">
                    Settings coming soon...
                </p>
            </div>
        </PageContainer>
    )
}
