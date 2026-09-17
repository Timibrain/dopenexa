import SwiftUI
import UniformTypeIdentifiers

struct ReviewSheet: View {
    let booking: Booking
    @Environment(\.dismiss) private var dismiss
    @State private var rating=5; @State private var bodyText=""; @State private var error:String?
    var body: some View { NavigationStack { Form { Section("Your rating") { Picker("Stars",selection:$rating){ForEach(1...5,id:\.self){Text("\(String(repeating:"★",count:$0))").tag($0)}}.pickerStyle(.segmented) }; Section("Optional note"){TextField("What stood out?",text:$bodyText,axis:.vertical)}; if let error{Text(error).foregroundStyle(.red)} }.navigationTitle("Leave a review").toolbar{ToolbarItem(placement:.confirmationAction){Button("Post"){Task{await post()}}}} } }
    private func post() async { do { _=try await APIClient.shared.createReview(bookingID:booking.id,rating:rating,body:bodyText.isEmpty ? nil : bodyText); dismiss() } catch { self.error = error.localizedDescription } }
}

struct DisputeSheet: View {
    let booking: Booking; @Environment(\.dismiss) private var dismiss; @State private var reason=""; @State private var details=""; @State private var error:String?
    var body: some View { NavigationStack { Form { TextField("Reason",text:$reason); TextField("Explain what happened",text:$details,axis:.vertical); if let error{Text(error).foregroundStyle(.red)} }.navigationTitle("Open dispute").toolbar{ToolbarItem(placement:.confirmationAction){Button("Submit"){Task{await submit()}}}} } }
    private func submit() async { do { _=try await APIClient.shared.openDispute(bookingID:booking.id,reason:reason,details:details); dismiss() } catch { self.error = error.localizedDescription } }
}

struct ProjectAttachmentsView: View {
    let booking:Booking; @State private var items:[AttachmentItem]=[]; @State private var importing=false; @State private var error:String?
    var body: some View { VStack(alignment:.leading,spacing:12){ HStack{Text("Files").font(DopenexaFont.title(20));Spacer();Button{importing=true}label:{Image(systemName:"paperclip.circle.fill").font(.title2)}}; ForEach(items){item in HStack{Image(systemName:"doc.fill").foregroundStyle(DopenexaColor.brand);VStack(alignment:.leading){Text(item.filename).font(DopenexaFont.label().weight(.semibold));Text("\(item.sizeBytes/1024) KB").font(.caption).foregroundStyle(DopenexaColor.muted)};Spacer()}.dopenexaCard(radius:16)}; if items.isEmpty{Text("Share briefs, references and deliverables here.").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted)}; if let error{Text(error).font(.caption).foregroundStyle(.red)} }.fileImporter(isPresented:$importing,allowedContentTypes:[.pdf,.image,.plainText],allowsMultipleSelection:false){result in Task{await handle(result)}}.task{await load()} }
    private func load()async{items=(try? await APIClient.shared.attachments(bookingID:booking.id)) ?? []}
    private func handle(_ result:Result<[URL],Error>) async { do { guard let url=try result.get().first else{return}; let accessed=url.startAccessingSecurityScopedResource(); defer{if accessed{url.stopAccessingSecurityScopedResource()}}; let data=try Data(contentsOf:url); let mime=url.pathExtension.lowercased()=="pdf" ? "application/pdf" : (url.pathExtension.lowercased()=="txt" ? "text/plain" : "image/jpeg"); _=try await APIClient.shared.uploadAttachment(bookingID:booking.id,data:data,filename:url.lastPathComponent,mimeType:mime); await load() } catch {self.error = error.localizedDescription} }
}
