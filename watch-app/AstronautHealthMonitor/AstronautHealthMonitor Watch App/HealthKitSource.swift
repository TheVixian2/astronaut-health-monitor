import Foundation

/// Placeholder for real heart rate from HealthKit.
///
/// TODO: unused — this project has no physical watch, so every reading comes
/// from `SimulatedSource` via the watchOS Simulator. If a real device is ever
/// added: request authorisation for `HKQuantityType(.heartRate)`, run an
/// `HKAnchoredObjectQuery`, and surface the newest sample through
/// `nextSample()`. Remember HealthKit needs the entitlement plus usage
/// descriptions in the target's Info settings.
final class HealthKitSource: VitalsSource {

    func nextSample() -> Double {
        assertionFailure("HealthKitSource is a stub — use SimulatedSource")
        return 0
    }

    func simulateExertion() {
        // No-op: a real heart cannot be asked to speed up on command.
    }
}
