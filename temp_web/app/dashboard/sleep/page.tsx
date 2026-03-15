import { Suspense } from 'react'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { SleepChart } from '@/components/charts/SleepChart'
import { WidgetGrid } from '@/components/layout/WidgetGrid'
import { MetricWidget } from '@/components/widgets/MetricWidget'
import { DashboardSkeleton } from '@/components/auth/DashboardSkeleton'

export const metadata = {
    title: 'Sleep | WHOOP Insights',
}

export default function SleepPage() {
    return (
        <Suspense fallback={<DashboardSkeleton />}>
            <SleepContent />
        </Suspense>
    )
}

const mockData = {
    trend: [
        { date: 'Mon', hours: 7.2, performance: 88 },
        { date: 'Tue', hours: 8.1, performance: 95 },
        { date: 'Wed', hours: 6.5, performance: 75 },
        { date: 'Thu', hours: 7.8, performance: 90 },
        { date: 'Fri', hours: 7.5, performance: 85 },
        { date: 'Sat', hours: 8.5, performance: 98 },
        { date: 'Sun', hours: 7.5, performance: 92 },
    ],
}

async function SleepContent() {
    return (
        <PageContainer>
            <PageHeader
                title="Sleep"
                subtitle="Rest and regeneration analysis"
            />

            <div className="mb-6">
                <SleepChart data={mockData.trend} />
            </div>

            <WidgetGrid columns={3}>
                <MetricWidget label="Total Sleep" value={7.5} unit="hrs" />
                <MetricWidget label="Efficiency" value={92} unit="%" />
                <MetricWidget label="Disturbances" value={2} />
            </WidgetGrid>
        </PageContainer>
    )
}
