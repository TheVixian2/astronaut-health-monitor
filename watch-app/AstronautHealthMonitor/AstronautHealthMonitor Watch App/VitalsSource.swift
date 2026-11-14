// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
import Foundation

/// A source of heart-rate samples.
///
/// The watch is the heart-rate sensor: it posts one sample per tick. Everything else it
/// shows (HRV, activity, sleep, SpO2, temperature, breathing, cabin air) comes from the
/// backend, the single source of truth, so the watch and the web always show the same numbers.
protocol VitalsSource: AnyObject {
    /// The next heart-rate sample, in bpm.
    func nextSample() -> Double

    /// Debug builds only: ramp the heart rate so a presenter can show it live.
    func simulateExertion()
}
