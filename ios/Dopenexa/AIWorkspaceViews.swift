import SwiftUI

struct AIResultsView: View {
    @EnvironmentObject private var store: AppStore
    let query: String
    @State private var matches:[Professional] = []
    @State private var intent:AIIntent?
    @State private var error:String?
    var body: some View {
        ScrollView { VStack(alignment:.leading,spacing:18) {
            HStack { Image(systemName:"sparkles").foregroundStyle(DopenexaColor.brand); Text("Dopenexa AI").font(DopenexaFont.label()); Spacer(); if let intent { DopenexaPill(text:intent.category?.capitalized ?? "Broad match") } }
            Text(query).font(DopenexaFont.title(23))
            if let intent { Text("I interpreted this as a \(intent.category?.replacingOccurrences(of:"-", with:" ") ?? "general") request.").font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted) }
            ForEach(matches) { p in NavigationLink { ProfessionalView(professional:p) } label: { AIProfessionalCard(professional:p) }.buttonStyle(.plain) }
            if let error { Text(error).foregroundStyle(.red).font(.caption) }
        }.padding(20) }
        .background(DopenexaColor.surface.ignoresSafeArea())
        .navigationTitle("Matches")
        .task { do { let r=try await APIClient.shared.aiMatch(text:query); matches=r.matches; intent=r.intent } catch { self.error = error.localizedDescription } }
    }
}
private struct AIProfessionalCard:View { let professional:Professional; var body:some View { VStack(alignment:.leading,spacing:12){HStack{Image(systemName:professional.imageName).font(.title2).foregroundStyle(DopenexaColor.brandDark).frame(width:52,height:52).background(DopenexaColor.brandSoft).clipShape(Circle());VStack(alignment:.leading){HStack{Text(professional.name).font(DopenexaFont.body().weight(.bold));if professional.verified{Image(systemName:"checkmark.seal.fill").foregroundStyle(DopenexaColor.success)}};Text(professional.headline ?? "Professional").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted)};Spacer();Text("\(professional.match)%").font(DopenexaFont.title(18)).foregroundStyle(DopenexaColor.brand)};Text(professional.matchReason ?? "Relevant skills and trust signals matched to your request.").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted);HStack{DopenexaPill(text:"★ \(String(format: "%.1f", professional.rating))");DopenexaPill(text:"\(professional.completedJobs) jobs")}}.dopenexaCard(radius:20)} }

struct ProjectView: View {
    let booking: Booking
    @State private var project: Project?
    @State private var draftTitle=""
    @State private var draftBody=""
    @State private var error:String?
    @State private var adding=false
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:18) {
                    header
                    if let project { timeline(project) }
                    ProjectAttachmentsView(booking: booking)
                    Button { adding=true } label: { Label("Add project update",systemImage:"plus.circle.fill") }.buttonStyle(DopenexaPrimaryButtonStyle())
                    if let error { Text(error).foregroundStyle(.red).font(.caption) }
                }.padding(20)
            }
            .background(DopenexaColor.surface.ignoresSafeArea())
            .navigationTitle("Project")
            .sheet(isPresented:$adding) {
                NavigationStack { Form { TextField("Title",text:$draftTitle); TextField("What happened?",text:$draftBody,axis:.vertical) }
                    .navigationTitle("New update")
                    .toolbar { ToolbarItem(placement:.confirmationAction) { Button("Post") { Task { await addUpdate() } } } }
                }
            }
            .task { await load() }
        }
    }
    private var header: some View { VStack(alignment:.leading,spacing:8) { DopenexaPill(text:booking.status.capitalized,icon:"circle.fill"); Text("Project \(booking.id.prefix(8))").font(DopenexaFont.display(28)); Text(booking.startsAt.formatted(date:.complete,time:.shortened)).font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted) } }
    private func timeline(_ p:Project)->some View { VStack(alignment:.leading,spacing:12) { ForEach(p.updates) { u in HStack(alignment:.top,spacing:12) { Image(systemName:"checkmark.circle.fill").foregroundStyle(DopenexaColor.success); VStack(alignment:.leading,spacing:4) { Text(u.title).font(DopenexaFont.body().weight(.semibold)); Text(u.body).font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted); Text(u.createdAt.formatted(date:.abbreviated,time:.shortened)).font(.caption).foregroundStyle(DopenexaColor.muted) } }.dopenexaCard(radius:18) } } }
    private func load() async { project=try? await APIClient.shared.project(bookingID:booking.id) }
    private func addUpdate() async { do { _=try await APIClient.shared.addProjectUpdate(bookingID:booking.id,title:draftTitle,body:draftBody); draftTitle=""; draftBody=""; adding=false; await load() } catch { self.error = error.localizedDescription } }
}

struct NotificationsView: View {
    @State private var items:[NotificationItem] = []
    var body: some View {
        NavigationStack {
            List(items) { n in
                VStack(alignment:.leading, spacing:5) {
                    HStack { Text(n.title).font(.headline); Spacer(); if !n.isRead { Circle().fill(DopenexaColor.brand).frame(width:7,height:7) } }
                    Text(n.body).font(.subheadline)
                    Text(n.createdAt.formatted(date:.abbreviated,time:.shortened)).font(.caption).foregroundStyle(.secondary)
                }
                .contentShape(Rectangle())
                .onTapGesture { Task { try? await APIClient.shared.markNotificationRead(id:n.id); await load() } }
            }
            .navigationTitle("Notifications")
            .task { await load() }
        }
    }
    private func load() async { items = (try? await APIClient.shared.notifications()) ?? [] }
}
