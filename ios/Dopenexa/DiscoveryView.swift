import SwiftUI

struct DiscoveryView: View {
    @EnvironmentObject private var store: AppStore
    var initialQuery: String = ""
    @State private var query = ""
    @State private var showAIResults = false
    @State private var showFilters = false
    @State private var verifiedOnly = false
    @State private var minRating = 0.0
    @State private var maxPrice = 0
    @State private var serviceType = ""
    var body: some View {
        NavigationStack { ScrollView(showsIndicators:false) { VStack(alignment:.leading,spacing:18) {
            HStack{VStack(alignment:.leading,spacing:5){Text("Find your match").font(DopenexaFont.display(30));Text("Search naturally, then narrow the list when you need to.").font(DopenexaFont.body()).foregroundStyle(DopenexaColor.muted)};Spacer()}
            HStack{Image(systemName:"sparkles").foregroundStyle(DopenexaColor.brand);TextField("What outcome do you need?",text:$query).onSubmit{showAIResults=true};if !query.isEmpty{Button{query="";Task{await search()}}label:{Image(systemName:"xmark.circle.fill").foregroundStyle(DopenexaColor.muted)}}}.padding(15).background(.white).clipShape(RoundedRectangle(cornerRadius:18)).overlay(RoundedRectangle(cornerRadius:18).stroke(DopenexaColor.line))
            HStack{Text("\(store.professionals.count) professionals").font(DopenexaFont.label());Spacer();Button{showFilters=true}label:{Label("Filters",systemImage:"slider.horizontal.3")}.font(DopenexaFont.label()).foregroundStyle(DopenexaColor.brand)}
            if verifiedOnly || minRating > 0 || maxPrice > 0 || !serviceType.isEmpty { ScrollView(.horizontal,showsIndicators:false){HStack{if verifiedOnly{DopenexaPill(text:"Verified")};if minRating>0{DopenexaPill(text:"★ \(String(format: "%.0f", minRating))+")};if maxPrice>0{DopenexaPill(text:"≤ ₦\(maxPrice.formatted())")};if !serviceType.isEmpty{DopenexaPill(text:serviceType.capitalized)}}} }
            if store.isLoading{ProgressView().frame(maxWidth:.infinity).padding(30)}else{LazyVStack(spacing:14){ForEach(store.professionals){p in NavigationLink { ProfessionalView(professional:p) } label: { ProfessionalCard(professional:p) }.buttonStyle(.plain)}}}
            if let e=store.error{Text(e).font(.caption).foregroundStyle(.red)}
        }.padding(20)}.background(DopenexaColor.surface.ignoresSafeArea()).navigationBarHidden(true)
        .sheet(isPresented:$showFilters){FilterSheet(verifiedOnly:$verifiedOnly,minRating:$minRating,maxPrice:$maxPrice,serviceType:$serviceType){Task{await search()}}}
        .sheet(isPresented:$showAIResults){NavigationStack{AIResultsView(query:query).environmentObject(store)}}.task{query=initialQuery;await search()}}
    }
    private func search() async { await store.search(query,verified:verifiedOnly,minRating:minRating,maxPriceNGN:maxPrice > 0 ? maxPrice:nil,serviceType:serviceType.isEmpty ? nil:serviceType) }
}
private struct ProfessionalCard:View{let professional:Professional;var body:some View{VStack(alignment:.leading,spacing:14){HStack{Image(systemName:professional.imageName).font(.title2).foregroundStyle(DopenexaColor.brandDark).frame(width:54,height:54).background(DopenexaColor.brandSoft).clipShape(Circle());VStack(alignment:.leading,spacing:4){HStack{Text(professional.name).font(DopenexaFont.body().weight(.bold));if professional.verified{Image(systemName:"checkmark.seal.fill").foregroundStyle(DopenexaColor.success)}};Text(professional.headline ?? "Professional").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted)};Spacer();Text(professional.match>0 ? "\(professional.match)%":"Matched").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.brand)};HStack{DopenexaPill(text:"★ \(String(format: "%.1f", professional.rating))");DopenexaPill(text:"\(professional.completedJobs) jobs")};Text("View profile").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.brand)}.dopenexaCard()}}
private struct FilterSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var verifiedOnly: Bool
    @Binding var minRating: Double
    @Binding var maxPrice: Int
    @Binding var serviceType: String
    let apply: () -> Void
    var body: some View {
        NavigationStack {
            Form {
                Section("Trust") { Toggle("Verified professionals", isOn: $verifiedOnly) }
                Section("Rating") {
                    Picker("Minimum rating", selection: $minRating) {
                        Text("Any").tag(0.0); Text("4+").tag(4.0); Text("4.5+").tag(4.5)
                    }
                }
                Section("Budget") { TextField("Maximum ₦", value: $maxPrice, format: .number).keyboardType(.numberPad) }
                Section("Service format") {
                    Picker("Type", selection: $serviceType) {
                        Text("Any").tag("")
                        ForEach(["appointment","hourly","fixed","project","recurring"], id: \.self) { Text($0.capitalized).tag($0) }
                    }
                }
            }
            .navigationTitle("Filters")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Apply") { apply(); dismiss() } } }
        }
    }
}
