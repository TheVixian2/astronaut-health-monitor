import Foundation

/// Heart rate, HRV and activity as random walks with mean reversion, so they
/// wander like real signals instead of drifting away or jittering.
///
/// There is no physical watch in this project, so this is the source used for
/// the entire demo. `HealthKitSource` exists only as a placeholder.
final class SimulatedSource: VitalsSource {

    private let restingBpm: Double
    private var current: Double
    let hrvBaselineMs: Double
    private var hrv: Double
    let activeMinBaseline: Double
    private var activeMin: Double

    /// Ticks of elevated heart rate still owed to a "Simulate exertion" press.
    private var exertionTicksRemaining = 0

    /// ~2 minutes at one sample every 3 s — long enough to show and talk over,
    /// short enough to recover before the next demo run.
    private static let exertionTicks = 40

    init(restingBpm: Double = 58,  // a1's normal in backend/engine.py CREW
          hrvBaselineMs: Double = 55, activeMinBaseline: Double = 45) {
        self.restingBpm = restingBpm
        self.current = restingBpm
        self.hrvBaselineMs = hrvBaselineMs
        self.hrv = hrvBaselineMs
        self.activeMinBaseline = activeMinBaseline
        self.activeMin = activeMinBaseline * 0.55   // partway through the day
    }

    func nextSample() -> WatchSample {
        let exerting = exertionTicksRemaining > 0
        if exerting { exertionTicksRemaining -= 1 }

        // Exertion: heart rate up, HRV down, activity accumulates faster.
        let hrTarget = exerting ? restingBpm * 1.75 : restingBpm
        current += Double.random(in: -1.5...1.5) + (hrTarget - current) * 0.12
        current = min(max(current, 40), 200)

        let hrvTarget = exerting ? hrvBaselineMs * 0.55 : hrvBaselineMs
        hrv += Double.random(in: -1.5...1.5) + (hrvTarget - hrv) * 0.1
        hrv = min(max(hrv, 10), 150)

        activeMin += exerting ? 0.5 : 0.02

        return WatchSample(heartRateBpm: current.rounded(), hrvSdnnMs: hrv.rounded(),
                           activeMin: (activeMin * 10).rounded() / 10)
    }

    func simulateExertion() {
        exertionTicksRemaining = Self.exertionTicks
    }
}
