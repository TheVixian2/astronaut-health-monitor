import Foundation

/// A source of heart-rate samples.
///
/// Heart rate is the ONLY real signal in this project — every other vital is
/// simulated server-side. The watch pulls one sample per tick and posts it.
protocol VitalsSource: AnyObject {
    /// The next heart-rate sample, in bpm.
    func nextSample() -> Double

    /// Debug builds only: ramp the heart rate so a presenter can trigger an
    /// alert live during the demo.
    func simulateExertion()
}
