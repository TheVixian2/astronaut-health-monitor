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
        let source: String
    }

    /// POST /astronauts/{id}/ingest
    func ingest(heartRate: Double) async throws {
        let url = Self.baseURL
            .appendingPathComponent("astronauts")
            .appendingPathComponent(astronautID)
            .appendingPathComponent("ingest")

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(
            IngestBody(timestamp: Date(), heartRateBpm: heartRate, source: "simulated")
        )

        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
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
}
