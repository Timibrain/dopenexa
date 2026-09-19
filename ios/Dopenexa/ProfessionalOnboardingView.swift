import SwiftUI

struct ProfessionalOnboardingView: View {
    @EnvironmentObject private var store: AppStore
    let profile: ProfessionalProfile?
    @State private var headline = ""
    @State private var bio = ""
    @State private var years = 1
    @State private var area = ""
    @State private var serviceName = ""
    @State private var serviceDescription = ""
    @State private var serviceType = "project"
    @State private var price = ""
    @State private var weekday = 1
    @State private var startTime = "09:00"
    @State private var endTime = "17:00"
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section { Text("Turn your expertise into a profile customers can trust and book.").font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted) }
                Section("Your positioning") {
                    TextField("Headline", text: $headline)
                    TextField("Service area", text: $area)
                    TextField("Bio", text: $bio, axis: .vertical).lineLimit(4...8)
                }
                Section("Experience") { Stepper("Years of experience: \(years)", value: $years, in: 0...80) }
                Section("First service") {
                    TextField("Service name", text: $serviceName)
                    TextField("What is included?", text: $serviceDescription, axis: .vertical).lineLimit(2...5)
                    Picker("Service type", selection: $serviceType) { Text("Project").tag("project"); Text("Hourly").tag("hourly"); Text("Appointment").tag("appointment") }
                    HStack { Text("Price in Naira"); Spacer(); TextField("0", text: $price).keyboardType(.numberPad).multilineTextAlignment(.trailing) }
                }
                Section("Availability") {
                    Picker("Day", selection: $weekday) { ForEach(0..<7, id: \.self) { Text(dayName($0)).tag($0) } }
                    HStack { Text("From"); Spacer(); TextField("09:00", text: $startTime).multilineTextAlignment(.trailing) }
                    HStack { Text("Until"); Spacer(); TextField("17:00", text: $endTime).multilineTextAlignment(.trailing) }
                }
                Section("Verification") {
                    Label(profile?.verificationStatus == "verified" ? "Verified" : "Review pending", systemImage: profile?.verificationStatus == "verified" ? "checkmark.seal.fill" : "clock")
                    Text("Verification is a separate review. Completing onboarding does not verify your professional account.").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted)
                }
                Section {
                    if let error { Text(error).font(DopenexaFont.label()).foregroundStyle(.red) }
                    Button(saving ? "Creating your workspace…" : "Finish professional setup") { Task { await save() } }.buttonStyle(DopenexaPrimaryButtonStyle()).disabled(saving || headline.isEmpty || bio.isEmpty || serviceName.isEmpty || Int(price) == nil)
                }
            }
            .navigationTitle("Professional setup")
            .navigationBarTitleDisplayMode(.inline)
            .onAppear {
                headline = profile?.headline ?? ""; bio = profile?.bio ?? ""; years = profile?.yearsExperience ?? 1; area = profile?.serviceArea ?? ""
            }
        }
    }

    private func dayName(_ day: Int) -> String { Calendar.current.weekdaySymbols[day] }

    private func save() async {
        guard let priceNGN = Int(price) else { return }
        saving = true; error = nil
        do {
            _ = try await APIClient.shared.saveProfessionalProfile(headline: headline, bio: bio, yearsExperience: years, serviceArea: area.isEmpty ? nil : area)
            let services = (try? await APIClient.shared.professionalServices()) ?? []
            if !services.contains(where: { $0.name.caseInsensitiveCompare(serviceName) == .orderedSame }) {
                _ = try await APIClient.shared.createProfessionalService(name: serviceName, description: serviceDescription, serviceType: serviceType, priceNGN: priceNGN, durationMinutes: nil)
            }
            let availability = (try? await APIClient.shared.professionalAvailability()) ?? []
            if !availability.contains(where: { $0.weekday == weekday && $0.startTime.hasPrefix(startTime) && $0.endTime.hasPrefix(endTime) }) {
                _ = try await APIClient.shared.createAvailability(weekday: weekday, startTime: startTime, endTime: endTime)
            }
            await store.completeProfessionalOnboarding()
        } catch { self.error = error.localizedDescription }
        saving = false
    }
}
