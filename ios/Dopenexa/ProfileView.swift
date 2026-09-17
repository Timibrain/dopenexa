import SwiftUI

struct ProfileView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    VStack(spacing: 10) {
                        Circle().fill(DopenexaColor.brandSoft).frame(width: 86, height: 86)
                            .overlay(Image(systemName: store.currentUser?.role == "professional" ? "briefcase.fill" : "person.fill").font(.title).foregroundStyle(DopenexaColor.brandDark))
                        Text(store.currentUser?.displayName ?? "Your Dopenexa profile").font(DopenexaFont.title())
                        Text(store.currentUser?.role.capitalized ?? "Account").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted)
                    }.padding(.top, 20)
                    if store.currentUser?.role == "professional" {
                        NavigationLink { ProfessionalAvailabilityView() } label: { ProfileRow(icon: "clock", title: "Availability") }
                        NavigationLink { ProfessionalOnboardingView(profile: nil).environmentObject(store) } label: { ProfileRow(icon: "person.text.rectangle", title: "Professional profile") }
                        NavigationLink { ProfessionalTrustView() } label: { ProfileRow(icon: "checkmark.seal", title: "Trust & verification") }
                        NavigationLink { ProfessionalEarningsView() } label: { ProfileRow(icon: "nairasign.circle", title: "Earnings & payouts") }
                    }
                    if store.currentUser?.role != "professional" {
                        NavigationLink { SavedProfessionalsView() } label: { ProfileRow(icon: "bookmark", title: "Saved professionals") }
                    }
                    NavigationLink { NotificationsView() } label: { ProfileRow(icon: "bell", title: "Notifications") }
                    ProfileRow(icon: "lock", title: "Security")
                    ProfileRow(icon: "questionmark.circle", title: "Help & support")
                    Button("Sign out", role: .destructive) { store.logout() }.buttonStyle(.bordered).padding(.top, 8)
                }.padding(20)
            }
            .background(DopenexaColor.surface.ignoresSafeArea())
            .navigationTitle("Profile")
        }
    }
}
private struct ProfileRow: View {
    let icon: String; let title: String
    var body: some View {
        HStack { Image(systemName: icon).frame(width: 28).foregroundStyle(DopenexaColor.brand); Text(title).font(DopenexaFont.body()); Spacer(); Image(systemName: "chevron.right").font(.caption).foregroundStyle(DopenexaColor.muted) }
            .padding(16).background(.white).clipShape(RoundedRectangle(cornerRadius: 17)).overlay(RoundedRectangle(cornerRadius: 17).stroke(DopenexaColor.line))
    }
}
