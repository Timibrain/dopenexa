import SwiftUI

struct RealtimeConversationView: View {
    let conversation: Conversation
    @State private var messages:[APIMessage] = []
    @State private var draft = ""
    @State private var socket: RealtimeSocket?
    @State private var error:String?
    var body: some View {
        VStack(spacing:0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing:10) {
                        ForEach(messages) { message in
                            MessageBubble(message:message).id(message.id)
                        }
                    }.padding(16)
                }.onChange(of:messages.count) { _,_ in if let id=messages.last?.id { withAnimation { proxy.scrollTo(id,anchor:.bottom) } } }
            }
            HStack(spacing:10) {
                TextField("Message…",text:$draft,axis:.vertical).lineLimit(1...4).padding(11).background(DopenexaColor.surface).clipShape(RoundedRectangle(cornerRadius:16))
                Button { send() } label: { Image(systemName:"arrow.up").foregroundStyle(.white).frame(width:42,height:42).background(DopenexaColor.brand).clipShape(Circle()) }.disabled(draft.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty)
            }.padding(12).background(.white).overlay(Rectangle().frame(height:1).foregroundStyle(DopenexaColor.line),alignment:.top)
        }.background(DopenexaColor.surface.ignoresSafeArea()).navigationTitle("Project chat").navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .onDisappear { socket?.disconnect() }
        .alert("Something went wrong",isPresented:Binding(get:{error != nil},set:{_ in error=nil})){Button("OK",role:.cancel){}} message:{Text(error ?? "")}
    }
    private func load() async {
        do { messages=try await APIClient.shared.messages(conversationID:conversation.id) }
        catch { self.error = error.localizedDescription }
        let s=RealtimeSocket { message in if !messages.contains(where:{$0.id==message.id}) { messages.append(message) } }
        socket=s; await s.connect(conversationID:conversation.id)
    }
    private func send() { let text=draft.trimmingCharacters(in:.whitespacesAndNewlines); guard !text.isEmpty else{return}; socket?.send(body:text); draft="" }
}
private struct MessageBubble:View { let message:APIMessage; var body:some View { let mine=message.senderID == UserDefaults.standard.string(forKey:"dopenexa_user_id"); return HStack { if mine { Spacer() }; VStack(alignment:mine ? .trailing:.leading,spacing:4){Text(message.body).font(DopenexaFont.body()).foregroundStyle(mine ? .white:DopenexaColor.ink).padding(.horizontal,14).padding(.vertical,10).background(mine ? DopenexaColor.brand:.white).clipShape(RoundedRectangle(cornerRadius:17));Text(message.createdAt.formatted(date:.omitted,time:.shortened)).font(.caption2).foregroundStyle(DopenexaColor.muted)}; if !mine { Spacer() } } } }
