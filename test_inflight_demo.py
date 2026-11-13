"""Unit test untuk skenario Demo yang tidak di-reset setiap pemindaian.

Jalankan dari folder utama proyek:
    python -m unittest test_inflight_demo.py -v

Mode ini hanya SIMULASI, tanpa perlu koneksi OpenSky.
"""
import unittest
from datetime import datetime, timezone

from config import HORIZONTAL_THRESHOLD_M, VERTICAL_THRESHOLD_M
from flight_plan import generate_flight_plan
from inflight_cpa_service import make_persistent_demo_snapshot, analyze_inflight
from cpa_api_service import interpolate_waypoint
from simulator import haversine_km


class PersistentDemoTests(unittest.TestCase):
    def setUp(self):
        self.plan = generate_flight_plan()
        self.duration = float(self.plan["mission"]["duration_s"])
        self.epoch = datetime.now(timezone.utc).timestamp()

    def test_demo_aircraft_moves_over_simulation_time(self):
        first = make_persistent_demo_snapshot(self.plan, 0.0, self.epoch)
        later = make_persistent_demo_snapshot(self.plan, self.duration / 2, self.epoch)
        self.assertEqual(first["states"][0][0], later["states"][0][0])
        self.assertNotAlmostEqual(first["states"][0][5], later["states"][0][5], places=6)

    def test_same_elapsed_reproducible(self):
        a = make_persistent_demo_snapshot(self.plan, 100.0, self.epoch)
        b = make_persistent_demo_snapshot(self.plan, 100.0, self.epoch + 40)
        self.assertAlmostEqual(a["states"][0][5], b["states"][0][5], places=9)
        self.assertAlmostEqual(a["states"][0][6], b["states"][0][6], places=9)

    def test_demo_aircraft_crosses_at_midpoint(self):
        t = self.duration / 2
        snapshot = make_persistent_demo_snapshot(self.plan, t, self.epoch)
        aircraft = snapshot["states"][0]
        drone = interpolate_waypoint(self.plan["waypoints"], t)
        distance_m = haversine_km(
            aircraft[6], aircraft[5], drone["latitude"], drone["longitude"]
        ) * 1000
        self.assertLess(distance_m, 15.0)

    def test_late_conflicts_follow_configured_separation(self):
        before = analyze_inflight(self.plan, 0, source="demo")
        late = analyze_inflight(self.plan, self.duration * 0.96, source="demo")
        self.assertGreaterEqual(before["potential_conflicts"], 1)
        self.assertEqual(late["potential_conflicts"], len(late["conflicts"]))
        for conflict in late["conflicts"]:
            self.assertLessEqual(conflict["horizontal_cpa_m"], HORIZONTAL_THRESHOLD_M)
            self.assertLessEqual(conflict["vertical_separation_m"], VERTICAL_THRESHOLD_M)
        self.assertEqual(late["aircraft_analyzed"], 2)
        self.assertIn("analysis_generated_at_utc", late)


if __name__ == "__main__":
    unittest.main()
