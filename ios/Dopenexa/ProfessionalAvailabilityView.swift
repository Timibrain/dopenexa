import SwiftUI

struct ProfessionalAvailabilityView: View {
    @State private var windows: [AvailabilityWindow] = []
    @State private var showAdd = false
    var body: some View {
        List {
            ForEach(windows) { w in
                HStack {
                    Text(day(w.weekday)).font(DopenexaFont.body().weight(.semibold))
                    Spacer()
                    Text("\(w.startTime)–\(w.endTime)").foregroundStyle(DopenexaColor.muted)
                }
                .swipeActions {
                    Button(role: .destructive) { Task { try? await APIClient.shared.deleteAvailability(id: w.id); await load() } } label: { Label("Delete", systemImage: "trash") }
                }
            }
            .onDelete(perform: delete)
            .overlay {
                if windows.isEmpty { ContentUnavailableView("No hours yet", systemImage: "clock", description: Text("Add your working windows to make your services bookable.")) }
            }
        }
        .navigationTitle("Availability")
        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Add") { showAdd = true } } }
        .task { await load() }
        .sheet(isPresented: $showAdd) { AddAvailabilityView { Task { await load() } } }
    }
    private func load() async { windows = (try? await APIClient.shared.professionalAvailability()) ?? [] }
    private func delete(_ offsets: IndexSet) { for i in offsets { Task { try? await APIClient.shared.deleteAvailability(id: windows[i].id); await load() } } }
    private func day(_ i: Int) -> String { ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"][i] }
}

struct AddAvailabilityView: View {
    @Environment(\.dismiss) private var dismiss
    let onSave: () -> Void
    @State private var weekday = 1
    @State private var start = "09:00"
    @State private var end = "17:00"
    var body: some View {
        NavigationStack {
            Form {
                Picker("Day", selection: $weekday) { ForEach(0..<7) { Text(["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"][$0]).tag($0) } }
                TextField("Start (HH:MM)", text: $start)
                TextField("End (HH:MM)", text: $end)
                Button("Save") { Task { _ = try? await APIClient.shared.createAvailability(weekday: weekday, startTime: start, endTime: end); onSave(); dismiss() } }
            }
            .navigationTitle("Working hours")
        }
    }
}
