import SwiftUI

struct ProfessionalTrustView: View {
    @State private var submissions:[VerificationSubmissionItem]=[]
    @State private var documentType="Professional credential"
    @State private var reference=""
    @State private var error:String?
    @State private var submitting=false
    var body: some View {
        Form {
            Section("Verification") {
                Text("Verified profiles can display a trust badge to customers. Submit a reference for the document or credential you want the Dopenexa team to review.")
                    .font(.subheadline).foregroundStyle(.secondary)
                TextField("Document type",text:$documentType)
                TextField("Document reference",text:$reference)
                Button(submitting ? "Submitting…" : "Submit for review") { Task { await submit() } }.disabled(submitting || reference.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty)
            }
            Section("History") {
                if submissions.isEmpty { Text("No verification submissions yet.").foregroundStyle(.secondary) }
                ForEach(submissions) { item in
                    VStack(alignment:.leading,spacing:5) {
                        HStack { Text(item.documentType).font(.headline); Spacer(); DopenexaPill(text:item.status.capitalized) }
                        if let note=item.reviewerNote, !note.isEmpty { Text(note).font(.caption).foregroundStyle(.secondary) }
                    }
                }
            }
        }.navigationTitle("Trust & verification").task { await load() }
        .alert("Something went wrong",isPresented:Binding(get:{error != nil},set:{if !$0{error=nil}})){Button("OK",role:.cancel){}} message:{Text(error ?? "")}
    }
    private func load() async { submissions=(try? await APIClient.shared.verificationHistory()) ?? [] }
    private func submit() async { submitting=true; defer{ submitting=false }; do { _=try await APIClient.shared.submitVerification(documentType:documentType,reference:reference); reference=""; await load() } catch { self.error = error.localizedDescription } }
}
