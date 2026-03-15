import { Suspense } from 'react'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { WidgetGrid } from '@/components/layout/WidgetGrid'
import { RecoveryWidget } from '@/components/widgets/RecoveryWidget'
import { SleepWidget } from '@/components/widgets/SleepWidget'
import { StrainWidget } from '@/components/widgets/StrainWidget'
import { HRVTrendWidget } from '@/components/widgets/HRVTrendWidget'
import { MetricWidget } from '@/components/widgets/MetricWidget'
import { DashboardSkeleton } from '@/components/auth/DashboardSkeleton'

export const metadata = {
    title: 'Dashboard | WHOOP Insights',
}

export default function DashboardPage() {
    return (
        <Suspense fallback={<DashboardSkeleton />}>
            <DashboardContent />
        </Suspense>
    )
}

// Mock data (matches Phase 20 instructions)
const mockData = {
    recovery: {
        score: 85,
        hrv: 65,
        rhr: 52,
        status: 'success' as const,
    },
    sleep: {
        hours: 7.5,
        performance: 92,
        efficiency: 88,
    },
    strain: {
        strain: 14.2,
        calories: 2450,
        workouts: 1,
    },
    hrv: {
        current: 65,
        average: 62,
        trend: 'up' as const,
    },
}

async function DashboardContent() {
    return (
        <PageContainer>
            <PageHeader
                title="Dashboard"
                subtitle="Your daily biometric overview"
            />

            {/* Main metrics */}
            <WidgetGrid columns={3}>
                <RecoveryWidget {...mockData.recovery} />
                <SleepWidget {...mockData.sleep} />
                <StrainWidget {...mockData.strain} />
            </WidgetGrid>

            {/* Secondary metrics */}
            <div className="mt-6">
                <WidgetGrid columns={4}>
                    <HRVTrendWidget {...mockData.hrv} />
                    <MetricWidget
                        label="Resting HR"
                        value={mockData.recovery.rhr}
                        unit="bpm"
                    />
                    <MetricWidget
                        label="Sleep Need"
                        value={8.0}
                        unit="hours"
                    />
                    <MetricWidget
                        label="Calories"
                        value={mockData.strain.calories.toLocaleString()}
                    />
                </WidgetGrid>
            </div>
        </PageContainer>
    )
}
