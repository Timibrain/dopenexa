import SwiftUI

struct RecommendationStrip: View {
    @State private var items:[Recommendation] = []
    var body: some View {
        VStack(alignment:.leading, spacing:12) {
            HStack {
                VStack(alignment:.leading, spacing:3) { Text("Picked for you").font(DopenexaFont.title(20)); Text("Based on your activity and trusted signals").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted) }
                Spacer(); Image(systemName:"sparkles").foregroundStyle(DopenexaColor.brand)
            }
            if items.isEmpty { ProgressView().frame(maxWidth:.infinity).padding(.vertical,16) }
            else {
                ScrollView(.horizontal, showsIndicators:false) {
                    HStack(spacing:12) {
                        ForEach(items) { item in
                            NavigationLink { ProfessionalView(professional: Professional(id:item.id,name:item.name,headline:item.headline,bio:item.bio,rating:item.rating,reviews:item.reviews,verified:item.verified,completedJobs:item.completedJobs,match:0,matchReason:item.reason)) } label: {
                                VStack(alignment:.leading, spacing:10) {
                                    Image(systemName:"person.crop.circle.fill").font(.system(size:34)).foregroundStyle(DopenexaColor.brandDark).frame(width:52,height:52).background(DopenexaColor.brandSoft).clipShape(Circle())
                                    Text(item.name).font(DopenexaFont.body().weight(.bold)).lineLimit(1)
                                    Text(item.headline ?? "Professional").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted).lineLimit(2)
                                    HStack { Text("★ \(item.rating,specifier:"%.1f")"); if item.verified { Image(systemName:"checkmark.seal.fill").foregroundStyle(DopenexaColor.success) } }.font(DopenexaFont.label())
                                    Text(item.reason).font(DopenexaFont.label(10)).foregroundStyle(DopenexaColor.muted).lineLimit(2)
                                }.frame(width:185, alignment:.leading).dopenexaCard(radius:20)
                            }.buttonStyle(.plain)
                        }
                    }
                }
            }
        }.task { items = (try? await APIClient.shared.recommendations()) ?? [] }
    }
}
