// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
import Foundation
import Observation
import WatchKit

/// Something that cannot wait for Mission Control: the round trip to Earth is longer
/// than the time there is to act. Shown as a full-screen pop-up with a haptic.
struct UrgentNotice: Identifiable, Equatable {
    let id: String
    let title: String
    let action: String
    let roundTripMin: Int
    let detail: String
}

/// Drives the watch: post the heart-rate sample, then read everything else from the
/// backend (the single source of truth). Once every 3 s; chart and sleep log every 30 s.
@Observable
final class MonitorModel {

    private(set) var heartRate: Double = 0
    private(set) var alert: VitalsAlert?
    private(set) var isConnected = false
    /// Full vitals + the astronaut's own baseline, refreshed each tick.
    private(set) var snapshot: VitalsSnapshot?
    /// Stored heart rate over the last hour, oldest first.
    private(set) var hrHistory: [HistoryPoint] = []
    /// The last 7 nights from the on-board lighting log, oldest first.
    private(set) var nights: [SleepNight] = []
    /// Real ISS cabin air (NASA ISS Live), or a clearly labelled demo override.
    private(set) var cabin: CabinAir?
    /// The current "can't wait for Earth" pop-up, if any. The view clears it on dismiss.
    var urgent: UrgentNotice?

    private let source: VitalsSource
    private let api: APIClient
    private var loop: Task<Void, Never>?
    private var ticks = 0
    private var realOneWayDelayS = 1320

    /// Last alert / urgent notice we haptic'd for, so each buzzes once, not forever.
    private var lastAlertID: String?
    private var lastUrgentID: String?

    /// Psychological flags never show on the watch (team decision 2026-11-14): they go to
    /// the commander first, and the wellbeing level is never on the wrist.
    private static let psychological: Set<String> = ["sleep_debt", "wellbeing_concern", "wellbeing_urgent"]

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

    /// Ask Claude (through the backend) about the wearer's own physical data or the cabin.
    func ask(_ question: String) async -> AskAnswer {
        do {
            return try await api.ask(question)
        } catch {
            return AskAnswer(answer: "Can't reach the station computer right now. Try again in a moment.",
                             source: "offline")
        }
    }

    private func tick() async {
        let bpm = source.nextSample()
        heartRate = bpm

        do {
            try await api.ingest(heartRate: bpm)
            isConnected = true
            snapshot = try await api.vitals()

            if ticks % 10 == 0 {
                hrHistory = try await api.lastHour()
                nights = try await api.sleepNights()
                cabin = try? await api.cabinAir()
                if let d = try? await api.realOneWayDelayS() { realOneWayDelayS = d }
            }
            ticks += 1

            // The backend lists alerts newest first, and leaves out unreleased psychological ones
            // for the astronaut themselves (?viewer=); the watch also skips released ones.
            let newest = try await api.alerts().first { !Self.psychological.contains($0.profile) }
            if newest?.id != lastAlertID {
                lastAlertID = newest?.id
                alert = newest
                if newest != nil {
                    WKInterfaceDevice.current().play(.notification)
                }
            }
            checkUrgent()
        } catch {
            // Backend not up yet, or it fell over. Keep sampling and showing heart rate —
            // the watch must never go blank mid-demo. The last snapshot stays on screen.
            isConnected = false
        }
    }

    /// Urgent = it cannot wait for a reply from Earth: the round trip (2 x real light time)
    /// is longer than the time there is to act.
    private func checkUrgent() {
        let roundTrip = 2 * realOneWayDelayS
        var notice: UrgentNotice?
        if let c = cabin, c.status == "above_limit" {
            let co2 = c.co21hAvgMmhg ?? c.co2Mmhg ?? 0
            notice = UrgentNotice(
                id: "cabin-co2-\(c.demoOverride == true ? "demo" : "live")",
                title: "Cabin CO₂ \(String(format: "%.1f", co2)) mmHg",
                action: "Move to a ventilated module and check the CO₂ scrubber now.",
                roundTripMin: roundTrip / 60,
                detail: "NASA limit \(String(format: "%g", c.co2LimitMmhg)) mmHg. Headaches and poorer sleep start around 3 mmHg."
                    + (c.demoOverride == true ? " DEMO OVERRIDE, not real ISS data." : " Live ISS reading."))
        } else if let a = alert, ["alert", "critical"].contains(a.severity), roundTrip > a.actWithinS {
            notice = UrgentNotice(id: a.id, title: a.profile.replacingOccurrences(of: "_", with: " ").capitalized,
                                  action: a.onboardAction, roundTripMin: roundTrip / 60,
                                  detail: "Act within \(a.actWithinS / 60) min.")
        }
        guard let n = notice else { lastUrgentID = nil; return }
        if n.id != lastUrgentID {
            lastUrgentID = n.id
            urgent = n
            WKInterfaceDevice.current().play(.failure)
        }
    }
}
