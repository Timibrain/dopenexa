import unittest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, insert, select

from app.models import Base, Booking, Payment, ProfessionalProfile, User
from app.routers.professionals import build_search_query


class ProfessionalDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, ProfessionalProfile.__table__, Booking.__table__, Payment.__table__],
        )
        self.active_user, self.active_profile = uuid4(), uuid4()
        self.inactive_user, self.inactive_profile = uuid4(), uuid4()
        self.incomplete_user, self.incomplete_profile = uuid4(), uuid4()
        self.retired_user, self.retired_profile = uuid4(), uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                insert(User),
                [
                    {"id": self.active_user, "display_name": "Active", "role": "professional", "is_active": True},
                    {"id": self.inactive_user, "display_name": "Inactive", "role": "professional", "is_active": False},
                    {"id": self.incomplete_user, "display_name": "Incomplete", "role": "professional", "is_active": True},
                    {"id": self.retired_user, "display_name": "Retired", "role": "professional", "is_active": False},
                ],
            )
            conn.execute(
                insert(ProfessionalProfile),
                [
                    {"id": self.active_profile, "user_id": self.active_user, "headline": "Active", "onboarding_complete": True},
                    {"id": self.inactive_profile, "user_id": self.inactive_user, "headline": "Inactive", "onboarding_complete": True},
                    {"id": self.incomplete_profile, "user_id": self.incomplete_user, "headline": "Incomplete", "onboarding_complete": False},
                    {"id": self.retired_profile, "user_id": self.retired_user, "headline": "Retired", "onboarding_complete": False},
                ],
            )
            booking_id = uuid4()
            service_id = uuid4()
            # A historical booking/payment must not make a retired profile discoverable.
            conn.execute(
                insert(Booking),
                {"id": booking_id, "customer_id": self.active_user, "professional_id": self.retired_profile,
                 "service_id": service_id, "status": "completed", "starts_at": datetime.now(timezone.utc), "total_ngn": 100},
            )
            conn.execute(
                insert(Payment),
                {"id": uuid4(), "booking_id": booking_id, "provider": "paystack", "status": "paid",
                 "amount_ngn": 100, "idempotency_key": str(uuid4())},
            )

    def tearDown(self):
        self.engine.dispose()

    def test_only_active_completed_profiles_are_discoverable(self):
        with self.engine.connect() as conn:
            rows = conn.execute(select(build_search_query().subquery())).all()
        profile_ids = {row[0] for row in rows}
        self.assertEqual(profile_ids, {self.active_profile})

    def test_existing_filters_remain_applied_to_discoverable_profiles(self):
        query = build_search_query(q="Active", min_rating=0, verified=False)
        sql = str(query.compile(self.engine))
        self.assertIn("users.is_active", sql)
        self.assertIn("professional_profiles.onboarding_complete", sql)
        self.assertIn("lower(professional_profiles.headline)", sql)


if __name__ == "__main__":
    unittest.main()
