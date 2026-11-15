// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
import Foundation

/// Heart rate as a random walk around a resting baseline, with mean reversion
/// so it wanders like a real signal instead of drifting away or jittering.
///
/// There is no physical watch in this project, so this is the source used for
/// the entire demo. `HealthKitSource` exists only as a placeholder.
final class SimulatedSource: VitalsSource {

    private let restingBpm: Double
    private var current: Double

    /// Ticks of elevated heart rate still owed to a "Simulate exertion" press.
    private var exertionTicksRemaining = 0

    /// ~2 minutes at one sample every 3 s — long enough to show and talk over,
    /// short enough to recover before the next demo run.
    private static let exertionTicks = 40

    init(restingBpm: Double = 58) {  // a1's normal in backend/engine.py CREW
        self.restingBpm = restingBpm
        self.current = restingBpm
    }

    func nextSample() -> Double {
        let target: Double
        if exertionTicksRemaining > 0 {
            exertionTicksRemaining -= 1
            target = restingBpm * 1.75
        } else {
            target = restingBpm
        }
        current += Double.random(in: -1.5...1.5) + (target - current) * 0.12
        current = min(max(current, 40), 200)
        return current.rounded()
    }

    func simulateExertion() {
        exertionTicksRemaining = Self.exertionTicks
    }
}
