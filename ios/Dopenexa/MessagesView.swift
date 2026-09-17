import SwiftUI

struct MessagesView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        NavigationStack {
            List(store.conversations) { c in
                NavigationLink { RealtimeConversationView(conversation:c) } label: {
                    HStack(spacing:12) {
                        Image(systemName:"bubble.left.and.bubble.right.fill").foregroundStyle(DopenexaColor.brand).frame(width:42,height:42).background(DopenexaColor.brandSoft).clipShape(Circle())
                        VStack(alignment:.leading,spacing:4) { Text(c.bookingID.map { "Project \($0.prefix(8))" } ?? "Conversation").font(DopenexaFont.body().weight(.semibold)); Text("Open project chat").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted) }
                    }.padding(.vertical,4)
                }
            }.scrollContentBackground(.hidden).background(DopenexaColor.surface).navigationTitle("Messages").task { await store.loadConversations() }
        }
    }
}
