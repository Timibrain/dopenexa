import SwiftUI

struct ProfessionalView: View {
    let professional: Professional
    @EnvironmentObject private var store: AppStore
    @State private var detail: ProfessionalDetail?
    @State private var selected: Service?
    @State private var saved = false
    @State private var saveBusy = false
    @State private var reviews:[ReviewItem] = []
    var body: some View {
        ScrollView {
            VStack(alignment:.leading,spacing:20) {
                ZStack(alignment:.bottomLeading) {
                    RoundedRectangle(cornerRadius:28).fill(LinearGradient(colors:[DopenexaColor.brandSoft,DopenexaColor.lavender],startPoint:.topLeading,endPoint:.bottomTrailing)).frame(height:210)
                    Image(systemName:"person.crop.circle.fill").font(.system(size:78)).foregroundStyle(DopenexaColor.brandDark)
                    DopenexaPill(text:professional.match>0 ? "\(professional.match)% AI match":"Smart match",icon:"sparkles").padding(16)
                }
                HStack(alignment:.top) {
                    VStack(alignment:.leading,spacing:6) { HStack{Text(detail?.name ?? professional.name).font(DopenexaFont.display(29));if professional.verified{Image(systemName:"checkmark.seal.fill").foregroundStyle(DopenexaColor.success)}};Text(detail?.headline ?? professional.headline ?? "Professional").font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted) }
                    Spacer()
                    if store.currentUser?.role == "customer" { Button { Task { await toggleSaved() } } label: { Image(systemName:saved ? "bookmark.fill" : "bookmark").font(.title3).foregroundStyle(DopenexaColor.brand).frame(width:44,height:44).background(.white).clipShape(Circle()).overlay(Circle().stroke(DopenexaColor.line)) }.disabled(saveBusy) }
                }
                HStack{Text("★ \(professional.rating,specifier:"%.1f")");Text("•");Text("\(professional.reviews) reviews");Text("•");Text(professional.location)}.font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted)
                Text(detail?.bio ?? professional.bio ?? "").font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted)
                HStack{Metric(value:"\(professional.completedJobs)",label:"Jobs");Metric(value:"\(professional.reviews)",label:"Reviews");Metric(value:professional.verified ? "Verified":"Pending",label:"Trust")}
                Text("Services").font(DopenexaFont.title())
                if let detail { ForEach(detail.services){service in ServiceCard(service:service){selected=service}} } else { ProgressView() }
                if !reviews.isEmpty {
                    HStack { Text("Recent reviews").font(DopenexaFont.title()); Spacer(); Text("\(reviews.count)").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted) }
                    ForEach(reviews.prefix(3)) { review in ReviewCard(review:review) }
                }
            }.padding(20)
        }.background(DopenexaColor.surface.ignoresSafeArea()).navigationTitle("").navigationBarTitleDisplayMode(.inline)
        .sheet(item:$selected){service in BookingFlow(professional:professional,service:service)}
        .task { do { detail=try await APIClient.shared.professional(id:professional.id); if store.currentUser?.role == "customer" { saved=(try? await APIClient.shared.savedProfessionals().contains(where:{$0.id==professional.id})) ?? false }; reviews=(try? await APIClient.shared.reviews(professionalID: professional.id)) ?? [] } catch { store.error=error.localizedDescription } }
    }
    private func toggleSaved() async { saveBusy=true; defer{saveBusy=false}; do { if saved { try await APIClient.shared.unsaveProfessional(id:professional.id) } else { try await APIClient.shared.saveProfessional(id:professional.id) }; saved.toggle() } catch { store.error=error.localizedDescription } }
}
private struct Metric:View{let value:String;let label:String;var body:some View{VStack(spacing:4){Text(value).font(DopenexaFont.title(17));Text(label).font(DopenexaFont.label(10)).foregroundStyle(DopenexaColor.muted)}.frame(maxWidth:.infinity).padding(.vertical,12).background(.white).clipShape(RoundedRectangle(cornerRadius:16))}}
private struct ServiceCard:View{let service:Service;let action:()->Void;var body:some View{VStack(alignment:.leading,spacing:10){HStack{Text(service.name).font(DopenexaFont.body().weight(.bold));Spacer();Text("₦\(service.priceNGN.formatted())").font(DopenexaFont.title(17)).foregroundStyle(DopenexaColor.brand)};Text(service.description ?? "").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted);HStack{DopenexaPill(text:service.serviceType.capitalized);if let d=service.durationMinutes{DopenexaPill(text:"\(d) min")};Spacer();Button("Book",action:action).buttonStyle(.borderedProminent).tint(DopenexaColor.brand)}}.dopenexaCard()}}

private struct ReviewCard: View { let review:ReviewItem; var body:some View { VStack(alignment:.leading,spacing:7){ HStack{Text(String(repeating:"★",count:review.rating)).foregroundStyle(DopenexaColor.warning);Spacer();Text(review.createdAt.formatted(date:.abbreviated,time:.omitted)).font(.caption).foregroundStyle(DopenexaColor.muted)}; if let body=review.body,!body.isEmpty{Text(body).font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted)} }.dopenexaCard(radius:18) } }
