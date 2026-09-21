import SwiftUI

struct ProfessionalDashboardView: View {
    @EnvironmentObject var store: AppStore
    @State private var dashboard: ProfessionalDashboard?
    @State private var requests:[ProfessionalRequest] = []
    @State private var profile:ProfessionalProfile?
    @State private var services:[Service] = []
    @State private var showOnboarding = false
    @State private var showServiceEditor = false
    @State private var showProfile = false
    @State private var showSettings = false
    @State private var showLogoutConfirmation = false
    @State private var error:String?
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading, spacing:20) {
                    if let profile, !profile.onboardingComplete { onboardingCard }
                    if let d = dashboard { stats(d) }
                    requestsSection
                    servicesSection
                }.padding(20)
            }
            .background(DopenexaColor.surface.ignoresSafeArea())
            .navigationTitle("Workspace")
            .toolbar { ToolbarItem(placement:.topBarTrailing) { HStack {
                NavigationLink { ProfessionalEarningsView() } label:{ Image(systemName:"nairasign.circle") }
                Button { showOnboarding=true } label:{ Image(systemName:"slider.horizontal.3") }
                Menu {
                    Button("Profile") { showProfile = true }
                    Button("Settings") { showSettings = true }
                    Divider()
                    Button("Log out", role: .destructive) { showLogoutConfirmation = true }
                } label: {
                    Label("Account", systemImage: "person.circle")
                }
            } } }
            .sheet(isPresented:$showOnboarding) { ProfessionalOnboardingView(profile:profile).environmentObject(store) }
            .sheet(isPresented:$showServiceEditor) { ServiceEditorView().environmentObject(store) }
            .sheet(isPresented:$showProfile) { ProfileView().environmentObject(store) }
            .sheet(isPresented:$showSettings) { ProfessionalSettingsView().environmentObject(store) }
            .confirmationDialog("Log out of Dopenexa?", isPresented: $showLogoutConfirmation, titleVisibility: .visible) {
                Button("Log Out", role: .destructive) { store.logout() }
                Button("Cancel", role: .cancel) {}
            }
            .task { await load() }
            .alert("Something went wrong", isPresented: Binding(get:{error != nil},set:{if !$0{error=nil}})) { Button("OK",role:.cancel){} } message:{ Text(error ?? "") }
        }
    }
    private var onboardingCard: some View { VStack(alignment:.leading,spacing:10){ DopenexaPill(text:"Finish setup",icon:"sparkles"); Text("Turn your profile into a bookable business.").font(DopenexaFont.title(19)); Text("Add your positioning, service area and first service so customers can understand what you offer.").font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted); Button("Complete profile"){showOnboarding=true}.buttonStyle(DopenexaPrimaryButtonStyle()) }.dopenexaCard() }
    private func stats(_ d:ProfessionalDashboard)->some View { VStack(alignment:.leading,spacing:12){Text("Today at a glance").font(DopenexaFont.title(20)); HStack{Metric(title:"Requests",value:"\(d.pendingRequests)",icon:"tray.full");Metric(title:"Upcoming",value:"\(d.upcomingBookings)",icon:"calendar");Metric(title:"Earned",value:"₦\(d.earningsNGN.formatted())",icon:"nairasign.circle")}} }
    private var requestsSection:some View { VStack(alignment:.leading,spacing:12){HStack{Text("Booking requests").font(DopenexaFont.title(20));Spacer();Text("\(requests.count)").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted)}; if requests.isEmpty { Text("No new requests yet. Your availability and services will appear here when customers book.").font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted).dopenexaCard() } else { ForEach(requests){ r in RequestCard(request:r,action:{ action in Task { await handle(r,action:action) } }) } }} }
    private var servicesSection:some View { VStack(alignment:.leading,spacing:12){HStack{Text("Your services").font(DopenexaFont.title(20));Spacer();Button("Add"){showServiceEditor=true}.font(DopenexaFont.label())}; ForEach(services){s in HStack{VStack(alignment:.leading){Text(s.name).font(DopenexaFont.body().weight(.semibold));Text("₦\(s.priceNGN.formatted()) · \(s.serviceType.capitalized)").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted)};Spacer();Image(systemName:"chevron.right").foregroundStyle(DopenexaColor.muted)}.dopenexaCard(radius:18)} }}
    private func load() async { do { async let d=APIClient.shared.professionalDashboard(); async let r=APIClient.shared.professionalRequests(); async let p=APIClient.shared.professionalMe(); async let s=APIClient.shared.professionalServices(); dashboard=try await d; requests=try await r; profile=try await p; services=try await s } catch { self.error = error.localizedDescription } }
    private func handle(_ request: ProfessionalRequest, action: String) async {
        do {
            if action == "confirm" { _ = try await APIClient.shared.confirmBooking(id: request.id) }
            else if action == "decline" { _ = try await APIClient.shared.declineBooking(id: request.id) }
            await load()
        } catch { self.error = error.localizedDescription }
    }
}
private struct Metric:View{let title:String;let value:String;let icon:String;var body:some View{VStack(alignment:.leading,spacing:8){Image(systemName:icon).foregroundStyle(DopenexaColor.brand);Text(value).font(DopenexaFont.title(19));Text(title).font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted)}.frame(maxWidth:.infinity,alignment:.leading).dopenexaCard(radius:18)}}
private struct ProfessionalSettingsView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        NavigationStack {
            List {
                Section("Account") {
                    NavigationLink("Profile") { ProfileView().environmentObject(store) }
                    Text(store.currentUser?.displayName ?? "Dopenexa professional")
                        .foregroundStyle(DopenexaColor.muted)
                }
                Section("Security") {
                    Label("Session protected by Keychain", systemImage: "lock.shield")
                    if store.faceIDEnabled {
                        Label("Face ID enabled", systemImage: "faceid")
                    }
                }
            }
            .navigationTitle("Settings")
        }
    }
}
private struct RequestCard:View{let request:ProfessionalRequest;let action:(String)->Void;var body:some View{VStack(alignment:.leading,spacing:12){HStack{DopenexaPill(text:"New request",icon:"sparkle");Spacer();Text("₦\(request.totalNGN.formatted())").font(DopenexaFont.title(17))};Text(request.startsAt.formatted(date:.abbreviated,time:.shortened)).font(DopenexaFont.body().weight(.semibold));if let note=request.customerNote,!note.isEmpty{Text(note).font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted)};HStack{Button("Decline"){action("decline")}.buttonStyle(.bordered);Button("Accept"){action("confirm")}.buttonStyle(DopenexaPrimaryButtonStyle())}}.dopenexaCard(radius:20)}}
