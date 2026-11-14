import Foundation

/// An alert as the backend reports it.
///
/// Deliberately a subset of the Alert object in `docs/api-spec.md`: the watch
/// shows only the condition name, a severity colour and the one pre-written
/// `onboardAction` line. The long Claude `insight` is web-app only.
struct VitalsAlert: Decodable, Identifiable, Equatable {
    let id: String
    let profile: String
    let severity: String
    let bodyRegion: String
    let onboardAction: String
    let actWithinS: Int
    let groundEtaS: Int?
}

/// A full vitals snapshot with the astronaut's own baseline alongside it.
/// Only `heartRateBpm` is real; everything else is simulated server-side.
struct VitalsSnapshot: Decodable, Equatable {
    let heartRateBpm: Double
    let spo2Pct: Double
    let tempC: Double
    let respRateBpm: Double
    let sleepHLastNight: Double
    /// NOTE the capital T. The JSON key is `mood_1to5`, and
    /// `.convertFromSnakeCase` capitalises the first *letter* of each
    /// underscore-separated component — so `1to5` becomes `1To5`, not `1to5`.
    /// Renaming this to `mood1to5` makes every vitals decode fail silently,
    /// which the UI then reports as "offline".
    let mood1To5: Int
    let source: String
    let baseline: Baseline

    struct Baseline: Decodable, Equatable {
        let heartRateBpm: Double
        let spo2Pct: Double
        let tempC: Double
        let respRateBpm: Double
        let sleepHLastNight: Double
        let mood1To5: Int   // capital T — see the note above
    }
}

/// One point of the stored heart-rate history (GET /history), for the chart.
struct HistoryPoint: Decodable {
    let ts: Date
    let heartRateBpm: Double?
}

/// One night from the on-board lighting log (GET /circadian).
struct SleepNight: Decodable {
    let nightOf: String
    let sleepH: Double
}

/// Talks to the backend at localhost. The watchOS Simulator reaches the Mac's
/// own localhost directly, which is why the whole demo runs on one machine.
actor APIClient {

    static let baseURL = URL(string: "http://localhost:8000")!

    private let astronautID: String
    private let session: URLSession

    private let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        e.dateEncodingStrategy = .iso8601
        return e
    }()

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    init(astronautID: String = "a1") {
        self.astronautID = astronautID
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 5
        config.waitsForConnectivity = false
        self.session = URLSession(configuration: config)
    }

    private struct IngestBody: Encodable {
        let timestamp: Date
        let heartRateBpm: Double
        let hrvSdnnMs: Double   // PROVISIONAL: the backend ignores these two
        let activeMin: Double   // until it stores HRV and activity
        let source: String
    }

    /// POST /astronauts/{id}/ingest
    func ingest(_ sample: WatchSample) async throws {
        let url = Self.baseURL
            .appendingPathComponent("astronauts")
            .appendingPathComponent(astronautID)
            .appendingPathComponent("ingest")

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(
            IngestBody(timestamp: Date(), heartRateBpm: sample.heartRateBpm, hrvSdnnMs: sample.hrvSdnnMs,
                       activeMin: sample.activeMin, source: "simulated")
        )

        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }

    /// GET /astronauts/{id}/vitals
    func vitals() async throws -> VitalsSnapshot {
        let url = Self.baseURL
            .appendingPathComponent("astronauts")
            .appendingPathComponent(astronautID)
            .appendingPathComponent("vitals")

        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return try decoder.decode(VitalsSnapshot.self, from: data)
    }

    /// GET /astronauts/{id}/alerts
    ///
    /// The watch polls rather than holding an SSE connection: one request every
    /// 3 s alongside the ingest is far less code than streaming on watchOS, and
    /// the latency is irrelevant next to the light-time delay we're modelling.
    func alerts() async throws -> [VitalsAlert] {
        let url = Self.baseURL
            .appendingPathComponent("astronauts")
            .appendingPathComponent(astronautID)
            .appendingPathComponent("alerts")

        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return try decoder.decode([VitalsAlert].self, from: data)
    }

    /// GET /astronauts/{id}/history?hours=1 — the stored readings for the chart.
    func lastHour() async throws -> [HistoryPoint] {
        var url = Self.baseURL
            .appendingPathComponent("astronauts")
            .appendingPathComponent(astronautID)
            .appendingPathComponent("history")
        url.append(queryItems: [URLQueryItem(name: "hours", value: "1")])
        return try await get(url)
    }

    /// GET /astronauts/{id}/circadian?view=crew — only the nights are used here.
    func sleepNights() async throws -> [SleepNight] {
        struct Circadian: Decodable { let nights: [SleepNight] }
        var url = Self.baseURL
            .appendingPathComponent("astronauts")
            .appendingPathComponent(astronautID)
            .appendingPathComponent("circadian")
        url.append(queryItems: [URLQueryItem(name: "view", value: "crew")])
        let c: Circadian = try await get(url)
        return c.nights
    }

    private func get<T: Decodable>(_ url: URL) async throws -> T {
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return try decoder.decode(T.self, from: data)
    }
}
