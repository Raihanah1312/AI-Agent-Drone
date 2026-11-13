"""Unit tests for Stage 8C flight plan build and In-Flight Hermes explanation."""
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from simulation_plan import build_simulation_plan
from inflight_advisor_api import router

BASE = dict(start_lat=-6.1754, start_lon=106.8272,
            end_lat=-6.16, end_lon=106.85,
            altitude_m=150, speed_mps=10, time_step_s=30)
T0 = datetime(2026, 10, 29, 13, 0, tzinfo=timezone.utc)

class SimulationPlanTest(TestCase):
    def make(self, **kw):
        return build_simulation_plan(**BASE, reference_time=T0, **kw)

    def test_original_plan_points(self):
        data = self.make()
        self.assertEqual(data['mission']['delay_s'], 0)
        self.assertEqual(len(data['mission']['control_points']), 2)
        self.assertAlmostEqual(data['mission']['duration_s'], 304.72, places=0)

    def test_route_waypoint_present_in_active_plan(self):
        bend = [-6.17, 106.84]
        data = self.make(control_points=[[BASE['start_lat'], BASE['start_lon']], bend,
                                                [BASE['end_lat'], BASE['end_lon']]])
        self.assertEqual(len(data['mission']['control_points']), 3)
        self.assertTrue(any(abs(p['latitude']-bend[0]) < .000001 and
                            abs(p['longitude']-bend[1]) < .000001 for p in data['waypoints']))

    def test_altitude_every_waypoint(self):
        data = build_simulation_plan(**{**BASE, 'altitude_m': 550}, reference_time=T0)
        self.assertTrue(all(p['altitude_m'] == 550 for p in data['waypoints']))
        self.assertIn('tidak dimodelkan', data['mission']['altitude_profile_note'])

    def test_delay_holds_drone_at_start(self):
        data = self.make(delay_s=120)
        self.assertEqual(data['waypoints'][0]['elapsed_s'], 0)
        self.assertEqual(data['waypoints'][1]['elapsed_s'], 120)
        self.assertEqual(data['waypoints'][0]['latitude'], data['waypoints'][1]['latitude'])
        self.assertEqual(data['waypoints'][0]['longitude'], data['waypoints'][1]['longitude'])
        self.assertAlmostEqual(data['mission']['duration_s'], 424.72, places=0)
        self.assertEqual(data['mission']['travel_duration_s'], 304.72)

    def test_reject_mismatched_endpoints(self):
        with self.assertRaisesRegex(ValueError, 'sesuai Mission Planner'):
            self.make(control_points=[[0, 0],[-6.17,106.84],[-6.16,106.85]])

    def test_reject_long_route(self):
        with self.assertRaises(ValueError):
            self.make(control_points=[[-6.1754,106.8272],[-6.11,106.81],[-6.16,106.85]])

    def test_reject_delay_over_limit(self):
        with self.assertRaises(ValueError): self.make(delay_s=500)

    def test_reject_prediction_over_horizon(self):
        with self.assertRaisesRegex(ValueError, '600'):
            self.make(control_points=[[-6.1754,106.8272],[-6.15,106.8272],[-6.16,106.85]],delay_s=240)


class InFlightAiTest(TestCase):
    def setUp(self):
        app=FastAPI(); app.include_router(router)
        self.client=TestClient(app)
        self.payload=dict(source='opensky', analysis_status='POTENTIAL_CONFLICT',
            data_quality_status='INCOMPLETE_ANALYSIS', potential_conflicts=1,
            aircraft_received=22, aircraft_analyzed=14, aircraft_skipped=8,
            simulation_elapsed_s=40, remaining_duration_s=265,
            conflicts=[dict(callsign='TEST',horizontal_cpa_m=800,
                            vertical_separation_m=50,time_to_cpa_s=20)])

    def test_only_explanation_no_control(self):
        with patch('inflight_advisor_api.ask_hermes',return_value='Potensi konflik perlu dievaluasi.') as llm:
            response=self.client.post('/api/inflight-advice',json=self.payload)
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertTrue(data['simulation_only'])
        self.assertEqual(data['facts']['aircraft_skipped'],8)
        self.assertNotIn('control_points',data)
        self.assertIn('Potensi',data['advice'])
        self.assertEqual(llm.call_count,1)

    def test_no_conflict_doesnt_call_llm(self):
        with patch('inflight_advisor_api.ask_hermes') as llm:
            response=self.client.post('/api/inflight-advice',json={**self.payload,'potential_conflicts':0})
        self.assertEqual(response.status_code,200)
        llm.assert_not_called()

    def test_reject_invalid_fact(self):
        response=self.client.post('/api/inflight-advice',json={**self.payload, 'aircraft_skipped': -1})
        self.assertEqual(response.status_code,422)
