import Foundation
import Observation
import WatchKit

/// Drives the watch: pull a sample, post it, refresh vitals. Once every 3 s.
/// The chart and the sleep log are refreshed every 30 s.
@Observable
final class MonitorModel {

    private(set) var sample: WatchSample?
    private(set) var alert: VitalsAlert?
    private(set) var isConnected = false
    /// Full vitals + the astronaut's own baseline, refreshed each tick.
    /// nil until the backend answers; the watch's own readings work without it.
    private(set) var snapshot: VitalsSnapshot?
    /// Stored heart rate over the last hour, oldest first.
    private(set) var hrHistory: [HistoryPoint] = []
    /// The last 7 nights from the on-board lighting log, oldest first.
    private(set) var nights: [SleepNight] = []

    var hrvBaselineMs: Double { source.hrvBaselineMs }
    var activeMinBaseline: Double { source.activeMinBaseline }

    private let source: VitalsSource
    private let api: APIClient
    private var loop: Task<Void, Never>?
    private var ticks = 0

    /// Last alert we haptic'd for, so a persisting alert buzzes once, not forever.
    private var lastAlertID: String?

    /// Psychological flags never show on the watch: they go to the commander
    /// first (team decision 2026-11-14). Only other alerts reach the wrist.
    private static let psychological: Set<String> = ["sleep_debt"]

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
        let s = source.nextSample()
        sample = s

        do {
            try await api.ingest(s)
            isConnected = true

            snapshot = try await api.vitals()

            if ticks % 10 == 0 {
                hrHistory = try await api.lastHour()
                nights = try await api.sleepNights()
            }
            ticks += 1

            let newest = try await api.alerts().last { !Self.psychological.contains($0.profile) }
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
            // the watch's own readings — the watch must never go blank mid-demo.
            isConnected = false
        }
    }
}
