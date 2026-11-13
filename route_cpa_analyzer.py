import json
import math
from datetime import datetime, timezone

from aircraft_validator import classify_aircraft
from flight_plan import generate_flight_plan
from opensky_client import get_aircraft_states
from trajectory_predictor import predict_position

EARTH_RADIUS_M = 6_371_000.0
from config import HORIZONTAL_THRESHOLD_M, VERTICAL_THRESHOLD_M
MAX_PREDICTION_S = 600.0
REPORT_FILE = "route_cpa_report.json"


def relative_position(drone_lat, drone_lon, aircraft_lat, aircraft_lon):
    """Vektor relatif pesawat terhadap drone pada bidang lokal East-North."""
    mean_lat = math.radians((drone_lat + aircraft_lat) / 2.0)
    delta_lon = (aircraft_lon - drone_lon + 180.0) % 360.0 - 180.0
    east = math.radians(delta_lon) * EARTH_RADIUS_M * math.cos(mean_lat)
    north = math.radians(aircraft_lat - drone_lat) * EARTH_RADIUS_M
    return east, north


def calculate_interval_cpa(p0, p1):
    """Jarak horizontal minimum selama satu interval interpolasi linear."""
    duration = p1["time_s"] - p0["time_s"]
    if duration <= 0:
        return None
    x0, y0 = p0["east_m"], p0["north_m"]
    vx = (p1["east_m"] - x0) / duration
    vy = (p1["north_m"] - y0) / duration
    speed_squared = vx * vx + vy * vy
    tau = 0.0 if speed_squared == 0 else max(
        0.0, min(duration, -(x0 * vx + y0 * vy) / speed_squared)
    )
    return {
        "time_s": p0["time_s"] + tau,
        "horizontal_m": math.hypot(x0 + vx * tau, y0 + vy * tau),
    }


def analyze_route_cpa():
    print("=== ROUTE CPA ANALYZER + DATA VALIDATION ===")
    flight_plan = generate_flight_plan()
    waypoints = flight_plan["waypoints"]
    mission = flight_plan["mission"]
    mission_start = datetime.fromisoformat(mission["start_time_utc"]).timestamp()
    total_waypoints = len(waypoints)
    if total_waypoints == 0:
        raise ValueError("Flight plan tidak memiliki waypoint")

    print(f"Waypoint drone : {total_waypoints}")
    print(f"Durasi misi    : {mission['duration_s']:.2f} s")

    data = get_aircraft_states()
    states = data.get("states") or []
    snapshot_time = data.get("time")
    if snapshot_time is None:
        raise ValueError("Timestamp snapshot OpenSky tidak tersedia")

    aircraft_results = []
    excluded_aircraft = []
    unanalyzable_aircraft = []

    for index, state in enumerate(states):
        callsign = "UNKNOWN"
        if isinstance(state, (list, tuple)) and len(state) > 1:
            callsign = (state[1] or "").strip() or "UNKNOWN"

        category, reason = classify_aircraft(state, snapshot_time)
        identity = {"index": index, "callsign": callsign, "reason": reason}
        if category == "EXCLUDED":
            excluded_aircraft.append(identity)
            continue
        if category != "ANALYZED":
            unanalyzable_aircraft.append(identity)
            continue

        try:
            position_time = state[3]
            lon, lat, altitude = state[5], state[6], state[7]
            speed, heading = state[9], state[10]
            samples = []
            evaluated_steps = []
            for step_index, waypoint in enumerate(waypoints):
                t_abs = datetime.fromisoformat(waypoint["time_utc"]).timestamp()
                dt = t_abs - position_time
                if not (0 <= dt <= MAX_PREDICTION_S):
                    continue
                pred_lat, pred_lon = predict_position(
                    lat, lon, speed, heading, dt
                )
                east, north = relative_position(
                    waypoint["latitude"], waypoint["longitude"],
                    pred_lat, pred_lon,
                )
                samples.append({
                    "step_index": step_index,
                    "time_s": t_abs - mission_start,
                    "east_m": east,
                    "north_m": north,
                })
                evaluated_steps.append(step_index)

            if not samples:
                unanalyzable_aircraft.append({
                    **identity, "reason": "NO_VALID_PREDICTION_SAMPLES"
                })
                continue

            missing_steps = [
                i for i in range(total_waypoints) if i not in evaluated_steps
            ]
            candidates = [
                {"time_s": s["time_s"],
                 "horizontal_m": math.hypot(s["east_m"], s["north_m"])}
                for s in samples
            ]
            for p0, p1 in zip(samples, samples[1:]):
                if p1["step_index"] != p0["step_index"] + 1:
                    continue
                cpa = calculate_interval_cpa(p0, p1)
                if cpa is not None:
                    candidates.append(cpa)

            best = min(candidates, key=lambda item: item["horizontal_m"])
            vertical_m = abs(altitude - mission["altitude_m"])
            conflict = (
                best["horizontal_m"] <= HORIZONTAL_THRESHOLD_M
                and vertical_m <= VERTICAL_THRESHOLD_M
            )
            aircraft_results.append({
                "callsign": callsign,
                "index": index,
                "time_to_cpa_s": round(best["time_s"], 2),
                "horizontal_cpa_m": round(best["horizontal_m"], 2),
                "vertical_separation_m": round(vertical_m, 2),
                "potential_conflict": conflict,
                "samples_evaluated": len(samples),
                "total_waypoints": total_waypoints,
                "evaluated_steps": evaluated_steps,
                "missing_steps": missing_steps,
                "full_mission_coverage": not missing_steps,
            })
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            unanalyzable_aircraft.append({
                **identity,
                "reason": "PREDICTION_OR_DATA_ERROR",
                "error": str(exc),
            })

    aircraft_results.sort(key=lambda item: item["horizontal_cpa_m"])
    conflicts = [x for x in aircraft_results if x["potential_conflict"]]
    incomplete_aircraft = [
        x for x in aircraft_results if not x["full_mission_coverage"]
    ]

    # Pengecualian yang disengaja tidak otomatis menjadikan analisis incomplete.
    data_quality_status = (
        "INCOMPLETE_ANALYSIS"
        if unanalyzable_aircraft or incomplete_aircraft or not aircraft_results
        else "COMPLETE_ANALYSIS"
    )
    analysis_status = (
        "POTENTIAL_CONFLICT" if conflicts else
        "INCOMPLETE_ANALYSIS" if data_quality_status == "INCOMPLETE_ANALYSIS"
        else "NO_CONFLICT_DETECTED"
    )

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "opensky_snapshot_time": snapshot_time,
        "mission": mission,
        "aircraft_received": len(states),
        "aircraft_analyzed": len(aircraft_results),
        "aircraft_excluded": len(excluded_aircraft),
        "aircraft_unanalyzable": len(unanalyzable_aircraft),
        "aircraft_skipped": len(excluded_aircraft) + len(unanalyzable_aircraft),
        "potential_conflicts": len(conflicts),
        "analysis_status": analysis_status,
        "data_quality_status": data_quality_status,
        "classification": {
            "analyzed": len(aircraft_results),
            "excluded": excluded_aircraft,
            "unanalyzable": unanalyzable_aircraft,
        },
        "coverage": {
            "total_waypoints": total_waypoints,
            "aircraft_with_full_coverage": len(aircraft_results) - len(incomplete_aircraft),
            "aircraft_with_incomplete_coverage": len(incomplete_aircraft),
        },
        "closest_approaches": aircraft_results,
        "conflicts": conflicts,
        "thresholds": {
            "horizontal_m": HORIZONTAL_THRESHOLD_M,
            "vertical_m": VERTICAL_THRESHOLD_M,
            "max_prediction_s": MAX_PREDICTION_S,
        },
        "limitations": [
            "Constant-speed and constant-heading prediction",
            "Aircraft altitude assumed constant",
            "Horizontal CPA estimated by linear interpolation",
            "Only consecutive valid waypoint intervals are assessed",
            "Aircraft exclusion follows validator's research altitude filter",
            "Aircraft barometric altitude and drone altitude may use different references",
            "OpenSky coverage may be incomplete",
            "Full waypoint coverage does not imply prediction accuracy",
            "Research simulation only; not for operational flight decisions",
        ],
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    print("\n=== HASIL ANALISIS ===")
    print(f"Pesawat diterima      : {len(states)}")
    print(f"Pesawat dianalisis    : {len(aircraft_results)}")
    print(f"Pesawat EXCLUDED      : {len(excluded_aircraft)}")
    print(f"Pesawat UNANALYZABLE  : {len(unanalyzable_aircraft)}")
    print(f"Potensi konflik       : {len(conflicts)}")
    print(f"Status analisis       : {analysis_status}")
    print(f"Status kualitas data  : {data_quality_status}")

    print("\n=== PESAWAT DILEWATI ===")
    for category, items in (
        ("EXCLUDED", excluded_aircraft),
        ("UNANALYZABLE", unanalyzable_aircraft),
    ):
        for item in items:
            print(f"{item['callsign']:<12} | {category:<13} | {item['reason']}")

    print("\n=== VALIDASI CAKUPAN ===")
    for item in aircraft_results:
        print(
            f"{item['callsign']:<10} | Sampel: "
            f"{item['samples_evaluated']}/{total_waypoints} | "
            f"Missing: {item['missing_steps']} | "
            f"Full: {item['full_mission_coverage']}"
        )

    print("\n=== CPA TERDEKAT ===")
    for item in aircraft_results[:5]:
        print(
            f"{item['callsign']:<10} | CPA: {item['horizontal_cpa_m']:8.2f} m | "
            f"Vertikal: {item['vertical_separation_m']:8.2f} m | "
            f"t={item['time_to_cpa_s']:7.2f} s | "
            f"Konflik: {item['potential_conflict']}"
        )
    print(f"\nLaporan tersimpan: {REPORT_FILE}")
    return report


if __name__ == "__main__":
    try:
        analyze_route_cpa()
    except Exception as error:
        print(f"Terjadi error: {error}")
        raise
