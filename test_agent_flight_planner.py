"""Run from project root: python -m unittest test_agent_flight_planner.py -v"""
import json
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_flight_planner import run_agent_flight_planner, parse_action
from agent_planner_api import router

SNAPSHOT = {"time": 1793280200, "states": [{"callsign": "DEMO-CROSS"}, {"callsign": "DEMO-HIGH"}]}


def fake_cpa(plan, snapshot, **kwargs):
    assert snapshot is SNAPSHOT
    alt = plan['mission']['altitude_m']
    departure = kwargs['departure_epoch']
    # Different testing scenarios according to explicit attributes.
    zeros = alt >= 500 or departure >= 1793280200 + 120 or plan['mission']['route_id'].startswith('HERMES_ROUTE')
    conflict = [] if zeros else [dict(callsign='DEMO-CROSS', horizontal_cpa_m=100., vertical_separation_m=0., time_to_cpa_s=145.)]
    return {
        'potential_conflicts': len(conflict), 'conflicts': conflict,
        'aircraft_received': 2, 'aircraft_analyzed': 2, 'aircraft_skipped': 0,
        'analysis_status': 'NO_CONFLICT_DETECTED' if zeros else 'POTENTIAL_CONFLICT',
        'data_quality_status': 'COMPLETE_ANALYSIS',
        'route_coverage_complete': kwargs['coverage_complete'],
    }


def fail_cpa(plan, snapshot, **kwargs):
    return dict(potential_conflicts=1, conflicts=[dict(callsign='DEMO-CROSS',horizontal_cpa_m=100.,vertical_separation_m=0.)],
                aircraft_received=2,aircraft_analyzed=2,aircraft_skipped=0,
                analysis_status='POTENTIAL_CONFLICT',data_quality_status='COMPLETE_ANALYSIS',route_coverage_complete=True)


def call(actions, **kwargs):
    iterator = iter(actions)
    llm_calls = []
    def llm(system, user):
        llm_calls.append(user)
        return next(iterator)
    result = run_agent_flight_planner(epoch=1793280200, snapshot=SNAPSHOT,
        llm_fn=llm, analysis_fn=kwargs.pop('analysis_fn', fake_cpa), **kwargs)
    return result, llm_calls


class ParseTest(unittest.TestCase):
    def test_prompt_explicitly_forbids_native_tools(self):
        from agent_flight_planner import SYSTEM_PROMPT, _make_prompt
        self.assertIn('JANGAN menggunakan tools bawaan Hermes', SYSTEM_PROMPT)
        self.assertIn('BUKAN tool yang', SYSTEM_PROMPT)
        baseline = dict(route_id='ORIGINAL', potential_conflicts=1,
            analysis_status='POTENTIAL_CONFLICT', data_quality_status='COMPLETE_ANALYSIS',
            route_coverage_complete=True, cpa_candidate_eligible=False,
            distance_m=100, duration_s=10, conflicts=[])
        config = dict(max_steps=3, reference_plan={'altitude_m':150})
        msg = _make_prompt(baseline, [], config, 1, ['evaluate_altitude'])
        self.assertIn('JANGAN menjalankan tool bawaan Hermes', msg)
        self.assertIn('allowed_tools', msg)

    def test_fenced_json(self):
        out=parse_action('```json\n{"tool":"evaluate_delay","arguments":{"delay_s":120}}\n```')
        self.assertEqual(out['tool'], 'evaluate_delay')
    def test_prose_wrapped_json(self):
        self.assertEqual(parse_action('Usulan:\n{"tool":"finish","arguments":{}}')['tool'], 'finish')
    def test_unknown_tool_rejected(self):
        with self.assertRaises(ValueError): parse_action('{"tool":"delete_files"}')
    def test_not_json_rejected(self):
        with self.assertRaises(ValueError): parse_action('Tidak perlu apa-apa')


class PlannerTest(unittest.TestCase):
    def test_altitude_proposal_gets_evaluated(self):
        result, calls=call(['{"tool":"evaluate_altitude","arguments":{"altitude_m":550},"reason":"vertical"}'])
        self.assertEqual(result['status'],'MITIGATION_CPA_CANDIDATE_FOUND')
        self.assertEqual(result['recommended_action']['altitude_m'],550)
        self.assertTrue(result['recommended_action']['cpa_candidate_eligible'])
        self.assertEqual(len(calls),1)
    def test_delay_shifts_epoch_and_can_work(self):
        result,_=call(['{"tool":"evaluate_delay","arguments":{"delay_s":120}}'])
        self.assertEqual(result['recommended_action']['delay_s'],120)
        self.assertEqual(result['recommended_action']['extra_duration_s'],120)
    def test_route_from_offset(self):
        result,_=call(['{"tool":"evaluate_route","arguments":{"side":"right","offset_m":800,"bend_fraction":0.3}}'])
        choice=result['recommended_action']
        self.assertEqual(len(choice['control_points']),3)
        self.assertEqual(choice['route_geojson']['geometry']['type'],'LineString')
        self.assertGreater(choice['extra_distance_m'],0)
    def test_route_from_waypoint(self):
        result,_=call(['{"tool":"evaluate_route","arguments":{"waypoints":[[-6.17,106.84]]}}'])
        self.assertEqual(result['recommended_action']['tool'],'evaluate_route')
    def test_unsafe_waypoint_rejected_and_feedback(self):
        result,calls=call([
          '{"tool":"evaluate_route","arguments":{"waypoints":[[-6.8,107.6]]}}',
          '{"tool":"evaluate_altitude","arguments":{"altitude_m":550}}'
        ])
        self.assertEqual(result['attempts'][0]['outcome'],'REJECTED')
        self.assertIn('Waypoint', result['attempts'][0]['error'])
        self.assertIn('previous_tool_results', calls[1])
        self.assertTrue(result['attempts'][1]['cpa_candidate_eligible'])
    def test_bad_altitude_rejected(self):
        result,_=call(['{"tool":"evaluate_altitude","arguments":{"altitude_m":4000}}'],max_steps=1)
        self.assertEqual(result['attempts'][0]['outcome'],'REJECTED')
        self.assertIsNone(result['recommended_action'])
    def test_repeat_proposal_requires_new_strategy(self):
        result,calls=call([
          '{"tool":"evaluate_altitude","arguments":{"altitude_m":200}}',
          '{"tool":"evaluate_altitude","arguments":{"altitude_m":200}}',
          '{"tool":"evaluate_delay","arguments":{"delay_s":120}}',
          '{"tool":"finish","arguments":{}}'
        ],analysis_fn=fail_cpa)
        self.assertEqual(result['attempts'][0]['tool'],'evaluate_altitude')
        self.assertEqual(result['attempts'][1]['tool'],'evaluate_delay')
        self.assertEqual(len(calls),4)
        self.assertIn('PERBAIKI USULAN',calls[2])
        self.assertEqual(result['status'],'NO_ELIGIBLE_MITIGATION')
    def test_no_eligible_not_fabricated(self):
        result,_=call(['{"tool":"evaluate_altitude","arguments":{"altitude_m":200}}',
                       '{"tool":"finish","arguments":{}}'],analysis_fn=fail_cpa)
        self.assertEqual(result['status'],'NO_ELIGIBLE_MITIGATION')
        self.assertIsNone(result['recommended_action'])
    def test_step_cap(self):
        with self.assertRaises(ValueError): call([],max_steps=5)
    def test_single_snapshot_provider(self):
        calls=[]
        def provider(lat,lon,radius):
            calls.append((lat,lon,radius))
            return SNAPSHOT,None,None,False
        run_agent_flight_planner(source='opensky',epoch=1793280200,snapshot_provider=provider,
          llm_fn=lambda *_: '{"tool":"evaluate_altitude","arguments":{"altitude_m":550}}',
          analysis_fn=fake_cpa)
        self.assertEqual(len(calls),1)
    def test_insufficient_scan_coverage_not_eligible(self):
        result,_=call(['{"tool":"evaluate_altitude","arguments":{"altitude_m":550}}'],radius_km=149)
        self.assertFalse(result['geographic_coverage_complete'])
        self.assertFalse(result['attempts'][0]['cpa_candidate_eligible'])
    def test_no_recommendation_for_baseline_clean(self):
        def clean(plan,snapshot,**kw):
            data=fake_cpa(plan,snapshot,**kw)
            data['potential_conflicts']=0;data['conflicts']=[];data['analysis_status']='NO_CONFLICT_DETECTED'
            return data
        result, calls=call([],analysis_fn=clean)
        self.assertEqual(result['status'],'NO_MITIGATION_NEEDED')
        self.assertEqual(len(calls),0)


class ApiTest(unittest.TestCase):
    def test_endpoint_routing(self):
        app=FastAPI();app.include_router(router)
        with patch('agent_planner_api.run_agent_flight_planner',return_value={'status':'NO_ELIGIBLE_MITIGATION','attempts':[]}):
            response=TestClient(app).post('/api/agent-plan',json={
                'start_lat':-6.1754,'start_lon':106.8272,'end_lat':-6.16,'end_lon':106.85,
                'altitude_m':150,'speed_mps':10,'time_step_s':30,'radius_km':70,'source':'demo'})
        self.assertEqual(response.status_code,200)
    def test_invalid_steps_422(self):
        app=FastAPI();app.include_router(router)
        response=TestClient(app).post('/api/agent-plan',json={
                'start_lat':-6.1754,'start_lon':106.8272,'end_lat':-6.16,'end_lon':106.85,
                'altitude_m':150,'speed_mps':10,'time_step_s':30,'radius_km':70,'max_steps':999})
        self.assertEqual(response.status_code,422)


if __name__=='__main__': unittest.main()
