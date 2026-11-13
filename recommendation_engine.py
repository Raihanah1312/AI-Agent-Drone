"""Recommendation engine untuk skenario konflik sintetis (bukan penerbangan nyata)."""
import copy
import json
import math
from datetime import datetime, timezone

from flight_plan import generate_flight_plan
from test_dynamic_conflict import check_conflict
from trajectory_predictor import predict_position

AIRCRAFT = {
    "callsign": "SIM-MOVING-001",
    "latitude": -6.1678,
    "longitude": 106.8000,
    "altitude_m": 200.0,
    "speed_mps": 25.0,
    "heading_deg": 90.0,
}
SAMPLE_STEP_S = 5.0


def interpolate_drone(waypoints, elapsed_s):
    """Interpolasi linear di antara dua waypoint untuk waktu tertentu."""
    if elapsed_s <= waypoints[0]["elapsed_s"]:
        return copy.deepcopy(waypoints[0])
    if elapsed_s >= waypoints[-1]["elapsed_s"]:
        return copy.deepcopy(waypoints[-1])
    for a, b in zip(waypoints, waypoints[1:]):
        if a["elapsed_s"] <= elapsed_s <= b["elapsed_s"]:
            span = b["elapsed_s"] - a["elapsed_s"]
            fraction = (elapsed_s - a["elapsed_s"]) / span if span else 0
            return {
                "latitude": a["latitude"] + fraction * (b["latitude"] - a["latitude"]),
                "longitude": a["longitude"] + fraction * (b["longitude"] - a["longitude"]),
                "altitude_m": a["altitude_m"] + fraction * (b["altitude_m"] - a["altitude_m"]),
            }
    raise RuntimeError("Tidak dapat menginterpolasi waypoint")


def evaluate(name, waypoints, delay_s=0.0, altitude_m=None, latitude_offset_deg=0.0):
    duration_s = waypoints[-1]["elapsed_s"]
    n = math.ceil(duration_s / SAMPLE_STEP_S)
    times = [min(i * SAMPLE_STEP_S, duration_s) for i in range(n + 1)]
    conflict_samples = []
    min_horizontal_m = float("inf")
    min_vertical_m = float("inf")
    min_horizontal_at_s = None
    for t in times:
        drone = interpolate_drone(waypoints, t)
        if altitude_m is not None:
            drone["altitude_m"] = altitude_m
        drone["latitude"] += latitude_offset_deg
        # Aircraft begins moving at original mission start; delay affects its position.
        aircraft_t = t + delay_s
        lat, lon = predict_position(
            AIRCRAFT["latitude"], AIRCRAFT["longitude"],
            AIRCRAFT["speed_mps"], AIRCRAFT["heading_deg"], aircraft_t
        )
        result = check_conflict(drone, lat, lon, AIRCRAFT["altitude_m"])
        if result["horizontal_m"] < min_horizontal_m:
            min_horizontal_m = result["horizontal_m"]
            min_horizontal_at_s = t
        min_vertical_m = min(min_vertical_m, result["vertical_m"])
        if result["conflict"]:
            conflict_samples.append(round(t, 2))
    return {
        "name": name,
        "delay_s": delay_s,
        "altitude_m": altitude_m if altitude_m is not None else waypoints[0]["altitude_m"],
        "latitude_offset_deg": latitude_offset_deg,
        "sample_interval_s": SAMPLE_STEP_S,
        "samples_evaluated": len(times),
        "conflict_samples_count": len(conflict_samples),
        "conflict_times_s": conflict_samples,
        "min_horizontal_m": round(min_horizontal_m, 2),
        "min_horizontal_at_s": round(min_horizontal_at_s, 2),
        "min_vertical_m": round(min_vertical_m, 2),
        "passes_simulation_thresholds": len(conflict_samples) == 0,
    }


def main():
    plan = generate_flight_plan()
    waypoints = plan["waypoints"]
    if len(waypoints) < 2:
        raise ValueError("Flight plan harus memiliki minimal dua waypoint")

    scenarios = [
        evaluate("BASELINE", waypoints),
        evaluate("DELAY_60_SECONDS", waypoints, delay_s=60),
        evaluate("DELAY_120_SECONDS", waypoints, delay_s=120),
        evaluate("ALTITUDE_550_M", waypoints, altitude_m=550),
        evaluate("ROUTE_SHIFT_NORTH_APPROX_1_KM", waypoints, latitude_offset_deg=0.009),
    ]
    baseline = scenarios[0]
    # Hanya untuk peringkat simulasi, bukan jaminan keselamatan penerbangan.
    alternatives = sorted(
        scenarios[1:],
        key=lambda x: (x["conflict_samples_count"], -x["min_horizontal_m"])
    )
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenario_type": "SYNTHETIC_SIMULATION",
        "aircraft": AIRCRAFT,
        "mission_duration_s": plan["mission"]["duration_s"],
        "baseline": baseline,
        "alternatives_ranked": alternatives,
        "limitations": [
            "Synthetic aircraft only; not live OpenSky data",
            "Aircraft motion assumed constant speed, heading, and altitude",
            "5-second sampling can miss conflicts between samples",
            "Route shift moves all points including start and destination",
            "No airspace, terrain, obstacle, legal altitude, or vehicle performance validation",
            "Simulation thresholds are research parameters, not operational safety clearance",
        ],
    }
    with open("recommendation_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print("=== RECOMMENDATION ENGINE: SKENARIO SINTETIS ===")
    print(f"Durasi misi: {plan['mission']['duration_s']:.2f} s")
    for scenario in scenarios:
        status = "LOLOS AMBANG SIMULASI" if scenario["passes_simulation_thresholds"] else "ADA POTENSI KONFLIK"
        print(f"{scenario['name']}: {status} | sampel konflik={scenario['conflict_samples_count']} | "
              f"min horizontal={scenario['min_horizontal_m']:.2f} m | min vertikal={scenario['min_vertical_m']:.2f} m")
    print("Laporan: recommendation_report.json")
    print("PERINGATAN: Hasil ini bukan izin atau jaminan keselamatan penerbangan.")


if __name__ == "__main__":
    main()
