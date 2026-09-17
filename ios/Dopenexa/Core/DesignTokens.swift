import SwiftUI

enum DopenexaColor {
    static let brand = Color(red: 0.17, green: 0.32, blue: 0.82)
    static let brandDark = Color(red: 0.09, green: 0.15, blue: 0.33)
    static let brandSoft = Color(red: 0.92, green: 0.94, blue: 1.00)
    static let lavender = Color(red: 0.95, green: 0.94, blue: 1.00)
    static let surface = Color(red: 0.975, green: 0.98, blue: 0.99)
    static let ink = Color(red: 0.08, green: 0.10, blue: 0.16)
    static let muted = Color(red: 0.43, green: 0.46, blue: 0.53)
    static let line = Color.black.opacity(0.07)
    static let success = Color(red: 0.08, green: 0.52, blue: 0.36)
    static let warning = Color(red: 0.78, green: 0.48, blue: 0.08)
}

enum DopenexaFont {
    static func display(_ size: CGFloat = 32) -> Font { .system(size: size, weight: .bold, design: .serif) }
    static func title(_ size: CGFloat = 22) -> Font { .system(size: size, weight: .bold, design: .rounded) }
    static func body(_ size: CGFloat = 15) -> Font { .system(size: size, weight: .regular, design: .rounded) }
    static func label(_ size: CGFloat = 12) -> Font { .system(size: size, weight: .semibold, design: .rounded) }
}

struct DopenexaCard: ViewModifier {
    var radius: CGFloat = 22
    func body(content: Content) -> some View {
        content
            .padding(16)
            .background(.white)
            .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous).stroke(DopenexaColor.line))
    }
}

extension View {
    func dopenexaCard(radius: CGFloat = 22) -> some View { modifier(DopenexaCard(radius: radius)) }
}

struct DopenexaPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(DopenexaFont.body(15).weight(.semibold))
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 15)
            .background(DopenexaColor.brand.opacity(configuration.isPressed ? 0.82 : 1))
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
    }
}

struct DopenexaPill: View {
    let text: String
    var icon: String? = nil
    var body: some View {
        HStack(spacing: 5) {
            if let icon { Image(systemName: icon) }
            Text(text)
        }
        .font(DopenexaFont.label())
        .foregroundStyle(DopenexaColor.brandDark)
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(DopenexaColor.brandSoft)
        .clipShape(Capsule())
    }
}
