import Foundation

/// One reading from the watch's own sensors.
struct WatchSample {
    let heartRateBpm: Double
    /// Heart-rate variability (SDNN). Lower HRV tracks stress and depression
    /// (Kemp et al. 2010 meta-analysis), and the watch measures it for free.
    let hrvSdnnMs: Double
    /// Active minutes so far today. Crews grew steadily more sedentary over the
    /// 520-day Mars-500 isolation study (Basner et al. 2013).
    let activeMin: Double
}

/// A source of watch readings. There is no physical watch in this project:
/// `SimulatedSource` provides everything; `HealthKitSource` is a stub.
protocol VitalsSource: AnyObject {
    func nextSample() -> WatchSample

    /// The wearer's normal HRV and daily active minutes. PROVISIONAL: these move
    /// to the backend's stored mission days 7-14 once it stores HRV and activity.
    var hrvBaselineMs: Double { get }
    var activeMinBaseline: Double { get }

    /// Debug builds only: ramp the heart rate so a presenter can show it live.
    func simulateExertion()
}
