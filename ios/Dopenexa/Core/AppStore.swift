import Foundation
import SwiftUI
import AuthenticationServices

@MainActor final class AppStore: ObservableObject {
    @Published var professionals: [Professional] = []
    @Published var bookings: [Booking] = []
    @Published var conversations: [Conversation] = []
    @Published var currentUser: CurrentUser?
    @Published var professionalProfile: ProfessionalProfile?
    @Published var isLoading = false
    @Published var error: String?
    @Published var destination: DopenexaAuthDestination = .splash
    @Published var selectedRole: String?
    @Published var faceIDPrompt = false
    @Published var faceIDEnabled = UserDefaults.standard.bool(forKey: "dopenexa_face_id_enabled")
    @Published var faceIDError: String?

    private let authentication = AuthenticationService()
    private var hasStarted = false
    private var appleRawNonce: String?
    @Published private(set) var appleAuthorizationPending = false

    var isAuthenticated: Bool { currentUser != nil }

    init() { Task { await startEntryFlow() } }

    func startEntryFlow() async {
        guard !hasStarted else { return }
        hasStarted = true
        try? await Task.sleep(for: .milliseconds(850))
        let hasSession = DopenexaKeychain.get("access_token") != nil || DopenexaKeychain.get("refresh_token") != nil
        if hasSession {
            if faceIDEnabled { destination = .faceID } else { await restoreSession() }
        } else {
            destination = UserDefaults.standard.bool(forKey: "dopenexa_intro_seen") ? .authentication : .introduction
        }
    }

    func completeIntroduction() { UserDefaults.standard.set(true, forKey: "dopenexa_intro_seen"); destination = .roleSelection }
    func chooseRole(_ role: String) { selectedRole = role; destination = .authentication }
    func showSignIn() { selectedRole = nil; destination = .authentication }

    func login(email: String, password: String) async { await authenticate { try await authentication.login(email: email, password: password) } }
    func register(email: String, password: String, name: String, role: String = "customer") async { await authenticate { try await authentication.register(email: email, password: password, name: name, role: role) } }

    func beginAppleAuthorization() -> String? {
        guard !appleAuthorizationPending, !isLoading else { return nil }
        error = nil
        do {
            let rawNonce = try AppleNonce.generate()
            appleRawNonce = rawNonce
            appleAuthorizationPending = true
            return AppleNonce.hash(rawNonce)
        } catch {
            self.error = error.localizedDescription
            appleRawNonce = nil
            return nil
        }
    }

    func completeAppleAuthorization(_ result: Result<ASAuthorization, Error>, role: String?) async {
        guard appleAuthorizationPending else { return }
        appleAuthorizationPending = false
        let rawNonce = appleRawNonce
        appleRawNonce = nil
        guard let rawNonce else { error = "Apple sign-in expired. Please try again."; return }
        switch result {
        case .failure(let failure):
            if let authorizationError = failure as? ASAuthorizationError,
               authorizationError.code == .canceled {
                error = nil
            } else {
                error = "Apple sign-in could not be completed. Please try again or use email."
            }
        case .success(let authorization):
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = credential.identityToken,
                  let identityToken = String(data: tokenData, encoding: .utf8),
                  !identityToken.isEmpty else {
                error = "Apple did not return a valid identity token. Please try again."
                return
            }
            await authenticate { try await authentication.signInWithApple(identityToken: identityToken, rawNonce: rawNonce, role: role) }
        }
    }

    private func authenticate(_ call: () async throws -> TokenResponse) async {
        isLoading = true; error = nil
        do {
            let tokens = try await call()
            await APIClient.shared.setTokens(access: tokens.accessToken, refresh: tokens.refreshToken)
            try await refreshUser()
            await routeAuthenticatedUser()
            if BiometricAuthService.shared.isAvailable && !faceIDEnabled { faceIDPrompt = true }
        } catch { self.error = error.localizedDescription }
        isLoading = false
    }

    func restoreSession() async {
        isLoading = true; error = nil
        do { _ = try await APIClient.shared.refreshSession(); try await refreshUser(); await routeAuthenticatedUser() }
        catch { clearLocalSession(); destination = .authentication; self.error = "Your session expired. Please sign in again." }
        isLoading = false
    }

    func unlockWithFaceID() async {
        faceIDError = nil
        guard BiometricAuthService.shared.isAvailable else { faceIDError = "Face ID is unavailable on this device."; return }
        guard await BiometricAuthService.shared.authenticate(reason: "Unlock your secure Dopenexa session") else { faceIDError = "Face ID did not match. You can try again or use another account."; return }
        await restoreSession()
    }

    func enableFaceID() async {
        guard await BiometricAuthService.shared.authenticate(reason: "Enable Face ID for faster Dopenexa sign in") else { faceIDPrompt = false; return }
        faceIDEnabled = true; UserDefaults.standard.set(true, forKey: "dopenexa_face_id_enabled"); faceIDPrompt = false
    }
    func skipFaceID() { faceIDPrompt = false }

    func useAnotherAccount() { clearLocalSession(); destination = .authentication }

    func refreshUser() async throws {
        do { currentUser = try await APIClient.shared.me(); if let currentUser { UserDefaults.standard.set(currentUser.id, forKey: "dopenexa_user_id") } }
        catch { currentUser = nil; throw error }
    }

    func routeAuthenticatedUser() async {
        guard let currentUser else { destination = .authentication; return }
        if currentUser.role == "professional" {
            do { professionalProfile = try await APIClient.shared.professionalMe(); destination = professionalProfile?.onboardingComplete == true ? .app : .professionalOnboarding }
            catch { professionalProfile = nil; destination = .professionalOnboarding }
        } else { destination = .app }
    }

    func completeProfessionalOnboarding() async {
        do { professionalProfile = try await APIClient.shared.professionalMe(); destination = .app }
        catch { self.error = error.localizedDescription }
    }

    func logout() {
        let refresh = DopenexaKeychain.get("refresh_token")
        Task { await APIClient.shared.logout(refresh: refresh) }
        clearLocalSession(); destination = .authentication
    }

    private func clearLocalSession() {
        DopenexaKeychain.remove("access_token"); DopenexaKeychain.remove("refresh_token")
        currentUser = nil; professionalProfile = nil; professionals = []; bookings = []; conversations = []
        faceIDEnabled = false; UserDefaults.standard.set(false, forKey: "dopenexa_face_id_enabled")
    }

    func search(_ q: String, verified: Bool = false, minRating: Double = 0, maxPriceNGN: Int? = nil, serviceType: String? = nil) async { isLoading = true; do { professionals = try await APIClient.shared.searchProfessionals(query: q, verified: verified, minRating: minRating, maxPriceNGN: maxPriceNGN, serviceType: serviceType) } catch { self.error = error.localizedDescription }; isLoading = false }
    func loadBookings() async { do { bookings = try await APIClient.shared.bookings() } catch { self.error = error.localizedDescription } }
    func loadConversations() async { do { conversations = try await APIClient.shared.conversations() } catch { self.error = error.localizedDescription } }
    func book(professionalID: String, serviceID: String, date: Date, endsAt: Date?) async -> BookingCreated? { do { let b = try await APIClient.shared.createBooking(professionalID: professionalID, serviceID: serviceID, startsAt: date, endsAt: endsAt, note: nil); await loadBookings(); return b } catch { self.error = error.localizedDescription; return nil } }
    func pay(bookingID: String) async -> PaymentSession? { do { return try await APIClient.shared.createPayment(bookingID: bookingID) } catch { self.error = error.localizedDescription; return nil } }
}
