import Foundation

final class RealtimeSocket: NSObject, URLSessionWebSocketDelegate {
    private var task: URLSessionWebSocketTask?
    private let session: URLSession
    private let onMessage: (APIMessage) -> Void
    private let decoder = JSONDecoder.dopenexa

    init(onMessage: @escaping (APIMessage) -> Void) {
        self.onMessage = onMessage
        self.session = URLSession(configuration: .default)
        super.init()
    }

    func connect(conversationID: String) async {
        guard let token = await APIClient.shared.currentAccessToken() else { return }
        guard var components = URLComponents(string: UserDefaults.standard.string(forKey: "dopenexa_api_url") ?? "http://localhost:8000") else { return }
        components.scheme = components.scheme == "https" ? "wss" : "ws"
        components.path = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/realtime/conversations/\(conversationID)"
        guard let url = components.url else { return }
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        task = session.webSocketTask(with: request)
        task?.resume()
        receiveLoop()
    }

    func send(body: String) {
        task?.send(.string(jsonPayload(body))) { _ in }
    }

    func disconnect() { task?.cancel(with: .goingAway, reason: nil); task = nil }

    private func receiveLoop() {
        task?.receive { [weak self] result in
            guard let self else { return }
            if case .success(.string(let text)) = result,
               let data = text.data(using: .utf8),
               let message = try? self.decoder.decode(APIMessage.self, from: data) {
                Task { @MainActor in self.onMessage(message) }
            }
            self.receiveLoop()
        }
    }

    private func jsonPayload(_ value: String) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: ["body": value]) else { return "{}" }
        return String(data: data, encoding: .utf8) ?? "{}"
    }
}
