import { cn } from "@/lib/utils/cn"

export interface Workout {
    id: string
    name: string
    strain: number
    duration: string
    calories: number
}

interface WorkoutGridWidgetProps {
    workouts: Workout[]
    className?: string
}

/**
 * WorkoutGridWidget - Displays a summary of recent physical activities.
 * 
 * Design Rules:
 * 1. Rich charcoal background (#131316)
 * 2. Everything centered
 * 3. Uppercase labels with tracking-wider
 * 4. Tabular numbers for metrics
 * 5. Near-invisible borders
 */
export function WorkoutGridWidget({ workouts, className }: WorkoutGridWidgetProps) {
    if (workouts.length === 0) {
        return (
            <div className={cn("rounded-xl border border-border/50 bg-card p-5 flex flex-col items-center justify-center min-h-[200px]", className)}>
                <p className="text-sm text-muted-foreground uppercase tracking-wider font-medium">No Recent Workouts</p>
            </div>
        )
    }

    return (
        <div className={cn("rounded-xl border border-border/50 bg-card p-5", className)}>
            {/* Main Label */}
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground text-center mb-6">
                Recent Workouts
            </p>

            <div className="space-y-8">
                {workouts.map((workout, index) => (
                    <div key={workout.id} className={cn(
                        "flex flex-col items-center",
                        index !== workouts.length - 1 && "pb-8 border-b border-border/50"
                    )}>
                        {/* Workout Name */}
                        <h3 className="text-lg font-semibold mb-3 text-center">
                            {workout.name}
                        </h3>

                        {/* Metrics Grid */}
                        <div className="grid grid-cols-3 gap-8 w-full max-w-sm">
                            <div className="text-center">
                                <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground mb-1">
                                    Strain
                                </p>
                                <p className="text-base font-semibold tabular-nums text-warning">
                                    {workout.strain.toFixed(1)}
                                </p>
                            </div>
                            <div className="text-center">
                                <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground mb-1">
                                    Duration
                                </p>
                                <p className="text-base font-semibold tabular-nums text-foreground">
                                    {workout.duration}
                                </p>
                            </div>
                            <div className="text-center">
                                <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground mb-1">
                                    Calories
                                </p>
                                <p className="text-base font-semibold tabular-nums text-foreground">
                                    {workout.calories}
                                </p>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    )
}
