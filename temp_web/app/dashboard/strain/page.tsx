import { Suspense } from 'react'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { StrainChart } from '@/components/charts/StrainChart'
import { WorkoutDistributionChart } from '@/components/charts/WorkoutDistributionChart'
import { DashboardSkeleton } from '@/components/auth/DashboardSkeleton'

export const metadata = {
    title: 'Strain | WHOOP Insights',
}

export default function StrainPage() {
    return (
        <Suspense fallback={<DashboardSkeleton />}>
            <StrainContent />
        </Suspense>
    )
}

const mockData = {
    trend: [
        { date: 'Mon', strain: 12.5, calories: 2100 },
        { date: 'Tue', strain: 15.2, calories: 2450 },
        { date: 'Wed', strain: 10.1, calories: 1900 },
        { date: 'Thu', strain: 18.4, calories: 2800 },
        { date: 'Fri', strain: 14.2, calories: 2300 },
        { date: 'Sat', strain: 11.5, calories: 2050 },
        { date: 'Sun', strain: 14.5, calories: 2350 },
    ],
    distribution: [
        { sport: 'Cycling', count: 4, totalStrain: 16.5 },
        { sport: 'Running', count: 2, totalStrain: 14.2 },
        { sport: 'Weightlifting', count: 3, totalStrain: 12.8 },
        { sport: 'Swimming', count: 1, totalStrain: 11.5 },
    ],
}

async function StrainContent() {
    return (
        <PageContainer>
            <PageHeader
                title="Strain"
                subtitle="Physical exertion and activity tracking"
            />

            <div className="space-y-6">
                <StrainChart data={mockData.trend} />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <WorkoutDistributionChart data={mockData.distribution} />
                    {/* More strain widgets can go here */}
                </div>
            </div>
        </PageContainer>
    )
}
