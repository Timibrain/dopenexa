import Foundation
import Security

enum DopenexaAPIConfiguration {
    static let defaultBaseURLString = "https://api.dopenexa.com"

    static var baseURL: URL {
        let configured = Bundle.main.object(forInfoDictionaryKey: "DopenexaAPIURL") as? String
        let value = configured?.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if let value, !value.isEmpty, !value.contains("$("), let url = URL(string: value) {
            return url
        }

        if let override = UserDefaults.standard.string(forKey: "dopenexa_api_url"),
           let url = URL(string: override.trimmingCharacters(in: CharacterSet(charactersIn: "/"))) {
            return url
        }

        return URL(string: defaultBaseURLString)!
    }
}

enum DopenexaKeychain {
    private static let service = "com.dopenexa.auth"
    static func get(_ key: String) -> String? {
        let query:[String:Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:service, kSecAttrAccount as String:key, kSecReturnData as String:true, kSecMatchLimit as String:kSecMatchLimitOne]
        var result:AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let data=result as? Data else { return nil }
        return String(data:data,encoding:.utf8)
    }
    static func set(_ value: String?, for key: String) {
        let query:[String:Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:service, kSecAttrAccount as String:key]
        SecItemDelete(query as CFDictionary)
        guard let value, let data=value.data(using:.utf8) else { return }
        var item=query
        item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        SecItemAdd(item as CFDictionary,nil)
    }
    static func remove(_ key: String) { let query:[String:Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:service, kSecAttrAccount as String:key]; SecItemDelete(query as CFDictionary) }
}


private struct NotificationReadResponse: Decodable {
    let id: String
    let isRead: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case isRead = "is_read"
    }
}

struct ProfessionalProfileSavedResponse: Decodable {
    let id: String
    let onboardingComplete: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case onboardingComplete = "onboarding_complete"
    }
}

struct ReviewCreatedResponse: Decodable {
    let id: String
    let rating: Int
}

struct DeviceRegistrationResponse: Decodable {
    let id: String
    let registered: Bool
}

actor APIClient {
    static let shared = APIClient()
    private let baseURL: URL
    private var accessToken: String?
    private init() {
        baseURL = DopenexaAPIConfiguration.baseURL
        accessToken = DopenexaKeychain.get("access_token")
    }
    func setAccessToken(_ token: String?) { accessToken = token; DopenexaKeychain.set(token, for: "access_token") }
    func currentAccessToken() -> String? { accessToken }
    func hasStoredSession() -> Bool { DopenexaKeychain.get("access_token") != nil || DopenexaKeychain.get("refresh_token") != nil }
    func register(email: String, password: String, name: String, role: String = "customer") async throws -> TokenResponse { try await send("auth/register", method:"POST", body:["email":email,"password":password,"display_name":name,"role":role], response:TokenResponse.self) }
    func login(email: String, password: String) async throws -> TokenResponse { try await send("auth/login", method:"POST", body:["email":email,"password":password], response:TokenResponse.self) }
    func professional(id: String) async throws -> ProfessionalDetail { try await request("professionals/\(id)", response:ProfessionalDetail.self) }
    func createBooking(professionalID: String, serviceID: String, startsAt: Date, endsAt: Date?, note: String?) async throws -> BookingCreated {
        let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var body:[String:Any] = ["professional_id":professionalID,"service_id":serviceID,"starts_at":formatter.string(from:startsAt)]
        if let endsAt { body["ends_at"] = formatter.string(from: endsAt) }; if let note { body["customer_note"] = note }
        return try await send("bookings", method:"POST", body:body, response:BookingCreated.self)
    }
    func bookings() async throws -> [Booking] { try await request("bookings", response:[Booking].self) }
    func slots(professionalID: String, date: Date, durationMinutes: Int) async throws -> [Slot] { let df=DateFormatter(); df.dateFormat="yyyy-MM-dd"; return try await request("availability/slots?professional_id=\(professionalID)&date=\(df.string(from:date))&duration_minutes=\(durationMinutes)", response:[Slot].self) }
    func createPayment(bookingID: String) async throws -> PaymentSession { try await send("payments/create?booking_id=\(bookingID)", method:"POST", body:nil, response:PaymentSession.self) }
    func conversations() async throws -> [Conversation] { try await request("conversations", response:[Conversation].self) }
    func messages(conversationID: String) async throws -> [APIMessage] { try await request("conversations/\(conversationID)/messages", response:[APIMessage].self) }
    func sendMessage(conversationID: String, body: String) async throws -> APIMessage { try await send("conversations/\(conversationID)/messages", method:"POST", body:["body":body], response:APIMessage.self) }

    private func request<T: Decodable>(_ path:String, response:T.Type) async throws -> T { try await send(path, method:"GET", body:nil, response:response) }
    private func requestURL<T: Decodable>(_ url:URL, response:T.Type) async throws -> T {
        var request = URLRequest(url: url); request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField:"Content-Type")
        if let accessToken { request.setValue("Bearer \(accessToken)", forHTTPHeaderField:"Authorization") }
        let (data,res)=try await URLSession.shared.data(for:request)
        guard let http=res as? HTTPURLResponse else { throw APIError.server("No response") }
        guard 200..<300 ~= http.statusCode else { throw APIError.server(String(data:data,encoding:.utf8) ?? "HTTP \(http.statusCode)") }
        return try JSONDecoder.dopenexa.decode(T.self,from:data)
    }
    private func send<T: Decodable>(_ path:String, method:String, body:Any?, response:T.Type, allowRefresh: Bool = true) async throws -> T {
        guard let url = URL(string: path, relativeTo: baseURL.appendingPathComponent(""))?.absoluteURL else { throw APIError.server("Invalid request URL") }
        var request = URLRequest(url: url); request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField:"Content-Type")
        if let accessToken { request.setValue("Bearer \(accessToken)", forHTTPHeaderField:"Authorization") }
        if let body { request.httpBody = try JSONSerialization.data(withJSONObject: body) }
        let (data, res) = try await URLSession.shared.data(for: request)
        guard let http = res as? HTTPURLResponse else { throw APIError.server("No response") }
        if http.statusCode == 401 && allowRefresh && !path.hasPrefix("auth/refresh"), DopenexaKeychain.get("refresh_token") != nil {
            _ = try? await refreshSession()
            if accessToken != nil { return try await send(path, method: method, body: body, response: response, allowRefresh: false) }
        }
        guard 200..<300 ~= http.statusCode else { throw APIError.server(String(data:data,encoding:.utf8) ?? "HTTP \(http.statusCode)") }
        return try JSONDecoder.dopenexa.decode(T.self, from:data)
    }
}
enum APIError: Error, LocalizedError { case server(String); var errorDescription:String? { if case .server(let s)=self { return s }; return nil } }
extension JSONDecoder {
    static let dopenexa: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: value) { return date }
            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: value) { return date }
            throw DecodingError.dataCorruptedError(in: try decoder.singleValueContainer(), debugDescription: "Invalid ISO8601 date")
        }
        return d
    }()
}

extension APIClient {
    func me() async throws -> CurrentUser { try await request("auth/me", response: CurrentUser.self) }
    func professionalMe() async throws -> ProfessionalProfile { try await request("professional/me", response: ProfessionalProfile.self) }
    func saveProfessionalProfile(headline:String,bio:String,yearsExperience:Int,serviceArea:String?) async throws -> ProfessionalProfileSavedResponse {
        var body:[String:Any] = ["headline":headline,"bio":bio,"years_experience":yearsExperience]
        if let serviceArea { body["service_area"] = serviceArea }
        return try await send("professional/me", method:"PUT", body:body, response:ProfessionalProfileSavedResponse.self)
    }
    func professionalServices() async throws -> [Service] { try await request("professional/me/services", response:[Service].self) }
    func createProfessionalService(name:String,description:String,serviceType:String,priceNGN:Int,durationMinutes:Int?) async throws -> Service {
        var body:[String:Any] = ["name":name,"description":description,"service_type":serviceType,"price_ngn":priceNGN]
        if let durationMinutes { body["duration_minutes"] = durationMinutes }
        return try await send("professional/me/services", method:"POST", body:body, response:Service.self)
    }
    func updateProfessionalService(id:String,name:String,description:String,serviceType:String,priceNGN:Int,durationMinutes:Int?,isActive:Bool) async throws -> Service {
        var body:[String:Any] = ["name":name,"description":description,"service_type":serviceType,"price_ngn":priceNGN,"is_active":isActive]
        if let durationMinutes { body["duration_minutes"] = durationMinutes }
        return try await send("professional/me/services/\(id)", method:"PATCH", body:body, response:Service.self)
    }
    func deleteProfessionalService(id:String) async throws { _ = try await send("professional/me/services/\(id)", method:"DELETE", body:nil, response:[String:Bool].self) }
    func professionalAvailability() async throws -> [AvailabilityWindow] { try await request("professional/me/availability", response:[AvailabilityWindow].self) }
    func createAvailability(weekday:Int,startTime:String,endTime:String) async throws -> AvailabilityWindow { try await send("professional/me/availability", method:"POST", body:["weekday":weekday,"start_time":startTime,"end_time":endTime], response:AvailabilityWindow.self) }
    func deleteAvailability(id:String) async throws { _ = try await send("professional/me/availability/\(id)", method:"DELETE", body:nil, response:[String:Bool].self) }
    func professionalDashboard() async throws -> ProfessionalDashboard { try await request("professional/me/dashboard", response:ProfessionalDashboard.self) }
    func professionalRequests() async throws -> [ProfessionalRequest] { try await request("professional/me/requests", response:[ProfessionalRequest].self) }
    func confirmBooking(id:String) async throws -> [String:String] { try await send("bookings/\(id)/confirm", method:"POST", body:nil, response:[String:String].self) }
    func declineBooking(id:String) async throws -> [String:String] { try await send("bookings/\(id)/decline", method:"POST", body:nil, response:[String:String].self) }
    func startBooking(id:String) async throws -> [String:String] { try await send("bookings/\(id)/start", method:"POST", body:nil, response:[String:String].self) }
}

extension APIClient {
    func aiMatch(text: String) async throws -> AIMatchResponse { try await send("ai/match", method:"POST", body:["text":text], response:AIMatchResponse.self) }
    func aiIntent(text: String) async throws -> AIIntentResponse { try await send("ai/intent", method:"POST", body:["text":text], response:AIIntentResponse.self) }
    func project(bookingID:String) async throws -> Project { try await request("projects/\(bookingID)", response:Project.self) }
    func addProjectUpdate(bookingID:String,title:String,body:String,status:String="update") async throws -> ProjectUpdate { try await send("projects/\(bookingID)/updates", method:"POST", body:["title":title,"body":body,"status":status], response:ProjectUpdate.self) }
    func notifications() async throws -> [NotificationItem] { try await request("notifications", response:[NotificationItem].self) }
    func markNotificationRead(id:String) async throws { _ = try await send("notifications/\(id)/read", method:"POST", body:nil, response:NotificationReadResponse.self) }
}

extension APIClient {
    func paymentStatus(id:String) async throws -> PaymentStatus { try await request("payments/\(id)", response:PaymentStatus.self) }
    func refund(bookingID:String) async throws -> [String:String] { try await send("payments/refund/\(bookingID)", method:"POST", body:nil, response:[String:String].self) }
    func createReview(bookingID:String,rating:Int,body:String?) async throws -> ReviewCreatedResponse { var payload:[String:Any] = ["booking_id":bookingID,"rating":rating]; if let body { payload["body"]=body }; return try await send("reviews",method:"POST",body:payload,response:ReviewCreatedResponse.self) }
    func reviews(professionalID:String) async throws -> [ReviewItem] { try await request("reviews/professional/\(professionalID)",response:[ReviewItem].self) }
    func attachments(bookingID:String) async throws -> [AttachmentItem] { try await request("attachments/\(bookingID)",response:[AttachmentItem].self) }
    func uploadAttachment(bookingID:String,data:Data,filename:String,mimeType:String) async throws -> AttachmentItem {
        let boundary="Boundary-\(UUID().uuidString)"; var req=URLRequest(url:baseURL.appendingPathComponent("attachments/\(bookingID)")); req.httpMethod="POST"; req.setValue("multipart/form-data; boundary=\(boundary)",forHTTPHeaderField:"Content-Type")
        if let accessToken { req.setValue("Bearer \(accessToken)",forHTTPHeaderField:"Authorization") }
        var body=Data(); body.append(Data("--\(boundary)\r\n".utf8)); body.append(Data("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename.replacingOccurrences(of:"\"",with:""))\"\r\n".utf8)); body.append(Data("Content-Type: \(mimeType)\r\n\r\n".utf8)); body.append(data); body.append(Data("\r\n--\(boundary)--\r\n".utf8)); req.httpBody=body
        let (responseData,res)=try await URLSession.shared.data(for:req); guard let http=res as? HTTPURLResponse,200..<300 ~= http.statusCode else { throw APIError.server(String(data:responseData,encoding:.utf8) ?? "Upload failed") }; return try JSONDecoder.dopenexa.decode(AttachmentItem.self,from:responseData)
    }
    func openDispute(bookingID:String,reason:String,details:String) async throws -> DisputeItem { try await send("disputes/\(bookingID)",method:"POST",body:["reason":reason,"details":details],response:DisputeItem.self) }
    func dispute(bookingID:String) async throws -> DisputeItem { try await request("disputes/\(bookingID)",response:DisputeItem.self) }
}

extension APIClient {
    func refreshSession() async throws -> TokenResponse {
        guard let refresh = DopenexaKeychain.get("refresh_token") else { throw APIError.server("No refresh session") }
        let result:TokenResponse = try await send("auth/refresh",method:"POST",body:["refresh_token":refresh],response:TokenResponse.self)
        await setTokens(access: result.accessToken, refresh: result.refreshToken); return result
    }
    func setTokens(access:String?,refresh:String?) async { accessToken=access; DopenexaKeychain.set(access,for:"access_token"); DopenexaKeychain.set(refresh,for:"refresh_token") }
    func logout(refresh:String?) async { if let refresh { _=try? await send("auth/logout",method:"POST",body:["refresh_token":refresh],response:[String:Bool].self) }; accessToken=nil; DopenexaKeychain.remove("access_token"); DopenexaKeychain.remove("refresh_token") }
    func submitVerification(documentType:String,reference:String) async throws -> VerificationSubmissionItem { try await send("trust/verification",method:"POST",body:["document_type":documentType,"document_reference":reference],response:VerificationSubmissionItem.self) }
    func verificationHistory() async throws -> [VerificationSubmissionItem] { try await request("trust/verification/me",response:[VerificationSubmissionItem].self) }
    func payoutBalance() async throws -> PayoutBalance { try await request("payouts/balance",response:PayoutBalance.self) }
    func payoutHistory() async throws -> [PayoutItem] { try await request("payouts",response:[PayoutItem].self) }
    func savePayoutAccount(provider:String,accountName:String,reference:String) async throws -> [String:String] { try await send("payouts/account",method:"PUT",body:["provider":provider,"account_name":accountName,"account_reference":reference],response:[String:String].self) }
    func requestPayout() async throws -> PayoutItem { try await send("payouts",method:"POST",body:nil,response:PayoutItem.self) }
    func registerDevice(token:String,platform:String="ios") async throws -> DeviceRegistrationResponse { try await send("devices/register",method:"POST",body:["token":token,"platform":platform],response:DeviceRegistrationResponse.self) }
}

extension APIClient {
    func searchProfessionals(query:String, verified:Bool=false, minRating:Double=0, maxPriceNGN:Int?=nil, serviceType:String?=nil) async throws -> [Professional] {
        var components=URLComponents(url:baseURL.appendingPathComponent("professionals"), resolvingAgainstBaseURL:false)!
        var items:[URLQueryItem]=[]
        if !query.isEmpty { items.append(URLQueryItem(name:"q",value:query)) }
        if verified { items.append(URLQueryItem(name:"verified",value:"true")) }
        if minRating > 0 { items.append(URLQueryItem(name:"min_rating",value:String(minRating))) }
        if let maxPriceNGN { items.append(URLQueryItem(name:"max_price_ngn",value:String(maxPriceNGN))) }
        if let serviceType { items.append(URLQueryItem(name:"service_type",value:serviceType)) }
        components.queryItems=items
        return try await requestURL(components.url!, response:[Professional].self)
    }
    func savedProfessionals() async throws -> [SavedProfessional] { try await request("saved",response:[SavedProfessional].self) }
    func saveProfessional(id:String) async throws { _ = try await send("saved/\(id)",method:"POST",body:nil,response:[String:Bool].self) }
    func unsaveProfessional(id:String) async throws { _ = try await send("saved/\(id)",method:"DELETE",body:nil,response:[String:Bool].self) }
}

extension APIClient {
    func recommendations() async throws -> [Recommendation] { try await request("recommendations", response:[Recommendation].self) }
}
