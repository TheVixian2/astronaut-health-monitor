import Charts
import SwiftUI

struct ContentView: View {
    @State private var model = MonitorModel()
    /// Starting page. `SIMCTL_CHILD_AHM_PAGE=2 xcrun simctl launch …` opens on a
    /// given page, which is how screenshots of every page are taken for the deck.
    @State private var page = Int(ProcessInfo.processInfo.environment["AHM_PAGE"] ?? "") ?? 0

    var body: some View {
        NavigationStack {
        TabView(selection: $page) {
            TodayPage(model: model).tag(0)
            HeartPage(model: model).tag(1)
            SleepPage(model: model).tag(2)
            ScrollView {
                if let s = model.snapshot {
                    VitalsList(snapshot: s)
                } else {
                    Text("Waiting for the station…").font(.footnote).foregroundStyle(.secondary)
                }
                if let c = model.cabin {
                    CabinCard(cabin: c).padding(.top, 6)
                }
            }
            .navigationTitle("Vitals")
            .tag(3)
        }
        .tabViewStyle(.verticalPage)
        }
        .sheet(item: $model.urgent) { UrgentView(notice: $0) }
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

// MARK: - Page 1: Today

/// Three rings, each filled to the share of the wearer's OWN normal:
/// sleep last night, HRV now, active minutes today. Deliberately not one
/// combined score: the wellbeing level is never shown on the watch.
struct TodayPage: View {
    let model: MonitorModel

    private var sleep: (Double, Double)? {
        guard let s = model.snapshot else { return nil }
        return (s.sleepHLastNight, s.baseline.sleepHLastNight)
    }

    var body: some View {
        VStack(spacing: 6) {
            if let alert = model.alert {
                AlertBanner(alert: alert)
            }
            ZStack {
                Ring(fraction: ratio(sleep?.0, sleep?.1), color: .indigo, width: 9)
                    .frame(width: 92, height: 92)
                Ring(fraction: ratio(model.snapshot?.hrvSdnnMs, model.snapshot?.baseline.hrvSdnnMs), color: .teal, width: 9)
                    .frame(width: 70, height: 70)
                Ring(fraction: ratio(model.snapshot?.activeMin, model.snapshot?.baseline.activeMin), color: .orange, width: 9)
                    .frame(width: 48, height: 48)
            }
            .padding(.top, 2)
            VStack(spacing: 1) {
                legend("Sleep", sleep.map { String(format: "%.1fh", $0.0) }, ratio(sleep?.0, sleep?.1), .indigo)
                legend("HRV", model.snapshot?.hrvSdnnMs.map { "\(Int($0)) ms" },
                       ratio(model.snapshot?.hrvSdnnMs, model.snapshot?.baseline.hrvSdnnMs), .teal)
                legend("Move", model.snapshot?.activeMin.map { "\(Int($0)) min" },
                       ratio(model.snapshot?.activeMin, model.snapshot?.baseline.activeMin), .orange)
            }
            .font(.caption2)
        }
        .navigationTitle("Today")
    }

    private func ratio(_ value: Double?, _ normal: Double?) -> Double {
        guard let v = value, let n = normal, n > 0 else { return 0 }
        return v / n
    }

    private func legend(_ name: String, _ value: String?, _ r: Double, _ color: Color) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text(name).foregroundStyle(.secondary)
            Spacer(minLength: 2)
            Text(value ?? "--").monospacedDigit()
            Text(r > 0 ? "\(Int((r * 100).rounded()))%" : "")
                .foregroundStyle(r >= 0.85 ? Color.secondary : .orange)
                .monospacedDigit()
                .lineLimit(1)
                .fixedSize()
                .frame(minWidth: 36, alignment: .trailing)
        }
    }
}

struct Ring: View {
    let fraction: Double
    let color: Color
    let width: CGFloat

    var body: some View {
        ZStack {
            Circle().stroke(color.opacity(0.22), lineWidth: width)
            Circle()
                .trim(from: 0, to: min(max(fraction, 0), 1))
                .stroke(color, style: StrokeStyle(lineWidth: width, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.easeOut(duration: 0.6), value: fraction)
        }
    }
}

// MARK: - Page 2: Heart

struct HeartPage: View {
    let model: MonitorModel

    private var points: [(Date, Double)] {
        model.hrHistory.compactMap { p in p.heartRateBpm.map { (p.ts, $0) } }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Image(systemName: "heart.fill").foregroundStyle(.pink).font(.caption)
                    Text(model.heartRate > 0 ? "\(Int(model.heartRate))" : "--")
                        .font(.system(size: 34, weight: .semibold, design: .rounded))
                        .contentTransition(.numericText())
                        .animation(.default, value: model.heartRate)
                    Text("bpm").font(.caption2).foregroundStyle(.secondary)
                    Spacer()
                    if model.heartRate > 0, let base = model.snapshot?.baseline.heartRateBpm {
                        Deviation(value: model.heartRate, baseline: base, mode: .percent).font(.caption2)
                    }
                }

                if points.count > 1 {
                    Chart {
                        ForEach(points, id: \.0) { p in
                            LineMark(x: .value("Time", p.0), y: .value("bpm", p.1))
                                .foregroundStyle(.pink)
                                .interpolationMethod(.catmullRom)
                        }
                        if let base = model.snapshot?.baseline.heartRateBpm {
                            RuleMark(y: .value("Your normal", base))
                                .foregroundStyle(.secondary)
                                .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                        }
                    }
                    .chartXAxis(.hidden)
                    .chartYScale(domain: .automatic(includesZero: false))
                    .frame(height: 64)
                    Text("Last hour · dashed = your normal").font(.system(size: 9)).foregroundStyle(.secondary)
                } else {
                    Text(model.isConnected ? "Loading history…" : "Offline — live reading only")
                        .font(.caption2).foregroundStyle(.orange)
                }

                HStack {
                    Text("HRV").foregroundStyle(.secondary)
                    Spacer()
                    Text(model.snapshot?.hrvSdnnMs.map { "\(Int($0)) ms" } ?? "--").monospacedDigit()
                    if let v = model.snapshot?.hrvSdnnMs, let base = model.snapshot?.baseline.hrvSdnnMs {
                        Deviation(value: v, baseline: base, mode: .percent)
                            .frame(width: 34, alignment: .trailing)
                    }
                }
                .font(.caption)
                .padding(.top, 2)

                #if DEBUG
                Button("Simulate exertion") { model.simulateExertion() }
                    .font(.footnote)
                    .buttonStyle(.bordered)
                    .padding(.top, 2)
                #endif
            }
            .padding(.horizontal, 4)
        }
        .navigationTitle("Heart")
    }
}

// MARK: - Page 3: Sleep

struct SleepPage: View {
    let model: MonitorModel

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(model.snapshot.map { String(format: "%.1f", $0.sleepHLastNight) } ?? "--")
                    .font(.system(size: 30, weight: .semibold, design: .rounded))
                Text("h last night").font(.caption2).foregroundStyle(.secondary)
            }
            if let usual = model.snapshot?.baseline.sleepHLastNight {
                Text(String(format: "Your usual: %.1f h", usual)).font(.caption2).foregroundStyle(.secondary)
            }
            if !model.nights.isEmpty {
                Chart {
                    ForEach(model.nights, id: \.nightOf) { n in
                        BarMark(x: .value("Night", String(n.nightOf.suffix(2))), y: .value("Hours", n.sleepH))
                            .foregroundStyle(.indigo.gradient)
                            .cornerRadius(3)
                    }
                    if let usual = model.snapshot?.baseline.sleepHLastNight {
                        RuleMark(y: .value("Usual", usual))
                            .foregroundStyle(.secondary)
                            .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    }
                }
                .chartYAxis(.hidden)
                .frame(height: 70)
                Text("Last 7 nights").font(.system(size: 9)).foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 4)
        .navigationTitle("Sleep")
    }
}

// MARK: - Cabin air (real ISS data)

struct CabinCard: View {
    let cabin: CabinAir

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(cabin.demoOverride == true ? "CABIN · DEMO OVERRIDE" : "CABIN · LIVE FROM ISS")
                .font(.system(size: 9)).foregroundStyle(cabin.demoOverride == true ? .orange : .secondary)
            HStack {
                Text("CO₂").font(.caption2).foregroundStyle(.secondary)
                Spacer()
                Text(cabin.co2Mmhg.map { String(format: "%.2f mmHg", $0) } ?? "--")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(cabin.status == "above_limit" ? .red : cabin.status == "elevated" ? .orange : .primary)
            }
            HStack {
                Text("Temp").font(.caption2).foregroundStyle(.secondary)
                Spacer()
                Text(cabin.cabinTempC.map { String(format: "%.1f°C", $0) } ?? "--").font(.caption.monospacedDigit())
            }
            Text(String(format: "NASA limit %g mmHg", cabin.co2LimitMmhg)).font(.system(size: 9)).foregroundStyle(.secondary)
        }
        .padding(6)
        .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 9))
    }
}

// MARK: - Urgent: can't wait for Mission Control

struct UrgentView: View {
    let notice: UrgentNotice

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Label("ACT NOW ON BOARD", systemImage: "exclamationmark.triangle.fill")
                    .font(.caption.bold()).foregroundStyle(.red)
                Text(notice.title).font(.headline)
                Text(notice.action).font(.footnote)
                Text("Mission Control is \(notice.roundTripMin) min away (round trip): don't wait for them.")
                    .font(.caption2).foregroundStyle(.orange)
                Text(notice.detail).font(.system(size: 10)).foregroundStyle(.secondary)
            }
        }
    }
}
