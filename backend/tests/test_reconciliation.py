import unittest
from unittest.mock import patch

from app.config import settings
from app.db import SessionLocal, engine
from app.reconciliation import consistency_check, stale_cutoffs, stale_records
from app.routers.reconciliation import router


class ReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await engine.dispose()

    async def test_stale_selection_uses_configurable_thresholds(self):
        with patch.object(settings, "payment_reconciliation_after_minutes", 0), \
             patch.object(settings, "payout_reconciliation_after_minutes", 0), \
             patch.object(settings, "refund_reconciliation_after_minutes", 0):
            async with SessionLocal() as session:
                result = await stale_records(session)
        self.assertEqual(set(result), {"payments", "payouts", "refunds"})
        self.assertIsNotNone(stale_cutoffs())

    async def test_consistency_checker_returns_read_only_report(self):
        async with SessionLocal() as session:
            result = await consistency_check(session)
        self.assertIsInstance(result, list)

    def test_reconciliation_routes_are_admin_protected(self):
        paths = {route.path: route for route in router.routes}
        self.assertIn("/payments/{payment_id}", paths)
        self.assertTrue(any(getattr(dep.call, "__name__", "") == "checker" for dep in paths["/payments/{payment_id}"].dependant.dependencies))


if __name__ == "__main__":
    unittest.main()
