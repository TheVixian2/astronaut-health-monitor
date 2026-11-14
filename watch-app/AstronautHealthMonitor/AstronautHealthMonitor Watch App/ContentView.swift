import SwiftUI

struct ContentView: View {
    @State private var model = MonitorModel()

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                if let alert = model.alert {
                    AlertBanner(alert: alert)
                }

                HeartRateCard(
                    bpm: model.heartRate,
                    baseline: model.snapshot?.baseline.heartRateBpm,
                    isConnected: model.isConnected
                )

                if let s = model.snapshot {
                    VitalsList(snapshot: s)
                }

                #if DEBUG
                Button("Simulate exertion") {
                    model.simulateExertion()
                }
                .font(.footnote)
                .buttonStyle(.bordered)
                .padding(.top, 2)
                #endif
            }
            .padding(.horizontal, 2)
        }
        .onAppear { model.start() }
        .onDisappear { model.stop() }
    }
}

// MARK: - Alert

/// Condition name, severity colour, and the ONE pre-written action line.
/// Nothing else — the long Claude explanation lives on the web app.
struct AlertBanner: View {
    let alert: VitalsAlert

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(alert.profile.replacingOccurrences(of: "_", with: " ").uppercased())
                .font(.caption2.bold())
                .foregroundStyle(tint)
            Text(alert.onboardAction)
                .font(.footnote)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(8)
        .background(tint.opacity(0.22), in: RoundedRectangle(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(tint, lineWidth: 1.5))
    }

    private var tint: Color {
        switch alert.severity {
        case "critical": .red
        case "alert":    .orange
        default:         .yellow
        }
    }
}

// MARK: - Heart rate

struct HeartRateCard: View {
    let bpm: Double
    let baseline: Double?
    let isConnected: Bool

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 4) {
                Image(systemName: "heart.fill").foregroundStyle(.pink).font(.caption2)
                Text("HEART RATE").font(.caption2).foregroundStyle(.secondary)
            }
            Text(bpm > 0 ? "\(Int(bpm))" : "--")
                .font(.system(size: 44, weight: .semibold, design: .rounded))
                .contentTransition(.numericText())
                .animation(.default, value: bpm)

            if let base = baseline, bpm > 0 {
                // The whole point of the product: compared to THEIR normal,
                // not to a population threshold.
                Deviation(value: bpm, baseline: base, mode: .percent)
                    .font(.caption2)
            } else {
                Text(isConnected ? "bpm" : "bpm · offline")
                    .font(.caption2)
                    .foregroundStyle(isConnected ? Color.secondary : Color.orange)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 4)
    }
}

// MARK: - Other vitals

struct VitalsList: View {
    let snapshot: VitalsSnapshot

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("VS YOUR BASELINE").font(.system(size: 9)).foregroundStyle(.secondary)
                Spacer()
            }
            .padding(.bottom, 3)

            VitalRow(label: "SpO₂", value: snapshot.spo2Pct, baseline: snapshot.baseline.spo2Pct,
                     format: "%.0f%%", mode: .points(warn: 2, bad: 4))
            VitalRow(label: "Temp", value: snapshot.tempC, baseline: snapshot.baseline.tempC,
                     format: "%.1f°C", mode: .points(warn: 0.5, bad: 1.0))
            VitalRow(label: "Resp", value: snapshot.respRateBpm, baseline: snapshot.baseline.respRateBpm,
                     format: "%.0f", mode: .percent)
            VitalRow(label: "Sleep", value: snapshot.sleepHLastNight, baseline: snapshot.baseline.sleepHLastNight,
                     format: "%.1fh", mode: .points(warn: 1.0, bad: 2.0))
            VitalRow(label: "Mood", value: Double(snapshot.mood1To5), baseline: Double(snapshot.baseline.mood1To5),
                     format: "%.0f/5", mode: .points(warn: 1, bad: 2))
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 6)
        .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 9))
    }
}

struct VitalRow: View {
    let label: String
    let value: Double
    let baseline: Double
    let format: String
    let mode: DeviationMode

    var body: some View {
        HStack(spacing: 4) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            Spacer(minLength: 2)
            Text(String(format: format, value))
                .font(.caption.monospacedDigit())
            Deviation(value: value, baseline: baseline, mode: mode)
                .font(.system(size: 9).monospacedDigit())
                .frame(width: 34, alignment: .trailing)
        }
        .padding(.vertical, 1.5)
    }
}

// MARK: - Deviation

/// How far a value sits from this astronaut's own baseline.
///
/// `percent` suits heart rate and respiratory rate. `points` exists because
/// percentage is misleading for some vitals — SpO₂ 98 → 93 is only a 5%
/// deviation but a serious desaturation, so it is judged in absolute points.
enum DeviationMode {
    case percent
    case points(warn: Double, bad: Double)
}

struct Deviation: View {
    let value: Double
    let baseline: Double
    let mode: DeviationMode

    var body: some View {
        Text(text).foregroundStyle(tint)
    }

    private var delta: Double { value - baseline }

    private var text: String {
        switch mode {
        case .percent:
            guard baseline != 0 else { return "—" }
            let pct = delta / baseline * 100
            return abs(pct) < 1 ? "—" : String(format: "%+.0f%%", pct)
        case .points:
            return abs(delta) < 0.05 ? "—" : String(format: "%+.1f", delta)
        }
    }

    private var tint: Color {
        switch mode {
        case .percent:
            guard baseline != 0 else { return .secondary }
            let pct = abs(delta / baseline * 100)
            if pct >= 25 { return .red }
            if pct >= 12 { return .orange }
            return .secondary
        case .points(let warn, let bad):
            let d = abs(delta)
            if d >= bad { return .red }
            if d >= warn { return .orange }
            return .secondary
        }
    }
}

#Preview {
    ContentView()
}
