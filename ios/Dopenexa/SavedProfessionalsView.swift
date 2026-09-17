import SwiftUI

struct SavedProfessionalsView: View {
    @State private var items: [SavedProfessional] = []
    @State private var loading = true
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Saved professionals").font(DopenexaFont.display(30))
                Text("Keep the people you trust close for your next project.").font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted)
                if loading { ProgressView().frame(maxWidth: .infinity).padding(40) }
                else if items.isEmpty { empty }
                else { ForEach(items) { item in NavigationLink { ProfessionalView(professional: Professional(id:item.id,name:item.name,headline:item.headline,bio:item.bio,rating:item.rating,reviews:item.reviews,verified:item.verified,completedJobs:item.completedJobs)) } label: { savedCard(item) }.buttonStyle(.plain) } }
            }.padding(20)
        }.background(DopenexaColor.surface.ignoresSafeArea()).navigationTitle("Saved")
        .task { items = (try? await APIClient.shared.savedProfessionals()) ?? []; loading = false }
    }
    private var empty: some View { VStack(spacing: 10) { Image(systemName:"bookmark").font(.system(size:40)).foregroundStyle(DopenexaColor.brand); Text("Nothing saved yet").font(DopenexaFont.title()); Text("Tap the bookmark on a professional profile to save them here.").multilineTextAlignment(.center).font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted) }.frame(maxWidth:.infinity).padding(36).dopenexaCard() }
    private func savedCard(_ p:SavedProfessional)->some View { HStack(spacing:14) { Image(systemName:"person.crop.circle.fill").font(.title).foregroundStyle(DopenexaColor.brandDark).frame(width:52,height:52).background(DopenexaColor.brandSoft).clipShape(Circle()); VStack(alignment:.leading,spacing:4){ HStack{Text(p.name).font(DopenexaFont.body().weight(.bold)); if p.verified { Image(systemName:"checkmark.seal.fill").foregroundStyle(DopenexaColor.success) } }; Text(p.headline ?? "Professional").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted); Text("★ \(p.rating,specifier:"%.1f")  ·  \(p.completedJobs) jobs").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted) }; Spacer(); Image(systemName:"chevron.right").foregroundStyle(DopenexaColor.muted) }.dopenexaCard(radius:18) }
}
