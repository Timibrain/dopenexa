import Foundation
import SwiftUI

@MainActor final class AppStore: ObservableObject {
    @Published var professionals:[Professional] = []
    @Published var bookings:[Booking] = []
    @Published var conversations:[Conversation] = []
    @Published var isAuthenticated = false
    @Published var isLoading = false
    @Published var error:String?
    @Published var currentUser: CurrentUser?

    init() { isAuthenticated = DopenexaKeychain.get("access_token") != nil || DopenexaKeychain.get("refresh_token") != nil; if isAuthenticated { Task { if (try? await APIClient.shared.refreshSession()) != nil { await refreshUser() } else { isAuthenticated = false } } } }
    func login(email:String,password:String) async { await authenticate { try await APIClient.shared.login(email:email,password:password) } }
    func register(email:String,password:String,name:String,role:String="customer") async { await authenticate { try await APIClient.shared.register(email:email,password:password,name:name,role:role) } }
    private func authenticate(_ call:() async throws -> TokenResponse) async { isLoading=true; error=nil; do { let token=try await call(); await APIClient.shared.setTokens(access: token.accessToken, refresh: token.refreshToken); isAuthenticated=true; await refreshUser() } catch { self.error = error.localizedDescription }; isLoading=false }
    func refreshUser() async { do { currentUser = try await APIClient.shared.me(); UserDefaults.standard.set(currentUser?.id, forKey:"dopenexa_user_id") } catch { if isAuthenticated { self.error = error.localizedDescription } } }
    func logout() { let refresh=DopenexaKeychain.get("refresh_token"); Task { await APIClient.shared.logout(refresh:refresh) }; isAuthenticated=false; professionals=[]; bookings=[]; conversations=[]; currentUser=nil }
    func search(_ q:String, verified:Bool=false, minRating:Double=0, maxPriceNGN:Int?=nil, serviceType:String?=nil) async { isLoading=true; do { professionals=try await APIClient.shared.searchProfessionals(query:q,verified:verified,minRating:minRating,maxPriceNGN:maxPriceNGN,serviceType:serviceType) } catch { self.error = error.localizedDescription }; isLoading=false }
    func loadBookings() async { do { bookings=try await APIClient.shared.bookings() } catch { self.error = error.localizedDescription } }
    func loadConversations() async { do { conversations=try await APIClient.shared.conversations() } catch { self.error = error.localizedDescription } }
    func book(professionalID:String,serviceID:String,date:Date,endsAt:Date?) async -> BookingCreated? { do { let b=try await APIClient.shared.createBooking(professionalID:professionalID,serviceID:serviceID,startsAt:date,endsAt:endsAt,note:nil); await loadBookings(); return b } catch { self.error = error.localizedDescription; return nil } }
    func pay(bookingID:String) async -> PaymentSession? { do { return try await APIClient.shared.createPayment(bookingID:bookingID) } catch { self.error = error.localizedDescription; return nil } }
}
