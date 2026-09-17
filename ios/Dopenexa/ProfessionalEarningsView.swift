import SwiftUI

struct ProfessionalEarningsView: View {
    @State private var balance:PayoutBalance?
    @State private var payouts:[PayoutItem]=[]
    @State private var provider="pending"
    @State private var accountName=""
    @State private var accountReference=""
    @State private var error:String?
    @State private var busy=false
    var body: some View {
        ScrollView { VStack(alignment:.leading,spacing:18) {
            if let b=balance { HStack(spacing:12) { EarnCard(title:"Available",value:"₦\(b.availableNGN.formatted())"); EarnCard(title:"Earned",value:"₦\(b.earnedNGN.formatted())") } }
            VStack(alignment:.leading,spacing:10) {
                Text("Payout account").font(DopenexaFont.title(19)); TextField("Provider (e.g. configured bank provider)",text:$provider).textFieldStyle(.roundedBorder); TextField("Account name",text:$accountName).textFieldStyle(.roundedBorder); TextField("Account reference",text:$accountReference).textFieldStyle(.roundedBorder); Button("Save payout account") { Task { await saveAccount() } }.buttonStyle(DopenexaPrimaryButtonStyle())
            }.dopenexaCard()
            Button("Request available payout") { Task { await requestPayout() } }.buttonStyle(DopenexaPrimaryButtonStyle()).disabled(busy || (balance?.availableNGN ?? 0) < (balance?.minimumPayoutNGN ?? 1000))
            VStack(alignment:.leading,spacing:10) { Text("Payout history").font(DopenexaFont.title(19)); ForEach(payouts) { p in HStack { VStack(alignment:.leading){Text("₦\(p.amountNGN.formatted())").font(.headline);Text(p.createdAt.formatted(date:.abbreviated,time:.omitted)).font(.caption).foregroundStyle(.secondary)}; Spacer(); DopenexaPill(text:p.status.capitalized) }.dopenexaCard(radius:16) } }
            if let error { Text(error).foregroundStyle(.red).font(.caption) }
        }.padding(20) }.background(DopenexaColor.surface.ignoresSafeArea()).navigationTitle("Earnings") .task{await load()}
    }
    private func load() async { do { async let b=APIClient.shared.payoutBalance(); async let p=APIClient.shared.payoutHistory(); balance=try await b; payouts=try await p } catch { self.error = error.localizedDescription } }
    private func saveAccount() async { do { _=try await APIClient.shared.savePayoutAccount(provider:provider,accountName:accountName,reference:accountReference); await load() } catch { self.error = error.localizedDescription } }
    private func requestPayout() async { busy=true; defer{busy=false}; do { _=try await APIClient.shared.requestPayout(); await load() } catch { self.error = error.localizedDescription } }
}
private struct EarnCard:View { let title:String;let value:String;var body:some View{VStack(alignment:.leading,spacing:6){Text(title).font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted);Text(value).font(DopenexaFont.title(21))}.frame(maxWidth:.infinity,alignment:.leading).dopenexaCard(radius:18)} }
