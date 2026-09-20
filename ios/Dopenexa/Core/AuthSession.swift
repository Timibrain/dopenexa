import Foundation
import LocalAuthentication
import CryptoKit
import Security

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

    func signInWithApple(identityToken: String, rawNonce: String, role: String?) async throws -> TokenResponse {
        try await APIClient.shared.signInWithApple(identityToken: identityToken, nonce: rawNonce, role: role)
    }
}

enum AppleNonce {
    static func generate() throws -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
            throw APIError.server("Unable to create a secure Apple sign-in request")
        }
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    static func hash(_ rawNonce: String) -> String {
        SHA256.hash(data: Data(rawNonce.utf8)).map { String(format: "%02x", $0) }.joined()
    }
}
