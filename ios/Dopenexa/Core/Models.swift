import Foundation

struct Professional: Codable, Identifiable, Hashable {
    let id: String; let name: String; let headline: String?; let bio: String?
    let rating: Double; let reviews: Int; let verified: Bool; let completedJobs: Int
    var match: Int = 0; var matchReason: String?; var location: String = "Lagos"; var imageName: String = "person.crop.circle.fill"
    enum CodingKeys: String, CodingKey { case id,name,headline,bio,rating,reviews,verified; case completedJobs = "completed_jobs"; case match, matchReason = "match_reason" }
}
extension Professional {
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(String.self, forKey: .id)
        name = try values.decode(String.self, forKey: .name)
        headline = try values.decodeIfPresent(String.self, forKey: .headline)
        bio = try values.decodeIfPresent(String.self, forKey: .bio)
        rating = try values.decode(Double.self, forKey: .rating)
        reviews = try values.decode(Int.self, forKey: .reviews)
        verified = try values.decode(Bool.self, forKey: .verified)
        completedJobs = try values.decode(Int.self, forKey: .completedJobs)
        match = try values.decodeIfPresent(Int.self, forKey: .match) ?? 0
        matchReason = try values.decodeIfPresent(String.self, forKey: .matchReason)
    }
}

struct ProfessionalDetail: Codable, Identifiable {
    let id: String; let name: String; let headline: String?; let bio: String?; let yearsExperience: Int?
    let rating: Double; let reviews: Int; let verified: Bool; let services: [Service]
    enum CodingKeys: String, CodingKey { case id,name,headline,bio; case yearsExperience = "years_experience"; case rating,reviews,verified,services }
}
struct Service: Codable, Identifiable, Hashable {
    let id: String; let name: String; let description: String?; let serviceType: String; let priceNGN: Int; let durationMinutes: Int?
    enum CodingKeys: String, CodingKey { case id,name,description; case serviceType = "service_type"; case priceNGN = "price_ngn"; case durationMinutes = "duration_minutes" }
}
struct Booking: Codable, Identifiable, Hashable {
    let id: String; let status: String; let startsAt: Date; let endsAt: Date?; let totalNGN: Int; let serviceID: String; let professionalID: String
    enum CodingKeys: String, CodingKey { case id,status; case startsAt = "starts_at"; case endsAt = "ends_at"; case totalNGN = "total_ngn"; case serviceID = "service_id"; case professionalID = "professional_id" }
}
struct BookingCreated: Codable { let id: String; let status: String; let totalNGN: Int; let conversationID: String; enum CodingKeys: String, CodingKey { case id,status; case totalNGN = "total_ngn"; case conversationID = "conversation_id" } }
struct Slot: Codable, Identifiable { let startsAt: Date; let endsAt: Date; var id: Date { startsAt }; enum CodingKeys:String,CodingKey { case startsAt="starts_at"; case endsAt="ends_at" } }
struct PaymentSession: Codable { let paymentID: String; let status: String; let amountNGN: Int; let checkoutURL: String?; let provider: String?; let message: String?; enum CodingKeys: String, CodingKey { case paymentID = "payment_id"; case status; case amountNGN = "amount_ngn"; case checkoutURL = "checkout_url"; case provider; case message } }
struct Conversation: Codable, Identifiable { let id: String; let bookingID: String?; enum CodingKeys: String, CodingKey { case id; case bookingID = "booking_id" } }
struct APIMessage: Codable, Identifiable { let id: String; let senderID: String; let body: String; let createdAt: Date; enum CodingKeys: String, CodingKey { case id; case senderID = "sender_id"; case body; case createdAt = "created_at" } }
struct TokenResponse: Codable { let accessToken: String; let refreshToken: String; enum CodingKeys: String, CodingKey { case accessToken = "access_token"; case refreshToken = "refresh_token" } }

struct CurrentUser: Codable { let id: String; let email: String?; let displayName: String; let role: String
    enum CodingKeys: String, CodingKey { case id,email; case displayName="display_name"; case role }
}
struct ProfessionalProfile: Codable { let id:String; let name:String; let headline:String?; let bio:String?; let yearsExperience:Int?; let serviceArea:String?; let verificationStatus:String; let averageRating:Double; let reviewCount:Int; let completedJobs:Int; let onboardingComplete:Bool
    enum CodingKeys:String,CodingKey { case id,name,headline,bio; case yearsExperience="years_experience"; case serviceArea="service_area"; case verificationStatus="verification_status"; case averageRating="average_rating"; case reviewCount="review_count"; case completedJobs="completed_jobs"; case onboardingComplete="onboarding_complete" }
}
struct ProfessionalDashboard: Codable { let pendingRequests:Int; let upcomingBookings:Int; let inProgress:Int; let completedJobs:Int; let earningsNGN:Int; let rating:Double; let reviewCount:Int
    enum CodingKeys:String,CodingKey { case pendingRequests="pending_requests"; case upcomingBookings="upcoming_bookings"; case inProgress="in_progress"; case completedJobs="completed_jobs"; case earningsNGN="earnings_ngn"; case rating; case reviewCount="review_count" }
}
struct ProfessionalRequest: Codable, Identifiable { let id:String; let startsAt:Date; let endsAt:Date?; let totalNGN:Int; let serviceID:String; let customerID:String; let customerNote:String?
    enum CodingKeys:String,CodingKey { case id; case startsAt="starts_at"; case endsAt="ends_at"; case totalNGN="total_ngn"; case serviceID="service_id"; case customerID="customer_id"; case customerNote="customer_note" }
}
struct AvailabilityWindow: Codable, Identifiable { let id:String; let weekday:Int; let startTime:String; let endTime:String
    enum CodingKeys:String,CodingKey { case id,weekday; case startTime="start_time"; case endTime="end_time" }
}

struct AIMatchResponse: Codable { let intent: AIIntent; let matches: [Professional] }
struct AIIntent: Codable { let category: String?; let text: String }
struct Project: Codable { let bookingID:String; let status:String; let title:String; let startsAt:Date; let endsAt:Date?; let updates:[ProjectUpdate]
    enum CodingKeys:String,CodingKey { case bookingID="booking_id",status,title,startsAt="starts_at",endsAt="ends_at",updates }
}
struct ProjectUpdate: Codable, Identifiable { let id:String; let title:String; let body:String; let status:String; let createdAt:Date
    enum CodingKeys:String,CodingKey { case id,title,body,status,createdAt="created_at" }
}
struct NotificationItem: Codable, Identifiable { let id:String; let title:String; let body:String; let type:String; let isRead:Bool; let createdAt:Date; let bookingID:String?
    enum CodingKeys:String,CodingKey { case id,title,body,type,isRead="is_read",createdAt="created_at",bookingID="booking_id" }
}
struct AIIntentResponse: Codable { let text:String; let category:String?; let budgetNGN:Int?; let constraints:[String:String]; let confidence:Double; let method:String
    enum CodingKeys:String,CodingKey { case text,category,budgetNGN="budget_ngn",constraints,confidence,method }
}
struct AttachmentItem: Codable, Identifiable { let id:String; let filename:String; let mimeType:String; let sizeBytes:Int; let createdAt:Date?; enum CodingKeys:String,CodingKey { case id,filename; case mimeType="mime_type"; case sizeBytes="size_bytes"; case createdAt="created_at" } }
struct ReviewItem: Codable, Identifiable { let id:String; let bookingID:String; let rating:Int; let body:String?; let createdAt:Date; enum CodingKeys:String,CodingKey { case id; case bookingID="booking_id"; case rating,body; case createdAt="created_at" } }
struct PaymentStatus: Codable { let paymentID:String; let status:String; let amountNGN:Int; let provider:String; enum CodingKeys:String,CodingKey { case paymentID="payment_id"; case status; case amountNGN="amount_ngn"; case provider } }
struct DisputeItem: Codable { let id:String; let status:String; let reason:String; let details:String; let resolution:String?; let createdAt:Date; enum CodingKeys:String,CodingKey { case id,status,reason,details,resolution; case createdAt="created_at" } }

struct PayoutBalance: Codable { let earnedNGN:Int; let paidOutNGN:Int; let availableNGN:Int; let minimumPayoutNGN:Int
    enum CodingKeys:String,CodingKey { case earnedNGN="earned_ngn", paidOutNGN="paid_out_ngn", availableNGN="available_ngn", minimumPayoutNGN="minimum_payout_ngn" }
}
struct PayoutItem: Codable, Identifiable { let id:String; let amountNGN:Int; let status:String; let provider:String; let providerReference:String?; let createdAt:Date; let paidAt:Date?
    enum CodingKeys:String,CodingKey { case id; case amountNGN="amount_ngn"; case status,provider; case providerReference="provider_reference"; case createdAt="created_at"; case paidAt="paid_at" }
}
struct VerificationSubmissionItem: Codable, Identifiable { let id:String; let documentType:String; let status:String; let reviewerNote:String?; let createdAt:Date; let reviewedAt:Date?
    enum CodingKeys:String,CodingKey { case id; case documentType="document_type"; case status; case reviewerNote="reviewer_note"; case createdAt="created_at"; case reviewedAt="reviewed_at" }
}

struct SavedProfessional: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let headline: String?
    let bio: String?
    let rating: Double
    let reviews: Int
    let verified: Bool
    let completedJobs: Int
    enum CodingKeys: String, CodingKey { case id,name,headline,bio,rating,reviews,verified; case completedJobs="completed_jobs" }
}

struct Recommendation: Codable, Identifiable, Hashable {
    let id: String; let name: String; let headline: String?; let bio: String?
    let rating: Double; let reviews: Int; let verified: Bool; let completedJobs: Int
    let reason: String; let score: Int
    enum CodingKeys: String, CodingKey { case id,name,headline,bio,rating,reviews,verified; case completedJobs="completed_jobs"; case reason,score }
}
