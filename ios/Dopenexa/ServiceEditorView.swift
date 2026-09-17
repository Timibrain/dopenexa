import SwiftUI

struct ServiceEditorView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var description = ""
    @State private var type = "appointment"
    @State private var price = ""
    @State private var duration = "60"
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Service") {
                    TextField("Name", text: $name)
                    TextField("Description", text: $description, axis: .vertical)
                    Picker("Type", selection: $type) {
                        ForEach(["appointment","hourly","fixed","recurring","project"], id: \.self) { Text($0.capitalized).tag($0) }
                    }
                }
                Section("Pricing") {
                    TextField("Price (NGN)", text: $price).keyboardType(.numberPad)
                    TextField("Duration (minutes)", text: $duration).keyboardType(.numberPad)
                }
                Section {
                    Button(saving ? "Saving…" : "Create service") { Task { await save() } }
                        .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || Int(price) == nil)
                }
            }
            .navigationTitle("New service")
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } } }
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        do {
            _ = try await APIClient.shared.createProfessionalService(name: name, description: description, serviceType: type, priceNGN: Int(price) ?? 0, durationMinutes: Int(duration))
            dismiss()
        } catch {}
    }
}
