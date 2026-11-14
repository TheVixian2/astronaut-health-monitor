import SwiftUI

struct ContentView: View {
    @State private var model = MonitorModel()

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                if let alert = model.alert {
                    AlertBanner(alert: alert)
                }

                HeartRateCard(bpm: model.heartRate, isConnected: model.isConnected)

                #if DEBUG
                Button("Simulate exertion") {
                    model.simulateExertion()
                }
                .font(.footnote)
                .buttonStyle(.bordered)
                #endif
            }
            .padding(.horizontal, 2)
        }
        .onAppear { model.start() }
        .onDisappear { model.stop() }
    }
}

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
                .foregroundStyle(.primary)
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

struct HeartRateCard: View {
    let bpm: Double
    let isConnected: Bool

    var body: some View {
        VStack(spacing: 1) {
            HStack(spacing: 4) {
                Image(systemName: "heart.fill")
                    .foregroundStyle(.pink)
                    .font(.caption)
                Text("HEART RATE")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Text(bpm > 0 ? "\(Int(bpm))" : "--")
                .font(.system(size: 46, weight: .semibold, design: .rounded))
                .contentTransition(.numericText())
                .animation(.default, value: bpm)
            Text(isConnected ? "bpm" : "bpm · offline")
                .font(.caption2)
                .foregroundStyle(isConnected ? Color.secondary : Color.orange)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
    }
}

#Preview {
    ContentView()
}
