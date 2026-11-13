"""Geometri visualisasi potensi konflik CPA (SIMULASI / BUKAN AVIONIK).

Menambahkan posisi pesawat pada waktu analisis, perkiraan lintasan masa depan,
dan dua posisi pada waktu CPA. Semua memakai snapshot & epoch yang sama
seperti perhitungan CPA. Tidak melakukan panggilan OpenSky tambahan.
"""

import math

from trajectory_predictor import predict_position

MAX_PREDICTION_S = 600.0


def _valid(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _interpolate_route(plan, time_s):
    """Interpolasi koordinat drone pada waktu lokal sisa/seluruh misi."""
    pts = plan["waypoints"]
    if not pts:
        raise ValueError("Flight plan tanpa waypoint")

    if time_s <= pts[0]["elapsed_s"]:
        return pts[0]
    if time_s >= pts[-1]["elapsed_s"]:
        return pts[-1]

    for a, b in zip(pts, pts[1:]):
        start = float(a["elapsed_s"])
        end = float(b["elapsed_s"])
        if start <= time_s <= end:
            fraction = (time_s - start) / (end - start)
            return {
                "latitude": a["latitude"] + fraction * (b["latitude"] - a["latitude"]),
                "longitude": a["longitude"] + fraction * (b["longitude"] - a["longitude"]),
                "altitude_m": a["altitude_m"] + fraction * (b["altitude_m"] - a["altitude_m"]),
            }

    raise ValueError("Interpolasi rute gagal")


def attach_conflict_geometry(result, plan, snapshot, departure_epoch):
    """Menambah `conflict_visualizations` hanya untuk pesawat yang dideteksi konflik.

    departure_epoch adalah waktu analisis yang *sama* dengan yang diberikan ke
    analyze_flight_plan. Untuk inflight, 0 s berarti posisi drone simulasi pada
    scan itu, bukan waktu berangkat misi aslinya.
    """
    result["conflict_visualizations"] = []

    if not result.get("conflicts"):
        return result

    by_icao = {}
    for state in snapshot.get("states") or []:
        if isinstance(state, (list, tuple)) and len(state) >= 11:
            icao = str(state[0] or "").lower().strip()
            if icao:
                by_icao[icao] = state

    duration_s = float(plan["mission"]["duration_s"])

    for conflict in result["conflicts"]:
        icao = str(conflict.get("icao24") or "").strip().lower()
        state = by_icao.get(icao)
        if state is None:
            continue

        lat, lon, altitude = state[6], state[5], state[7]
        speed, heading, position_epoch = state[9], state[10], state[3]
        if not all(_valid(x) for x in (lat, lon, altitude, speed, heading, position_epoch)):
            continue
        if speed < 0 or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue

        cpa_s = conflict.get("time_to_cpa_s")
        if not _valid(cpa_s) or not (0 <= cpa_s <= duration_s + 0.1):
            continue

        age_s = float(departure_epoch) - float(position_epoch)
        # Tidak mengekstrapolasi mundur atau melewati horizon yang digunakan CPA.
        if not (0 <= age_s <= MAX_PREDICTION_S) or age_s + cpa_s > MAX_PREDICTION_S:
            continue

        try:
            now_lat, now_lon = predict_position(lat, lon, speed, heading, age_s)
            cpa_lat, cpa_lon = predict_position(lat, lon, speed, heading, age_s + cpa_s)
            drone_cpa = _interpolate_route(plan, cpa_s)

            # Garis hingga CPA + paling banyak 60 detik, selama valid horizon.
            end_s = min(
                duration_s,
                MAX_PREDICTION_S - age_s,
                max(cpa_s, 60.0) + 60.0,
            )
            samples = max(1, min(30, math.ceil(end_s / 15)))
            predicted_track = []
            for index in range(samples + 1):
                t = end_s * index / samples
                p_lat, p_lon = predict_position(lat, lon, speed, heading, age_s + t)
                predicted_track.append([p_lon, p_lat])
        except (ValueError, OverflowError, ZeroDivisionError):
            continue

        result["conflict_visualizations"].append({
            "icao24": icao,
            "callsign": str(conflict.get("callsign") or "UNKNOWN"),
            "time_to_cpa_s": float(cpa_s),
            "horizontal_cpa_m": float(conflict["horizontal_cpa_m"]),
            "vertical_separation_m": float(conflict["vertical_separation_m"]),
            "aircraft_at_analysis": {
                "latitude": now_lat, "longitude": now_lon,
            },
            "aircraft_at_cpa": {
                "latitude": cpa_lat, "longitude": cpa_lon,
                "altitude_m": float(altitude),
            },
            "drone_at_cpa": {
                "latitude": float(drone_cpa["latitude"]),
                "longitude": float(drone_cpa["longitude"]),
                "altitude_m": float(drone_cpa["altitude_m"]),
            },
            "predicted_track_lonlat": predicted_track,
            "visualization_model": "constant_speed_heading_altitude",
        })

    return result
