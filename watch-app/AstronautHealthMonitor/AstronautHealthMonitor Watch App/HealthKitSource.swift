import Foundation

/// Placeholder for real readings from HealthKit.
///
/// TODO: unused — this project has no physical watch, so every reading comes
/// from `SimulatedSource` via the watchOS Simulator. If a real device is ever
/// added: request authorisation for `.heartRate`, `.heartRateVariabilitySDNN`
/// and `.appleExerciseTime`, run `HKAnchoredObjectQuery`s, and surface the
/// newest samples through `nextSample()`. HealthKit needs the entitlement plus
/// usage descriptions in the target's Info settings.
final class HealthKitSource: VitalsSource {

    let hrvBaselineMs: Double = 0
    let activeMinBaseline: Double = 0

    func nextSample() -> WatchSample {
        assertionFailure("HealthKitSource is a stub — use SimulatedSource")
        return WatchSample(heartRateBpm: 0, hrvSdnnMs: 0, activeMin: 0)
    }

    func simulateExertion() {
        // No-op: a real heart cannot be asked to speed up on command.
    }
}
