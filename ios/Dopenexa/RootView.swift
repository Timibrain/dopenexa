import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        Group {
            switch store.destination {
            case .splash: SplashView()
            case .introduction: MarketplaceIntroductionView()
            case .roleSelection: RoleSelectionView()
            case .authentication: AuthenticationView(role: store.selectedRole)
            case .faceID: FaceIDWelcomeView()
            case .professionalOnboarding: ProfessionalOnboardingView(profile: store.professionalProfile).environmentObject(store)
            case .app: MainTabs()
            }
        }
        .task { await store.startEntryFlow() }
        .alert("Use Face ID next time?", isPresented: $store.faceIDPrompt) {
            Button("Enable Face ID") { Task { await store.enableFaceID() } }
            Button("Not now", role: .cancel) { store.skipFaceID() }
        } message: {
            Text("Your session is already protected in Keychain. Face ID adds a quick unlock when you return to Dopenexa.")
        }
    }
}

struct MainTabs: View {
    @EnvironmentObject var store: AppStore
    var body: some View {
        TabView {
            if store.currentUser?.role == "professional" {
                ProfessionalDashboardView().tabItem { Label("Workspace", systemImage: "briefcase.fill") }
            } else {
                CustomerHomeView().tabItem { Label("Home", systemImage: "house.fill") }
                DiscoveryView().tabItem { Label("Discover", systemImage: "sparkle.magnifyingglass") }
            }
            BookingsView().tabItem { Label("Bookings", systemImage: "calendar") }
            MessagesView().tabItem { Label("Messages", systemImage: "bubble.left.and.bubble.right") }
            ProfileView().tabItem { Label("Profile", systemImage: "person.crop.circle") }
        }.tint(DopenexaColor.brand)
    }
}
