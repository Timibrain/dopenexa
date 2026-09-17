import SwiftUI

struct CustomerHomeView: View {
    @EnvironmentObject private var store: AppStore
    @State private var query = ""
    @State private var showAI = false
    var body: some View {
        NavigationStack {
            ScrollView(showsIndicators:false) {
                VStack(alignment:.leading,spacing:22) {
                    hero
                    quickActions
                    RecommendationStrip()
                    recentBookings
                }.padding(.horizontal,20).padding(.top,12).padding(.bottom,28)
            }
            .background(DopenexaColor.surface.ignoresSafeArea())
            .navigationTitle("")
            .navigationDestination(isPresented:$showAI) { AIResultsView(query:query) }
        }
    }
    private var hero: some View {
        VStack(alignment:.leading,spacing:14) {
            HStack { DopenexaPill(text:"Your AI concierge",icon:"sparkles"); Spacer(); NavigationLink { NotificationsView() } label: { Image(systemName:"bell").font(.title3).foregroundStyle(DopenexaColor.ink).frame(width:42,height:42).background(.white).clipShape(Circle()).overlay(Circle().stroke(DopenexaColor.line)) } }
            Text("What do you need\nhelp with?").font(DopenexaFont.display(34)).foregroundStyle(DopenexaColor.ink)
            Text("Describe the outcome. Dopenexa will help you discover professionals who fit.").font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted)
            HStack(spacing:10) {
                Image(systemName:"sparkle.magnifyingglass").foregroundStyle(DopenexaColor.brand)
                TextField("e.g. Build a website for my business",text:$query)
                    .textInputAutocapitalization(.sentences)
                Button { if !query.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty { showAI=true } } label: { Image(systemName:"arrow.up").font(.headline).foregroundStyle(.white).frame(width:38,height:38).background(DopenexaColor.brand).clipShape(Circle()) }
            }.padding(10).background(.white).clipShape(RoundedRectangle(cornerRadius:20)).overlay(RoundedRectangle(cornerRadius:20).stroke(DopenexaColor.line))
        }.padding(20).background(LinearGradient(colors:[DopenexaColor.brandSoft,.white],startPoint:.topLeading,endPoint:.bottomTrailing)).clipShape(RoundedRectangle(cornerRadius:28))
    }
    private var quickActions: some View {
        HStack(spacing:12) {
            NavigationLink { DiscoveryView() } label: { HomeAction(icon:"square.grid.2x2",title:"Explore",subtitle:"Browse skills") }
            NavigationLink { SavedProfessionalsView() } label: { HomeAction(icon:"bookmark",title:"Saved",subtitle:"Your shortlist") }
        }
    }
    private var recentBookings: some View {
        VStack(alignment:.leading,spacing:10) {
            HStack { Text("Your bookings").font(DopenexaFont.title(20)); Spacer(); NavigationLink("See all") { BookingsView() }.font(DopenexaFont.label()).foregroundStyle(DopenexaColor.brand) }
            if store.bookings.isEmpty { Text("Your next booking will appear here.").font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted).dopenexaCard() }
            else { ForEach(Array(store.bookings.prefix(2))) { b in BookingMiniCard(booking:b) } }
        }.task { await store.loadBookings() }
    }
}
private struct HomeAction:View { let icon:String; let title:String; let subtitle:String; var body:some View { HStack(spacing:10){Image(systemName:icon).font(.headline).foregroundStyle(DopenexaColor.brand).frame(width:38,height:38).background(DopenexaColor.brandSoft).clipShape(Circle());VStack(alignment:.leading){Text(title).font(DopenexaFont.body().weight(.semibold));Text(subtitle).font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted)}}.frame(maxWidth:.infinity,alignment:.leading).dopenexaCard(radius:18)} }
private struct BookingMiniCard:View { let booking:Booking; var body:some View { HStack{VStack(alignment:.leading,spacing:4){Text(booking.startsAt.formatted(date:.abbreviated,time:.shortened)).font(DopenexaFont.label());Text("₦\(booking.totalNGN.formatted())").font(DopenexaFont.title(17))};Spacer();DopenexaPill(text:booking.status.replacingOccurrences(of:"_",with:" ").capitalized)}.dopenexaCard(radius:18) } }
