import SwiftUI

struct HomeView: View {
        @State private var query = ""
    @State private var showSearch = false
    @State private var showNotifications = false

    var body: some View {
        NavigationStack {
            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 24) {
                    header
                    aiSearch
                    featured
                    categories
                    trust
                }
                .padding(.horizontal, 20)
                .padding(.top, 12)
                .padding(.bottom, 32)
            }
            .background(DopenexaColor.surface.ignoresSafeArea())
            .sheet(isPresented: $showSearch) { DiscoveryView(initialQuery: query) }
            .sheet(isPresented: $showNotifications) { NotificationsView() }
        }
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 5) {
                Text("Good morning")
                    .font(DopenexaFont.display(30))
                    .foregroundStyle(DopenexaColor.ink)
                Text("A better way to get things done.")
                    .font(DopenexaFont.body(14))
                    .foregroundStyle(DopenexaColor.muted)
            }
            Spacer()
            Button { showNotifications = true } label: {
                Image(systemName: "bell")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(DopenexaColor.ink)
                    .frame(width: 44, height: 44)
                    .background(.white)
                    .clipShape(Circle())
                    .overlay(Circle().stroke(DopenexaColor.line))
            }
        }
    }

    private var aiSearch: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Dopenexa AI")
                .font(DopenexaFont.label())
                .foregroundStyle(DopenexaColor.brand)
            Button { showSearch = true } label: {
                HStack(spacing: 12) {
                    Image(systemName: "sparkles")
                        .foregroundStyle(DopenexaColor.brand)
                    Text(query.isEmpty ? "What do you need help with?" : query)
                        .font(DopenexaFont.body())
                        .foregroundStyle(query.isEmpty ? DopenexaColor.muted : DopenexaColor.ink)
                        .lineLimit(1)
                    Spacer()
                    Image(systemName: "arrow.up")
                        .foregroundStyle(.white)
                        .frame(width: 36, height: 36)
                        .background(DopenexaColor.brand)
                        .clipShape(Circle())
                }
                .padding(12)
                .background(.white)
                .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 20).stroke(DopenexaColor.line))
            }
            .buttonStyle(.plain)
            Text("Try: “I need a logo for my new company”")
                .font(DopenexaFont.label(11))
                .foregroundStyle(DopenexaColor.muted)
        }
    }

    private var featured: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack { Text("Made for your next move").font(DopenexaFont.title()); Spacer(); Text("Explore").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.brand) }
            ZStack(alignment: .bottomLeading) {
                RoundedRectangle(cornerRadius: 26, style: .continuous)
                    .fill(LinearGradient(colors: [DopenexaColor.brandDark, DopenexaColor.brand], startPoint: .topLeading, endPoint: .bottomTrailing))
                    .frame(height: 190)
                VStack(alignment: .leading, spacing: 8) {
                    DopenexaPill(text: "SMART MATCHING", icon: "sparkles")
                        .foregroundStyle(DopenexaColor.brandDark)
                    Text("Describe the outcome.\nWe’ll help you find the person.")
                        .font(DopenexaFont.display(23))
                        .foregroundStyle(.white)
                    Text("Verified professionals • Clear pricing • Secure booking")
                        .font(DopenexaFont.label(11))
                        .foregroundStyle(.white.opacity(0.72))
                }
                .padding(20)
            }
        }
    }

    private var categories: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Explore services").font(DopenexaFont.title())
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                Category(title: "Design", icon: "paintbrush.pointed.fill", color: DopenexaColor.lavender)
                Category(title: "Technology", icon: "laptopcomputer", color: DopenexaColor.brandSoft)
                Category(title: "Business", icon: "chart.bar.xaxis", color: Color.orange.opacity(0.12))
                Category(title: "Home", icon: "house.fill", color: Color.green.opacity(0.12))
            }
        }
    }

    private var trust: some View {
        HStack(spacing: 14) {
            Image(systemName: "checkmark.seal.fill").font(.title2).foregroundStyle(DopenexaColor.success)
            VStack(alignment: .leading, spacing: 3) {
                Text("Built around trust").font(DopenexaFont.body().weight(.semibold))
                Text("Verified profiles, transparent prices and booking history.").font(DopenexaFont.label(11)).foregroundStyle(DopenexaColor.muted)
            }
        }
        .dopenexaCard()
    }
}

private struct Category: View {
    let title: String; let icon: String; let color: Color
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Image(systemName: icon).font(.title3.weight(.semibold)).foregroundStyle(DopenexaColor.ink)
            Text(title).font(DopenexaFont.body().weight(.semibold))
        }
        .frame(maxWidth: .infinity, minHeight: 108, alignment: .topLeading)
        .padding(16)
        .background(color)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}
