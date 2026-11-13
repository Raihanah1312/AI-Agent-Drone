"""Construct a simulation-only mission from approved *what-if* parameters.

Supports waypoint geometry, constant-altitude scenarios and a departure hold.
CPA MUST be re-run on the constructed mission; this builder does not certify it.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from route_generator import build_route_flight_plan, haversine_m

MAX_EXTRA_DISTANCE_M = 4000.0
MAX_DELAY_S = 240.0
MAX_PREDICTION_S = 600.0


def build_simulation_plan(*, start_lat, start_lon, end_lat, end_lon,
                          altitude_m, speed_mps, time_step_s,
                          control_points=None, delay_s=0, route_id='SIMULATION',
                          reference_time=None):
    """Build mission and optional stationary initial hold, from validated inputs."""
    start, end = [float(start_lat), float(start_lon)], [float(end_lat), float(end_lon)]
    if control_points is None:
        points = [start, end]
    else:
        if not isinstance(control_points, list) or not 2 <= len(control_points) <= 4:
            raise ValueError('control_points harus berisi titik awal, 0–2 waypoint, titik tujuan')
        points = []
        for item in control_points:
            if not isinstance(item, list) or len(item) != 2 or any(isinstance(v, bool) for v in item):
                raise ValueError('Setiap control point harus [latitude, longitude]')
            lat, lon = float(item[0]), float(item[1])
            if not (math.isfinite(lat) and math.isfinite(lon)):
                raise ValueError('Koordinat harus bernilai finite')
            points.append([lat, lon])
        if haversine_m(*points[0], *start) > 2 or haversine_m(*points[-1], *end) > 2:
            raise ValueError('Awal dan tujuan control_points harus sesuai Mission Planner')
    delay_s = float(delay_s)
    if not math.isfinite(delay_s) or not 0 <= delay_s <= MAX_DELAY_S:
        raise ValueError('delay_s harus 0–240 detik')
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    if isinstance(reference_time, str):
        reference_time = datetime.fromisoformat(reference_time.replace('Z', '+00:00'))
    if reference_time.tzinfo is None:
        raise ValueError('reference_time harus memiliki zona waktu')
    reference_time = reference_time.astimezone(timezone.utc)

    flight = build_route_flight_plan(points, altitude_m, speed_mps, time_step_s,
                                    reference_time + timedelta(seconds=delay_s), route_id)
    direct = haversine_m(*start, *end)
    if flight['mission']['distance_m'] > direct + MAX_EXTRA_DISTANCE_M + 3:
        raise ValueError('Rute melebihi maksimum tambahan 4 km')
    if flight['mission']['duration_s'] + delay_s > MAX_PREDICTION_S:
        raise ValueError('Durasi termasuk penundaan melebihi horizon 600 detik')

    travel_duration = float(flight['mission']['duration_s'])
    flight['mission']['travel_duration_s'] = travel_duration
    flight['mission']['delay_s'] = delay_s
    flight['mission']['reference_start_time_utc'] = reference_time.isoformat()
    flight['mission']['operational_validation'] = 'NOT_EVALUATED'
    flight['mission']['altitude_profile_note'] = (
        'Ketinggian konstan sejak mulai perjalanan; proses lepas landas/climb tidak dimodelkan.'
    )

    if delay_s:
        # At t=0–delay drone stays at start. Subsequent samples keep their original
        # time_utc (already delayed); only elapsed_s shifts.
        shifted = [{**sample, 'step': index + 1,
                    'elapsed_s': round(float(sample['elapsed_s']) + delay_s, 2)}
                   for index, sample in enumerate(flight['waypoints'])]
        hold = {
            'step': 0, 'time_utc': reference_time.isoformat(), 'elapsed_s': 0.0,
            'latitude': shifted[0]['latitude'], 'longitude': shifted[0]['longitude'],
            'altitude_m': shifted[0]['altitude_m'],
        }
        flight['waypoints'] = [hold, *shifted]
        flight['mission']['duration_s'] = round(travel_duration + delay_s, 2)
        flight['mission']['start_time_utc'] = reference_time.isoformat()
    return flight
