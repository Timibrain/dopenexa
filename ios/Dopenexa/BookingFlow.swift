import SwiftUI
import SafariServices

private struct CheckoutSafariView: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> SFSafariViewController { SFSafariViewController(url: url) }
    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}

struct BookingFlow: View {
    let professional: Professional
    let service: Service
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var date = Calendar.current.date(byAdding: .day, value: 1, to: Date()) ?? Date()
    @State private var slots:[Slot] = []
    @State private var selectedSlot:Slot?
    @State private var booking:BookingCreated?
    @State private var payment:PaymentSession?
    @State private var showCheckout = false
    @State private var paymentStatusText: String?
    @State private var step=0
    @State private var loading=false

    var body: some View { NavigationStack { VStack(spacing:0) { progress; ScrollView { VStack(alignment:.leading,spacing:22) { if step==0 { schedule } else if step==1 { checkout } else { confirmation } }.padding(20) }; if step<2 { Button(step==0 ? "Continue to payment" : "Create booking & continue") { Task { await next() } }.buttonStyle(DopenexaPrimaryButtonStyle()).padding(20).disabled(loading || (step==0 && selectedSlot==nil)) } }.background(DopenexaColor.surface.ignoresSafeArea()).navigationTitle(step==0 ? "Choose a time" : step==1 ? "Secure checkout" : "Booking ready").toolbar{ToolbarItem(placement:.cancellationAction){Button("Close"){dismiss()}}}.task{await loadSlots()}.sheet(isPresented:$showCheckout,onDismiss:{Task{await refreshPaymentStatus()}}){if let value=payment?.checkoutURL,let url=URL(string:value){CheckoutSafariView(url:url)}} } }
    private var progress:some View { HStack{ForEach(0..<3){i in Capsule().fill(i<=step ? DopenexaColor.brand : DopenexaColor.line).frame(height:4)}}.padding(.horizontal,20).padding(.top,10) }
    private var schedule:some View { VStack(alignment:.leading,spacing:18){Text(service.name).font(DopenexaFont.display(28));Text("with \(professional.name)").font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted);DatePicker("Date",selection:$date,in:Date()...,displayedComponents:.date).datePickerStyle(.graphical).padding().background(.white).clipShape(RoundedRectangle(cornerRadius:20)).onChange(of:date){_,_ in Task{await loadSlots()}};Text("Live availability").font(DopenexaFont.title());if loading {ProgressView()} else if slots.isEmpty {Text("No available times for this date. Try another day.").foregroundStyle(DopenexaColor.muted)} else {LazyVGrid(columns:[GridItem(.flexible()),GridItem(.flexible()),GridItem(.flexible())],spacing:10){ForEach(slots){slot in Button(slot.startsAt.formatted(date:.omitted,time:.shortened)){selectedSlot=slot}.font(DopenexaFont.label()).frame(maxWidth:.infinity).padding(.vertical,13).background(selectedSlot?.id == slot.id ? DopenexaColor.brandSoft : .white).clipShape(RoundedRectangle(cornerRadius:13)).overlay(RoundedRectangle(cornerRadius:13).stroke(selectedSlot?.id == slot.id ? DopenexaColor.brand : DopenexaColor.line))}}}} }
    private var checkout:some View { VStack(alignment:.leading,spacing:18){Text("Review your booking").font(DopenexaFont.display(28));VStack(spacing:14){Row(label:"Service",value:service.name);Row(label:"Professional",value:professional.name);if let slot=selectedSlot{Row(label:"When",value:slot.startsAt.formatted(date:.abbreviated,time:.shortened))};Divider();Row(label:"Total",value:"₦\(service.priceNGN.formatted())",bold:true)}.dopenexaCard();HStack(spacing:10){Image(systemName:"lock.fill");Text("Dopenexa will create a secure payment session. No card details are stored by this app.").font(DopenexaFont.label(11))}.foregroundStyle(DopenexaColor.muted)} }
    private var confirmation:some View { VStack(spacing:18){Spacer(minLength:35);Image(systemName:"checkmark.circle.fill").font(.system(size:78)).foregroundStyle(DopenexaColor.success);Text("Booking created").font(DopenexaFont.display(30));Text(paymentStatusText ?? payment?.message ?? "Your booking is recorded and ready for payment-provider checkout.").multilineTextAlignment(.center).font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted);if let b=booking{VStack(alignment:.leading,spacing:10){Row(label:"Service",value:service.name);Row(label:"Booking",value:String(b.id.prefix(8)));Row(label:"Amount",value:"₦\(b.totalNGN.formatted())",bold:true)}.dopenexaCard()};Button("Done"){dismiss()}.buttonStyle(DopenexaPrimaryButtonStyle())}.frame(maxWidth:.infinity) }
    private func loadSlots() async { loading=true;do{slots=try await APIClient.shared.slots(professionalID:professional.id,date:date,durationMinutes:service.durationMinutes ?? 60)}catch{slots=[]};loading=false }
    private func refreshPaymentStatus() async { guard let id=payment?.paymentID else{return}; for _ in 0..<3 { do { let current=try await APIClient.shared.paymentStatus(id:id); paymentStatusText="Payment status: \(current.status)"; if current.status == "paid" || current.status == "failed" { break } } catch { break }; try? await Task.sleep(nanoseconds:1_000_000_000) } }
    private func next() async { if step==0 {step=1;return};guard let slot=selectedSlot else{return};loading=true;booking=await store.book(professionalID:professional.id,serviceID:service.id,date:slot.startsAt,endsAt:slot.endsAt);if let b=booking { payment=await store.pay(bookingID:b.id);step=2; if let urlString=payment?.checkoutURL, let url=URL(string:urlString) { showCheckout=true } };loading=false }
}
private struct Row:View{let label:String;let value:String;var bold=false;var body:some View{HStack(alignment:.top){Text(label).foregroundStyle(DopenexaColor.muted);Spacer();Text(value).multilineTextAlignment(.trailing).fontWeight(bold ? .bold:.regular)}.font(DopenexaFont.label())}}
