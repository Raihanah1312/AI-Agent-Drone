"""Tahap 7C: tes adaptif tanpa OpenSky dan tanpa model AI.

Jalankan: python -m unittest test_adaptive_routes.py -v
"""
import json
import unittest
from datetime import datetime, timezone

from route_generator import (
    ADAPTIVE_BEND_FRACTIONS,
    ADAPTIVE_OFFSETS_M,
    generate_route_candidates,
    haversine_m,
)
from route_evaluator import evaluate_route_candidates

EPOCH = datetime(2026, 10, 29, 3, tzinfo=timezone.utc).timestamp()


def fake_cpa(plan, snapshot, *, source, departure_epoch,
             coverage_complete, cached):
    route_id = plan["mission"]["route_id"]
    # Contoh buatan untuk menguji ranking, bukan prediksi penerbangan asli.
    conflicts = 0 if route_id in {
        "RIGHT_1000_M_F30", "RIGHT_1500_M_F70",
    } else 1
    return {
        "analysis_status": "NO_CONFLICT_DETECTED" if conflicts == 0 else "POTENTIAL_CONFLICT",
        "data_quality_status": "COMPLETE_ANALYSIS" if coverage_complete else "INCOMPLETE_ANALYSIS",
        "potential_conflicts": conflicts,
        "route_coverage_complete": coverage_complete,
        "aircraft_received": 1,
        "aircraft_analyzed": 1,
        "aircraft_skipped": 0,
        "conflicts": [{"callsign": "MOCK"}] if conflicts else [],
        "closest_approaches": [],
    }


class AdaptiveRouteTests(unittest.TestCase):
    def create_group(self, **kwargs):
        return generate_route_candidates(
            -6.1754, 106.8272, -6.16, 106.85,
            departure_time_utc=datetime.fromtimestamp(EPOCH, timezone.utc),
            **kwargs,
        )

    def evaluate(self, analyzer=fake_cpa, **kwargs):
        return evaluate_route_candidates(
            snapshot={"time": EPOCH, "states": [["mock"]]},
            departure_epoch=EPOCH,
            analysis_fn=analyzer,
            **kwargs,
        )

    def test_thirty_candidates(self):
        report = self.create_group(
            offsets_m=ADAPTIVE_OFFSETS_M,
            bend_fractions=ADAPTIVE_BEND_FRACTIONS,
        )
        self.assertEqual(report["candidate_count"], 30)
        self.assertEqual(report["search_mode"], "ADAPTIVE")
        self.assertEqual(len(set(c["route_id"] for c in report["candidates"])), 30)
        self.assertEqual({c["bend_fraction"] for c in report["candidates"]}, {0.3, 0.5, 0.7})
        self.assertIn("LEFT_500_M_F30", {c["route_id"] for c in report["candidates"]})
        self.assertIn("RIGHT_2500_M_F70", {c["route_id"] for c in report["candidates"]})
        json.dumps(report)

    def test_fraction_changes_waypoint(self):
        group = self.create_group(offsets_m=[1000], bend_fractions=[0.3, 0.7])
        a = next(c for c in group["candidates"] if c["route_id"] == "LEFT_1000_M_F30")
        b = next(c for c in group["candidates"] if c["route_id"] == "LEFT_1000_M_F70")
        self.assertGreater(haversine_m(*a["bend_point"], *b["bend_point"]), 1000)
        for c in group["candidates"]:
            bend = c["bend_point"]
            self.assertTrue(any(
                abs(wp["latitude"] - bend[0]) < 1e-6 and
                abs(wp["longitude"] - bend[1]) < 1e-6
                for wp in c["flight_plan"]["waypoints"]
            ))

    def test_one_snapshot_and_departure_all_31(self):
        seen = []
        def analyzer(plan, snapshot, **kwargs):
            seen.append((id(snapshot), kwargs["departure_epoch"], plan["mission"]["start_time_utc"]))
            return fake_cpa(plan, snapshot, **kwargs)
        result = self.evaluate(
            analyzer,
            offsets_m=ADAPTIVE_OFFSETS_M,
            bend_fractions=ADAPTIVE_BEND_FRACTIONS,
        )
        self.assertEqual(result["candidate_count"], 30)
        self.assertEqual(len(seen), 31)
        self.assertEqual(len(set(seen)), 1)

    def test_ranking_only_eligible(self):
        result = self.evaluate(
            offsets_m=ADAPTIVE_OFFSETS_M,
            bend_fractions=ADAPTIVE_BEND_FRACTIONS,
        )
        self.assertEqual(result["eligible_candidate_count"], 2)
        self.assertEqual(result["recommended_route_id"], "RIGHT_1000_M_F30")
        self.assertEqual(result["status"], "RECOMMENDATION_AVAILABLE")

    def test_all_candidates_have_geojson(self):
        result = self.evaluate(
            offsets_m=ADAPTIVE_OFFSETS_M,
            bend_fractions=ADAPTIVE_BEND_FRACTIONS,
        )
        for c in result["candidates"]:
            coords = c["route_geojson"]["geometry"]["coordinates"]
            self.assertEqual(coords[0], [106.8272, -6.1754])
            self.assertEqual(coords[-1], [106.85, -6.16])

    def test_opensky_fetched_only_once_adaptive(self):
        calls = []
        def provider(*args):
            calls.append(args)
            return {"time": EPOCH, "states": [["mock"]]}, 0.0, 1, False
        result = evaluate_route_candidates(
            source="opensky", departure_epoch=EPOCH,
            analysis_fn=fake_cpa,
            snapshot_provider=provider,
            offsets_m=ADAPTIVE_OFFSETS_M,
            bend_fractions=ADAPTIVE_BEND_FRACTIONS,
        )
        self.assertEqual(result["candidate_count"], 30)
        self.assertEqual(len(calls), 1)

    def test_long_routes_not_auto_eligible_if_incomplete(self):
        def incomplete(plan, snapshot, **kwargs):
            result = fake_cpa(plan, snapshot, **kwargs)
            if plan["mission"]["route_id"] != "ORIGINAL":
                result["potential_conflicts"] = 0
                result["conflicts"] = []
                result["analysis_status"] = "INCOMPLETE_ANALYSIS"
                result["data_quality_status"] = "INCOMPLETE_ANALYSIS"
                result["route_coverage_complete"] = False
            return result
        report = self.evaluate(
            incomplete,
            offsets_m=ADAPTIVE_OFFSETS_M,
            bend_fractions=ADAPTIVE_BEND_FRACTIONS,
        )
        self.assertEqual(report["eligible_candidate_count"], 0)
        self.assertEqual(report["status"], "NO_ELIGIBLE_ALTERNATIVE")

    def test_reject_bad_fractions(self):
        for fractions in ([0.3, 0.3], [0.05], [], [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]):
            with self.subTest(fractions=fractions), self.assertRaises(ValueError):
                self.create_group(bend_fractions=fractions)

    def test_reject_too_many_candidates(self):
        with self.assertRaises(ValueError):
            self.create_group(offsets_m=range(1, 9), bend_fractions=[0.2, 0.3, 0.4, 0.5, 0.6])

    def test_legacy_behavior_still_six(self):
        group = self.create_group()
        self.assertEqual(group["candidate_count"], 6)
        self.assertEqual(group["candidates"][0]["route_id"], "LEFT_500_M")


if __name__ == "__main__":
    unittest.main()
