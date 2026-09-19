import Foundation
import LocalAuthentication

enum DopenexaAuthDestination: Equatable {
    case splash
    case introduction
    case roleSelection
    case authentication
    case app
    case professionalOnboarding
    case faceID
}

final class BiometricAuthService {
    static let shared = BiometricAuthService()
    private init() {}

    var isAvailable: Bool {
        let context = LAContext()
        var error: NSError?
        return context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error)
    }

    func authenticate(reason: String) async -> Bool {
        let context = LAContext()
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else { return false }
        return await withCheckedContinuation { continuation in
            context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: reason) { success, _ in
                continuation.resume(returning: success)
            }
        }
    }
}

struct AuthenticationService {
    func login(email: String, password: String) async throws -> TokenResponse {
        try await APIClient.shared.login(email: email, password: password)
    }

    func register(email: String, password: String, name: String, role: String) async throws -> TokenResponse {
        try await APIClient.shared.register(email: email, password: password, name: name, role: role)
    }
}
