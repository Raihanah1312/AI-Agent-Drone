"""Uji sederhana route_generator.py tanpa OpenSky / Hermes."""

import json
import unittest
from datetime import datetime, timezone

from route_generator import (
    build_route_flight_plan,
    generate_route_candidates,
    haversine_m,
)


class RouteGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.data = generate_route_candidates(
            -6.1754, 106.8272, -6.16, 106.85,
            altitude_m=150, speed_mps=10, time_step_s=30,
            departure_time_utc=datetime(2026, 10, 29, tzinfo=timezone.utc),
        )

    def test_six_candidates(self):
        self.assertEqual(self.data["candidate_count"], 6)
        self.assertEqual(len(self.data["candidates"]), 6)
        self.assertEqual({c["side"] for c in self.data["candidates"]}, {"left", "right"})

    def test_all_candidates_longer_than_original(self):
        base = self.data["original_route"]["mission"]["distance_m"]
        for candidate in self.data["candidates"]:
            self.assertGreater(candidate["distance_m"], base)
            self.assertGreater(candidate["extra_duration_s"], 0)
            self.assertEqual(candidate["evaluation_status"], "NOT_EVALUATED")

    def test_bend_point_is_waypoint(self):
        for c in self.data["candidates"]:
            bend = c["bend_point"]
            points = c["flight_plan"]["waypoints"]
            self.assertTrue(any(
                abs(p["latitude"] - bend[0]) < 1e-6
                and abs(p["longitude"] - bend[1]) < 1e-6
                for p in points
            ))
            times = [p["elapsed_s"] for p in points]
            self.assertTrue(all(b > a for a, b in zip(times, times[1:])))

    def test_departure_identical(self):
        ref = self.data["original_route"]["mission"]["start_time_utc"]
        for c in self.data["candidates"]:
            self.assertEqual(c["flight_plan"]["mission"]["start_time_utc"], ref)
        json.dumps(self.data)

    def test_offset_and_direction(self):
        left = next(c for c in self.data["candidates"] if c["route_id"] == "LEFT_500_M")
        right = next(c for c in self.data["candidates"] if c["route_id"] == "RIGHT_500_M")
        self.assertGreater(haversine_m(*left["bend_point"], *right["bend_point"]), 990)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            build_route_flight_plan([(-6.17, 106.8), (-6.17, 106.8)])
        with self.assertRaises(ValueError):
            generate_route_candidates(-6.1, 106.8, -6.0, 106.9, speed_mps=0)


if __name__ == "__main__":
    unittest.main()
