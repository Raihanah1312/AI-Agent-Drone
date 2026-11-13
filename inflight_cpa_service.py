"""Analisis CPA sisa rute dari posisi drone simulasi saat ini.

Model what-if: posisi drone pada elapsed_s dianggap berada di lokasi itu
pada waktu pemindaian nyata. Sisa rute diproyeksikan 1x waktu misi,
bukan dipercepat mengikuti simulation speed pada layar.
Bukan sistem keselamatan penerbangan operasional.
"""

import math
from datetime import datetime, timezone

from aircraft_service import get_snapshot
from cpa_api_service import (
    analyze_flight_plan,
    interpolate_waypoint,
    make_demo_snapshot,
)
from simulator import haversine_km
from trajectory_predictor import predict_position
from cpa_visualization import attach_conflict_geometry


def build_remaining_plan(plan, elapsed_s):
    """Potong flight plan dan normalisasi waktu awal sisa lintasan ke 0."""
    mission = plan["mission"]
    duration = float(mission["duration_s"])

    if not math.isfinite(elapsed_s) or not (0 <= elapsed_s <= duration):
        raise ValueError(f"elapsed_s harus antara 0 dan {duration:.2f}")

    if elapsed_s >= duration - 1e-6:
        return None

    current = interpolate_waypoint(plan["waypoints"], elapsed_s)
    remaining = [{
        "step": 0,
        "elapsed_s": 0.0,
        "latitude": current["latitude"],
        "longitude": current["longitude"],
        "altitude_m": current["altitude_m"],
    }]

    for item in plan["waypoints"]:
        t = float(item["elapsed_s"])
        if t > elapsed_s + 1e-6:
            remaining.append({
                "step": len(remaining),
                "elapsed_s": round(t - elapsed_s, 6),
                "latitude": item["latitude"],
                "longitude": item["longitude"],
                "altitude_m": item["altitude_m"],
            })

    remaining_duration = max(0.0, duration - elapsed_s)
    remaining_mission = dict(mission)
    remaining_mission.update({
        "start": [current["latitude"], current["longitude"]],
        "duration_s": round(remaining_duration, 4),
        # Perhitungan sesuai geometri sisa rute, termasuk hold saat delay:
        # selama menunggu drone tidak menempuh jarak, meski waktu berjalan.
        "distance_m": round(sum(
            haversine_km(a["latitude"], a["longitude"],
                         b["latitude"], b["longitude"]) * 1000.0
            for a, b in zip(remaining, remaining[1:])
        ), 2),
        "start_time_utc": datetime.now(timezone.utc).isoformat(),
    })

    return {"mission": remaining_mission, "waypoints": remaining}



def make_persistent_demo_snapshot(plan, elapsed_s, now_epoch, *, simulation_duration_s=None):
    """Posisi pesawat DEMO pada detik simulasi `elapsed_s`.

    Pesawat dibuat SATU KALI SECARA LOGIS terhadap rute penuh, lalu
    diekstrapolasi ke waktu simulasi. Fungsi ini stateless agar hasilnya
    identik saat pause/resume, tanpa menyimpan state di RAM server.
    Berbeda dari membuat demo baru pada setiap `remaining` route.
    """
    duration = float(simulation_duration_s if simulation_duration_s is not None
                     else plan["mission"]["duration_s"])
    t = float(elapsed_s)
    if not math.isfinite(t) or not (0 <= t <= duration):
        raise ValueError(f"elapsed_s harus antara 0 dan {duration:.2f}")

    # Gunakan generator demo pre-flight dari rute ASLI, bukan sisa rute.
    # Posisi awal DEMO-CROSS ditentukan dari titik pertemuan di tengah misi.
    snapshot = make_demo_snapshot(plan, now_epoch)
    for state in snapshot.get("states") or []:
        if not isinstance(state, list) or len(state) < 11:
            continue
        lat, lon, speed, heading = state[6], state[5], state[9], state[10]
        if all(isinstance(v, (int, float)) and math.isfinite(v)
               for v in (lat, lon, speed, heading)) and speed >= 0:
            next_lat, next_lon = predict_position(lat, lon, speed, heading, t)
            state[5], state[6] = next_lon, next_lat
            state[3] = now_epoch
            state[4] = now_epoch
    snapshot["time"] = int(now_epoch)
    return snapshot


def analyze_inflight(plan, elapsed_s, radius_km=70.0, source="demo", demo_reference_plan=None):
    """Prediksi konflik untuk sisa rute pada titik simulasi sekarang."""
    if source not in ("demo", "opensky"):
        raise ValueError("source harus demo atau opensky")

    remaining = build_remaining_plan(plan, float(elapsed_s))
    now_epoch = datetime.now(timezone.utc).timestamp()

    if remaining is None:
        return {
            "source": source,
            "analysis_mode": "IN_FLIGHT_REMAINING_ROUTE",
            "analysis_status": "MISSION_COMPLETED",
            "data_quality_status": "NOT_APPLICABLE",
            "simulation_elapsed_s": round(elapsed_s, 2),
            "remaining_duration_s": 0.0,
            "remaining_distance_m": 0.0,
            "aircraft_received": 0,
            "aircraft_analyzed": 0,
            "aircraft_skipped": 0,
            "potential_conflicts": 0,
            "conflicts": [],
            "closest_approaches": [],
            "skipped": [],
            "limitations": ["Misi simulasi telah selesai"],
            "analysis_generated_at_utc": datetime.fromtimestamp(
                now_epoch, tz=timezone.utc).isoformat(),
        }

    current = remaining["waypoints"][0]
    center_lat = current["latitude"]
    center_lon = current["longitude"]

    if source == "demo":
        # Pesawat yang sama mengikuti waktu simulasi; tidak di-respawn
        # di tengah sisa rute setiap kali pemindaian.
        if demo_reference_plan is None:
            snapshot = make_persistent_demo_snapshot(plan, elapsed_s, now_epoch)
        else:
            snapshot = make_persistent_demo_snapshot(
                demo_reference_plan, elapsed_s, now_epoch,
                simulation_duration_s=plan["mission"]["duration_s"],
            )
        coverage_complete = True
        cached = False
        required_coverage_km = 0.0
    else:
        # Sertakan koridor sisa rute dalam area pemindaian CPA.
        # Bukan sekadar menguji pesawat pada posisi drone sekarang.
        max_route_offset_km = max(
            haversine_km(
                center_lat, center_lon,
                point["latitude"], point["longitude"],
            )
            for point in remaining["waypoints"]
        )
        required_coverage_km = radius_km + max_route_offset_km
        coverage_complete = required_coverage_km <= 150
        snapshot, _, _, cached = get_snapshot(
            center_lat,
            center_lon,
            min(150.0, required_coverage_km),
        )
        now_epoch = datetime.now(timezone.utc).timestamp()

    result = analyze_flight_plan(
        remaining,
        snapshot,
        source=source,
        departure_epoch=now_epoch,
        coverage_complete=coverage_complete,
        cached=cached,
    )

    result.update({
        "analysis_mode": "IN_FLIGHT_REMAINING_ROUTE",
        "analysis_generated_at_utc": datetime.fromtimestamp(
            now_epoch, tz=timezone.utc).isoformat(),
        "simulation_elapsed_s": round(float(elapsed_s), 2),
        "remaining_duration_s": remaining["mission"]["duration_s"],
        "remaining_distance_m": remaining["mission"]["distance_m"],
        "scan_center": {
            "latitude": center_lat,
            "longitude": center_lon,
        },
        "monitoring_radius_km": radius_km,
        "required_coverage_km": round(required_coverage_km, 2),
        "time_alignment_note": (
            "Posisi drone simulasi pada elapsed_s diasumsikan berlaku "
            "pada waktu scan; sisa penerbangan dihitung pada kecepatan "
            "misi 1x, tidak dipercepat oleh simulation speed UI."
        ),
        "demo_scenario_note": (
            "Pesawat sintetis yang sama bergerak mengikuti elapsed_s; "
            "bila mitigasi diterapkan, acuan skenario tetap rute original."
            if source == "demo" else None
        ),
    })
    return attach_conflict_geometry(result, remaining, snapshot, now_epoch)
