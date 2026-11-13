"""Pengujian Route Evaluator tanpa koneksi OpenSky / API berbayar.

Jalankan dari folder utama:
    python -m unittest test_route_evaluator.py -v
"""

import unittest
from datetime import datetime, timezone
from route_evaluator import evaluate_route_candidates

FIXED_EPOCH = datetime(2026, 10, 29, 2, 0, tzinfo=timezone.utc).timestamp()


def snapshot(epoch=FIXED_EPOCH):
    return {"time": int(epoch), "states": [["demo-aircraft"]]}


def fake_analyzer(conflicts_by_id, incomplete_ids=(), analyze_records=None):
    incomplete_ids = set(incomplete_ids)

    def _analyze(plan, data, *, source, departure_epoch, coverage_complete, cached):
        name = plan["mission"]["route_id"]
        if analyze_records is not None:
            analyze_records.append({
                "route_id": name,
                "snapshot": data,
                "epoch": departure_epoch,
                "start": plan["mission"]["start_time_utc"],
                "coverage": coverage_complete,
            })
        conflicts = conflicts_by_id.get(name, 1)
        incomplete = name in incomplete_ids or not coverage_complete
        status = ("POTENTIAL_CONFLICT" if conflicts > 0 else
                  "INCOMPLETE_ANALYSIS" if incomplete else "NO_CONFLICT_DETECTED")
        return {
            "potential_conflicts": conflicts,
            "analysis_status": status,
            "data_quality_status": "INCOMPLETE_ANALYSIS" if incomplete else "COMPLETE_ANALYSIS",
            "route_coverage_complete": coverage_complete,
            "aircraft_received": 1,
            "aircraft_analyzed": 1,
            "aircraft_skipped": 0,
            "conflicts": [{"callsign": "DEMO"}] * conflicts,
            "closest_approaches": [],
        }

    return _analyze


class EvaluatorTests(unittest.TestCase):
    def evaluate(self, fn, **kwargs):
        return evaluate_route_candidates(
            snapshot=snapshot(), departure_epoch=FIXED_EPOCH,
            analysis_fn=fn, **kwargs
        )

    def test_best_zero_conflict_by_shortest_detour(self):
        result = self.evaluate(fake_analyzer({
            "ORIGINAL": 1, "LEFT_1000_M": 0, "RIGHT_1500_M": 0,
        }))
        self.assertEqual(result["status"], "RECOMMENDATION_AVAILABLE")
        self.assertEqual(result["recommended_route_id"], "LEFT_1000_M")
        self.assertEqual(result["eligible_candidate_count"], 2)

    def test_six_candidates_and_geojson_order(self):
        result = self.evaluate(fake_analyzer({"ORIGINAL": 1}))
        self.assertEqual(result["candidate_count"], 6)
        route = result["candidates"][0]
        coords = route["route_geojson"]["geometry"]["coordinates"]
        self.assertEqual(coords[0], [106.8272, -6.1754])
        self.assertEqual(coords[-1], [106.85, -6.16])
        self.assertGreater(len(route["flight_plan"]["waypoints"]), 2)

    def test_no_candidate_when_all_conflict(self):
        result = self.evaluate(fake_analyzer({"ORIGINAL": 1}))
        self.assertEqual(result["status"], "NO_ELIGIBLE_ALTERNATIVE")
        self.assertIsNone(result["recommended_route"])
        self.assertEqual(result["eligible_candidate_count"], 0)

    def test_incomplete_zero_conflict_is_not_recommended(self):
        fn = fake_analyzer({"ORIGINAL": 1, "LEFT_500_M": 0}, ["LEFT_500_M"])
        result = self.evaluate(fn)
        self.assertEqual(result["status"], "NO_ELIGIBLE_ALTERNATIVE")
        self.assertIsNone(result["recommended_route_id"])
        candidate = next(c for c in result["candidates"] if c["route_id"] == "LEFT_500_M")
        self.assertEqual(candidate["evaluation_status"], "INCOMPLETE_ANALYSIS")

    def test_no_need_to_reroute_when_baseline_complete_zero(self):
        fn = fake_analyzer({"ORIGINAL": 0, "RIGHT_1500_M": 0})
        result = self.evaluate(fn)
        self.assertEqual(result["status"], "NO_REROUTE_NEEDED")
        self.assertIsNone(result["recommended_route_id"])

    def test_baseline_incomplete_blocks_recommendation(self):
        fn = fake_analyzer({"ORIGINAL": 1, "LEFT_500_M": 0}, ["ORIGINAL"])
        result = self.evaluate(fn)
        self.assertEqual(result["status"], "BASELINE_INCOMPLETE")
        self.assertIsNone(result["recommended_route_id"])

    def test_same_snapshot_and_departure_for_seven_routes(self):
        records = []
        fn = fake_analyzer({"ORIGINAL": 1}, analyze_records=records)
        self.evaluate(fn)
        self.assertEqual(len(records), 7)
        self.assertEqual(len({id(r["snapshot"]) for r in records}), 1)
        self.assertEqual(len({r["epoch"] for r in records}), 1)
        self.assertEqual(len({r["start"] for r in records}), 1)
        self.assertEqual(records[0]["epoch"], FIXED_EPOCH)

    def test_demo_builder_called_once(self):
        call_count = []

        def builder(plan, epoch):
            call_count.append((plan["mission"]["route_id"], epoch))
            return snapshot(epoch)

        result = evaluate_route_candidates(
            source="demo", departure_epoch=FIXED_EPOCH,
            analysis_fn=fake_analyzer({"ORIGINAL": 1}),
            demo_builder=builder,
        )
        self.assertEqual(result["aircraft_snapshot_count"], 1)
        self.assertEqual(call_count, [("ORIGINAL", FIXED_EPOCH)])

    def test_opensky_fetch_only_once(self):
        calls = []

        def provider(lat, lon, radius):
            calls.append((lat, lon, radius))
            return snapshot(), 0.0, 1, False

        evaluate_route_candidates(
            source="opensky", departure_epoch=FIXED_EPOCH,
            analysis_fn=fake_analyzer({"ORIGINAL": 1}),
            snapshot_provider=provider,
        )
        self.assertEqual(len(calls), 1)
        self.assertGreater(calls[0][2], 70)
        self.assertLessEqual(calls[0][2], 150)

    def test_incomplete_geographic_coverage_blocks_recommendation(self):
        result = self.evaluate(
            fake_analyzer({"ORIGINAL": 1, "LEFT_500_M": 0}),
            radius_km=150,
        )
        self.assertFalse(result["geographic_coverage_complete"])
        self.assertEqual(result["status"], "BASELINE_INCOMPLETE")
        self.assertIsNone(result["recommended_route"])

    def test_bad_radius_rejected(self):
        with self.assertRaises(ValueError):
            self.evaluate(fake_analyzer({"ORIGINAL": 1}), radius_km=200)


if __name__ == "__main__":
    unittest.main()
