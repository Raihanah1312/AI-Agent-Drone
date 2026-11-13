
import json
from datetime import datetime, timezone

from config import HORIZONTAL_THRESHOLD_M, VERTICAL_THRESHOLD_M
from opensky_client import get_aircraft_states
from flight_plan import generate_flight_plan
from simulator import haversine_km
from trajectory_predictor import predict_position

# Maksimum umur data posisi pesawat pada waktu snapshot
MAX_POSITION_AGE_S = 60.0

# Batas horizon prediksi sederhana
MAX_PREDICTION_S = 300.0

# Filter area pemantauan
RADIUS_KM = 70.0
MAX_ALTITUDE_M = 3300.0


def analyze_route():
    print("=== ROUTE CONFLICT ANALYZER ===")

    # Buat flight plan baru untuk waktu keberangkatan sekarang
    flight_plan = generate_flight_plan()
    waypoints = flight_plan["waypoints"]

    # Ambil satu snapshot OpenSky
    data = get_aircraft_states()
    states = data.get("states") or []
    snapshot_time = data.get("time")

    if not snapshot_time:
        raise ValueError("Timestamp snapshot OpenSky tidak tersedia")

    # Data yang dipakai untuk prediksi
    aircraft_list = []

    for state in states:
        lat = state[6]
        lon = state[5]
        altitude = state[7]
        speed = state[9]
        heading = state[10]
        position_time = state[3]

        if any(value is None for value in (
            lat, lon, altitude, speed, heading, position_time
        )):
            continue

        # Umur posisi relatif terhadap waktu snapshot
        position_age = snapshot_time - position_time

        if not (0 <= position_age <= MAX_POSITION_AGE_S):
            continue

        # Filter ketinggian pada snapshot awal
        if not (0 <= altitude <= MAX_ALTITUDE_M):
            continue

        aircraft_list.append({
            "callsign": (state[1] or "").strip() or "UNKNOWN",
            "latitude": lat,
            "longitude": lon,
            "altitude_m": altitude,
            "speed_mps": speed,
            "heading_deg": heading,
            "position_time": position_time
        })

    print(f"Pesawat diterima: {len(states)}")
    print(f"Pesawat dengan data prediksi valid: {len(aircraft_list)}")

    conflicts = []
    closest_approaches = []

    for aircraft in aircraft_list:
        closest = None

        for waypoint in waypoints:
            waypoint_time = datetime.fromisoformat(
                waypoint["time_utc"]
            ).timestamp()

            # Prediksi dari waktu posisi pesawat terakhir diketahui
            dt_s = waypoint_time - aircraft["position_time"]

            if not (0 <= dt_s <= MAX_PREDICTION_S):
                continue

            predicted_lat, predicted_lon = predict_position(
                aircraft["latitude"],
                aircraft["longitude"],
                aircraft["speed_mps"],
                aircraft["heading_deg"],
                dt_s
            )

            horizontal_m = haversine_km(
                waypoint["latitude"],
                waypoint["longitude"],
                predicted_lat,
                predicted_lon
            ) * 1000

            vertical_m = abs(
                aircraft["altitude_m"] - waypoint["altitude_m"]
            )

            # Radius pemantauan terhadap posisi drone saat itu
            if horizontal_m > RADIUS_KM * 1000:
                continue

            conflict = (
                horizontal_m <= HORIZONTAL_THRESHOLD_M
                and vertical_m <= VERTICAL_THRESHOLD_M
            )

            result = {
                "callsign": aircraft["callsign"],
                "waypoint_step": waypoint["step"],
                "time_utc": waypoint["time_utc"],
                "horizontal_m": round(horizontal_m, 2),
                "vertical_m": round(vertical_m, 2),
                "conflict": conflict
            }

            if closest is None or horizontal_m < closest["horizontal_m"]:
                closest = result

            if conflict:
                conflicts.append(result)

        if closest is not None:
            closest_approaches.append(closest)

    closest_approaches.sort(
        key=lambda item: item["horizontal_m"]
    )

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "opensky_snapshot_time": snapshot_time,
        "mission": flight_plan["mission"],
        "waypoints_analyzed": len(waypoints),
        "aircraft_received": len(states),
        "aircraft_with_valid_prediction_data": len(aircraft_list),
        "potential_conflict_events": len(conflicts),
        "conflicts": conflicts,
        "closest_approaches": closest_approaches[:10],
        "assumptions": [
            "Aircraft speed and heading are constant",
            "Aircraft altitude is held constant",
            "Drone follows a straight interpolated route",
            "Drone speed and altitude are constant",
            "Only discrete waypoints are evaluated",
            "Aircraft barometric altitude is compared with simulated drone altitude",
            "OpenSky coverage and prediction accuracy are not guaranteed",
            "For simulation and research only"
        ]
    }

    with open(
        "route_conflict_report.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=4)

    print(f"Waypoint drone: {len(waypoints)}")
    print(f"Potensi konflik pada waypoint: {len(conflicts)}")

    print("\n=== PENDEKATAN TERDEKAT ===")
    for item in closest_approaches[:5]:
        print(
            f"{item['callsign']:<10} | "
            f"Step {item['waypoint_step']:02d} | "
            f"Horizontal: {item['horizontal_m']:8.2f} m | "
            f"Vertikal: {item['vertical_m']:8.2f} m"
        )

    print("\nLaporan: route_conflict_report.json")


if __name__ == "__main__":
    try:
        analyze_route()
    except Exception as error:
        print(f"Terjadi error: {error}")
