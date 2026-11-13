import unittest
from cpa_visualization import attach_conflict_geometry


class CpaVisualizationTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            "mission": {"duration_s": 100.0, "altitude_m": 150},
            "waypoints": [
                {"elapsed_s": 0.0, "latitude": -6.2, "longitude": 106.8, "altitude_m": 150},
                {"elapsed_s": 50.0, "latitude": -6.19, "longitude": 106.81, "altitude_m": 150},
                {"elapsed_s": 100.0, "latitude": -6.18, "longitude": 106.82, "altitude_m": 150},
            ],
        }
        self.epoch = 1761700000.0
        self.snapshot = {
            "time": int(self.epoch),
            "states": [
                ["abc123", "DEMO-CROSS", "SIM", self.epoch, self.epoch,
                 106.8, -6.19, 150.0, False, 30.0, 90.0],
            ],
        }
        self.conflict = {
            "icao24": "abc123", "callsign": "DEMO-CROSS",
            "time_to_cpa_s": 50.0, "horizontal_cpa_m": 500.0,
            "vertical_separation_m": 0.0, "potential_conflict": True,
        }

    def test_geometry_for_conflict(self):
        result = attach_conflict_geometry(
            {"conflicts": [self.conflict]}, self.plan, self.snapshot, self.epoch
        )
        visual = result["conflict_visualizations"]
        self.assertEqual(len(visual), 1)
        self.assertEqual(visual[0]["icao24"], "abc123")
        self.assertAlmostEqual(visual[0]["drone_at_cpa"]["latitude"], -6.19)
        self.assertAlmostEqual(visual[0]["drone_at_cpa"]["longitude"], 106.81)
        self.assertGreaterEqual(len(visual[0]["predicted_track_lonlat"]), 2)

    def test_no_conflict_no_geometry(self):
        result = attach_conflict_geometry(
            {"conflicts": []}, self.plan, self.snapshot, self.epoch
        )
        self.assertEqual(result["conflict_visualizations"], [])

    def test_skip_invalid_position_time(self):
        snapshot = {"states": [list(self.snapshot["states"][0])]}
        snapshot["states"][0][3] = None
        result = attach_conflict_geometry(
            {"conflicts": [self.conflict]}, self.plan, snapshot, self.epoch
        )
        self.assertEqual(result["conflict_visualizations"], [])

    def test_inflight_remaining_route(self):
        # Untuk inflight, time_s dihitung dari awal sisa rute (bukan awal misi asli).
        remaining = {
            "mission": {"duration_s": 40, "altitude_m": 150},
            "waypoints": [
                {"elapsed_s": 0, "latitude": -6.19, "longitude": 106.81, "altitude_m": 150},
                {"elapsed_s": 40, "latitude": -6.18, "longitude": 106.82, "altitude_m": 150},
            ],
        }
        c = dict(self.conflict, time_to_cpa_s=20.0)
        result = attach_conflict_geometry(
            {"conflicts": [c]}, remaining, self.snapshot, self.epoch
        )
        self.assertEqual(len(result["conflict_visualizations"]), 1)
        self.assertAlmostEqual(result["conflict_visualizations"][0]["drone_at_cpa"]["latitude"], -6.185)


if __name__ == "__main__":
    unittest.main()
