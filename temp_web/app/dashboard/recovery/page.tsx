import { Suspense } from 'react'
import { PageContainer } from '@/components/layout/PageContainer'
import { PageHeader } from '@/components/layout/PageHeader'
import { WidgetGrid } from '@/components/layout/WidgetGrid'
import { RecoveryTrendChart } from '@/components/charts/RecoveryTrendChart'
import { RecoveryGauge } from '@/components/charts/RecoveryGauge'
import { MetricWidget } from '@/components/widgets/MetricWidget'
import { DashboardSkeleton } from '@/components/auth/DashboardSkeleton'

export const metadata = {
    title: 'Recovery | WHOOP Insights',
}

export default function RecoveryPage() {
    return (
        <Suspense fallback={<DashboardSkeleton />}>
            <RecoveryContent />
        </Suspense>
    )
}

// Mock data (matches Phase 22 & 30.3)
const mockData = {
    gauge: {
        score: 85,
        zone: 'optimal' as const,
    },
    trend: [
        { date: 'Mon', recovery: 65, hrv: 58 },
        { date: 'Tue', recovery: 82, hrv: 64 },
        { date: 'Wed', recovery: 45, hrv: 52 },
        { date: 'Thu', recovery: 78, hrv: 62 },
        { date: 'Fri', recovery: 92, hrv: 68 },
        { date: 'Sat', recovery: 88, hrv: 65 },
        { date: 'Sun', recovery: 85, hrv: 65 },
    ],
}

async function RecoveryContent() {
    return (
        <PageContainer>
            <PageHeader
                title="Recovery"
                subtitle="Daily physiological readiness"
            />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left: Score Gauge */}
                <div className="lg:col-span-1">
                    <RecoveryGauge {...mockData.gauge} />
                </div>

                {/* Right: Trend Chart */}
                <div className="lg:col-span-2">
                    <RecoveryTrendChart data={mockData.trend} showHRV={true} />
                </div>
            </div>

            <div className="mt-6">
                <WidgetGrid columns={3}>
                    <MetricWidget
                        label="Resting HR"
                        value={52}
                        unit="bpm"
                    />
                    <MetricWidget
                        label="HRV (Avg)"
                        value={62}
                        unit="ms"
                    />
                    <MetricWidget
                        label="Resp Rate"
                        value={14.5}
                        unit="rpm"
                    />
                </WidgetGrid>
            </div>
        </PageContainer>
    )
}
