import AuthenticationServices
import SwiftUI

struct SplashView: View {
    var body: some View {
        ZStack {
            LinearGradient(colors: [DopenexaColor.brandDark, DopenexaColor.brand], startPoint: .topLeading, endPoint: .bottomTrailing).ignoresSafeArea()
            VStack(spacing: 18) {
                DopenexaMark(light: true)
                Text("Dopenexa").font(DopenexaFont.display(42)).foregroundStyle(.white)
                Text("Find the right fit for the work that matters.").font(DopenexaFont.body()).foregroundStyle(.white.opacity(0.78))
            }
        }
    }
}

struct MarketplaceIntroductionView: View {
    @EnvironmentObject private var store: AppStore
    @State private var page = 0
    private let slides = [
        ("Find the right professional", "Discover people with the skills, experience and services your work needs.", "sparkles"),
        ("Book and pay securely in Naira", "Simple booking, protected payments and clear pricing from start to finish.", "lock.shield"),
        ("Work with confidence", "Verified professionals, useful reviews and a workspace that keeps every project moving.", "checkmark.seal")
    ]

    var body: some View {
        VStack(spacing: 24) {
            HStack { DopenexaMark(); Spacer(); Text("(page + 1)/(slides.count)").font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted) }
            TabView(selection: $page) {
                ForEach(Array(slides.enumerated()), id: \.offset) { index, slide in
                    VStack(alignment: .leading, spacing: 24) {
                        Spacer()
                        Image(systemName: slide.2).font(.system(size: 64, weight: .medium)).foregroundStyle(DopenexaColor.brand)
                        Text(slide.0).font(DopenexaFont.display(36)).foregroundStyle(DopenexaColor.brandDark)
                        Text(slide.1).font(DopenexaFont.body(18)).foregroundStyle(DopenexaColor.muted).lineSpacing(5)
                        Spacer()
                    }.tag(index)
                }
            }.tabViewStyle(.page(indexDisplayMode: .never))
            HStack(spacing: 8) { ForEach(0..<slides.count, id: \.self) { index in Capsule().fill(index == page ? DopenexaColor.brand : DopenexaColor.line).frame(width: index == page ? 26 : 8, height: 7) } }.frame(maxWidth: .infinity, alignment: .leading)
            Button(page == slides.count - 1 ? "Get Started" : "Continue") { if page < slides.count - 1 { withAnimation { page += 1 } } else { store.completeIntroduction() } }.buttonStyle(DopenexaPrimaryButtonStyle())
            Button("Already have an account? Sign in") { store.completeIntroduction(); store.showSignIn() }.font(DopenexaFont.label()).foregroundStyle(DopenexaColor.brand)
        }.padding(24).background(DopenexaColor.surface.ignoresSafeArea())
    }
}

struct RoleSelectionView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            DopenexaMark()
            Spacer(minLength: 10)
            Text("How do you want to use Dopenexa?").font(DopenexaFont.display(34)).foregroundStyle(DopenexaColor.brandDark)
            Text("Choose the workspace that fits what you need today.").font(DopenexaFont.body(17)).foregroundStyle(DopenexaColor.muted)
            VStack(spacing: 14) {
                RoleCard(icon: "person.2.fill", title: "I need a professional", detail: "Find trusted specialists and book the help you need.", tint: DopenexaColor.brand) { store.chooseRole("customer") }
                RoleCard(icon: "briefcase.fill", title: "I provide professional services", detail: "Build your profile, publish services and win better work.", tint: DopenexaColor.brandDark) { store.chooseRole("professional") }
            }
            Spacer()
            Button("Already have an account? Sign in") { store.showSignIn() }.frame(maxWidth: .infinity).font(DopenexaFont.label()).foregroundStyle(DopenexaColor.brand)
        }.padding(24).background(DopenexaColor.surface.ignoresSafeArea())
    }
}

struct AuthenticationView: View {
    @EnvironmentObject private var store: AppStore
    let role: String?
    @State private var showEmail = false
    var isRegistration: Bool { role != nil }
    var title: String { isRegistration ? (role == "professional" ? "Create your professional account" : "Create your customer account") : "Welcome back" }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 20) {
                HStack { DopenexaMark(); Spacer(); if isRegistration { Button("Back") { store.destination = .roleSelection }.font(DopenexaFont.label()).foregroundStyle(DopenexaColor.brand) } }
                Spacer(minLength: 18)
                Text(title).font(DopenexaFont.display(36)).foregroundStyle(DopenexaColor.brandDark)
                Text(isRegistration ? "Your Dopenexa workspace starts here." : "Sign in to continue to your marketplace.").font(DopenexaFont.body(17)).foregroundStyle(DopenexaColor.muted)
                if showEmail {
                    EmailAuthenticationForm(role: role)
                } else {
                    AppleSignInUnavailableButton()
                    Button("Continue with Email") { withAnimation { showEmail = true } }.buttonStyle(DopenexaPrimaryButtonStyle())
                    if isRegistration { Text("By continuing, you agree to use Dopenexa responsibly and keep your account details secure.").font(DopenexaFont.label(11)).foregroundStyle(DopenexaColor.muted) }
                }
                Spacer()
                if !isRegistration { Button("New to Dopenexa? Create an account") { store.destination = .roleSelection }.frame(maxWidth: .infinity).font(DopenexaFont.label()).foregroundStyle(DopenexaColor.brand) }
            }.padding(24).background(DopenexaColor.surface.ignoresSafeArea()).navigationBarHidden(true)
        }
    }
}

private struct EmailAuthenticationForm: View {
    @EnvironmentObject private var store: AppStore
    let role: String?
    @State private var name = ""
    @State private var email = ""
    @State private var password = ""
    var body: some View {
        VStack(spacing: 13) {
            if role != nil { TextField("Full name", text: $name).textContentType(.name).textFieldStyle(.roundedBorder) }
            TextField("Email address", text: $email).textContentType(.emailAddress).textInputAutocapitalization(.never).keyboardType(.emailAddress).textFieldStyle(.roundedBorder)
            SecureField("Password", text: $password).textContentType(role == nil ? .password : .newPassword).textFieldStyle(.roundedBorder)
            if let error = store.error { Text(error).font(DopenexaFont.label(12)).foregroundStyle(.red).frame(maxWidth: .infinity, alignment: .leading) }
            Button(store.isLoading ? "Connecting…" : (role == nil ? "Sign in with Email" : "Create account")) {
                Task { if let role { await store.register(email: email, password: password, name: name, role: role) } else { await store.login(email: email, password: password) } }
            }.buttonStyle(DopenexaPrimaryButtonStyle()).disabled(store.isLoading || email.isEmpty || password.isEmpty || (role != nil && name.isEmpty))
            AppleSignInUnavailableButton()
        }
    }
}

struct FaceIDWelcomeView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        VStack(spacing: 22) {
            Spacer()
            DopenexaMark()
            Image(systemName: "faceid").font(.system(size: 70, weight: .light)).foregroundStyle(DopenexaColor.brand)
            Text("Welcome back").font(DopenexaFont.display(34)).foregroundStyle(DopenexaColor.brandDark)
            Text("Your secure session is ready on this device.").font(DopenexaFont.body(17)).foregroundStyle(DopenexaColor.muted).multilineTextAlignment(.center)
            if let error = store.faceIDError { Text(error).font(DopenexaFont.label()).foregroundStyle(.red).multilineTextAlignment(.center) }
            Button("Sign in with Face ID") { Task { await store.unlockWithFaceID() } }.buttonStyle(DopenexaPrimaryButtonStyle())
            Button("Use another account") { store.useAnotherAccount() }.font(DopenexaFont.label()).foregroundStyle(DopenexaColor.brand)
            Spacer()
        }.padding(24).background(DopenexaColor.surface.ignoresSafeArea())
    }
}

private struct AppleSignInUnavailableButton: View {
    var body: some View {
        VStack(spacing: 7) {
            SignInWithAppleButton(.continue) { _ in } onCompletion: { _ in }
                .signInWithAppleButtonStyle(.black).frame(height: 52).clipShape(RoundedRectangle(cornerRadius: 15)).disabled(true)
            Text("Apple sign in will be available after secure backend identity verification is enabled.").font(DopenexaFont.label(10)).foregroundStyle(DopenexaColor.muted).multilineTextAlignment(.center)
        }
    }
}

private struct RoleCard: View {
    let icon: String; let title: String; let detail: String; let tint: Color; let action: () -> Void
    var body: some View { Button(action: action) { HStack(spacing: 16) { Image(systemName: icon).font(.title2).foregroundStyle(tint).frame(width: 42, height: 42).background(tint.opacity(0.1)).clipShape(Circle()); VStack(alignment: .leading, spacing: 5) { Text(title).font(DopenexaFont.body().weight(.semibold)).foregroundStyle(DopenexaColor.ink); Text(detail).font(DopenexaFont.label()).foregroundStyle(DopenexaColor.muted).multilineTextAlignment(.leading) }; Spacer(); Image(systemName: "chevron.right").foregroundStyle(DopenexaColor.muted) }.padding(18).background(.white).clipShape(RoundedRectangle(cornerRadius: 21, style: .continuous)).overlay(RoundedRectangle(cornerRadius: 21, style: .continuous).stroke(DopenexaColor.line)) }.buttonStyle(.plain) }
}

struct DopenexaMark: View {
    var light = false
    var body: some View { ZStack { Circle().fill(light ? .white.opacity(0.18) : DopenexaColor.brandSoft); Image(systemName: "sparkles").font(.system(size: 20, weight: .bold)).foregroundStyle(light ? .white : DopenexaColor.brand) }.frame(width: 48, height: 48) }
}
