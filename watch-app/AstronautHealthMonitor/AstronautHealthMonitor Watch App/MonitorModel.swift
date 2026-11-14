import Foundation
import Observation
import WatchKit

/// Drives the watch: pull a sample, post it, check for alerts. Once every 3 s.
@Observable
final class MonitorModel {

    private(set) var heartRate: Double = 0
    private(set) var alert: VitalsAlert?
    private(set) var isConnected = false
    /// Full vitals + the astronaut's own baseline, refreshed each tick.
    /// nil until the backend answers; the HR readout works without it.
    private(set) var snapshot: VitalsSnapshot?

    private let source: VitalsSource
    private let api: APIClient
    private var loop: Task<Void, Never>?

    /// Last alert we haptic'd for, so a persisting alert buzzes once, not forever.
    private var lastAlertID: String?

    init(source: VitalsSource = SimulatedSource(), api: APIClient = APIClient()) {
        self.source = source
        self.api = api
    }

    func start() {
        guard loop == nil else { return }
        loop = Task { [weak self] in
            while !Task.isCancelled {
                await self?.tick()
                try? await Task.sleep(for: .seconds(3))
            }
        }
    }

    func stop() {
        loop?.cancel()
        loop = nil
    }

    func simulateExertion() {
        source.simulateExertion()
    }

    private func tick() async {
        let bpm = source.nextSample()
        heartRate = bpm

        do {
            try await api.ingest(heartRate: bpm)
            isConnected = true

            snapshot = try await api.vitals()

            let newest = try await api.alerts().last
            if newest?.id != lastAlertID {
                lastAlertID = newest?.id
                alert = newest
                // Haptic only on a NEW alert — same rule as the backend's
                // new-match gate, for the same reason.
                if newest != nil {
                    WKInterfaceDevice.current().play(.notification)
                }
            }
        } catch {
            // Backend not up yet, or it fell over. Keep sampling and showing
            // heart rate — the watch must never go blank mid-demo. The last
            // snapshot stays on screen rather than blanking the vitals list.
            isConnected = false
        }
    }
}
