import unittest
from datetime import datetime, timezone
from app.synop import round_to_nearest_utc_hour, build_section_0

class SynopSection0Tests(unittest.TestCase):
    def test_round_down_before_half_hour(self):
        dt = datetime(2026, 10, 12, 19, 29, tzinfo=timezone.utc)
        self.assertEqual(round_to_nearest_utc_hour(dt), datetime(2026, 10, 12, 19, 0, tzinfo=timezone.utc))

    def test_round_up_at_half_hour(self):
        dt = datetime(2026, 10, 12, 19, 30, tzinfo=timezone.utc)
        self.assertEqual(round_to_nearest_utc_hour(dt), datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc))

    def test_round_crosses_day(self):
        dt = datetime(2026, 10, 12, 23, 40, tzinfo=timezone.utc)
        self.assertEqual(build_section_0(dt, "4"), "AAXX 13004 87016")

    def test_rejects_invalid_iw(self):
        with self.assertRaises(ValueError):
            build_section_0(datetime(2026, 10, 12, 12, tzinfo=timezone.utc), "2")

if __name__ == "__main__":
    unittest.main()
