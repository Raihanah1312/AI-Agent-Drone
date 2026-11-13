
import math

from config import HORIZONTAL_THRESHOLD_M, VERTICAL_THRESHOLD_M
from flight_plan import generate_flight_plan
from trajectory_predictor import predict_position

EARTH_RADIUS_M = 6371000.0

AIRCRAFT = {
    "latitude": -6.1678,
    "longitude": 106.8000,
    "altitude_m": 200.0,
    "speed_mps": 25.0,
    "heading_deg": 90.0,
}


def relative_position(drone, aircraft_lat, aircraft_lon):
    """Posisi relatif pesawat terhadap drone dalam meter."""
    mean_lat = math.radians(
        (drone["latitude"] + aircraft_lat) / 2
    )

    east_m = math.radians(
        aircraft_lon - drone["longitude"]
    ) * EARTH_RADIUS_M * math.cos(mean_lat)

    north_m = math.radians(
        aircraft_lat - drone["latitude"]
    ) * EARTH_RADIUS_M

    return east_m, north_m


def analyze_cpa():
    plan = generate_flight_plan()
    samples = []

    for waypoint in plan["waypoints"]:
        t = waypoint["elapsed_s"]

        aircraft_lat, aircraft_lon = predict_position(
            AIRCRAFT["latitude"],
            AIRCRAFT["longitude"],
            AIRCRAFT["speed_mps"],
            AIRCRAFT["heading_deg"],
            t
        )

        x, y = relative_position(
            waypoint,
            aircraft_lat,
            aircraft_lon
        )

        samples.append((t, x, y))

    best = None

    for i in range(len(samples) - 1):
        t0, x0, y0 = samples[i]
        t1, x1, y1 = samples[i + 1]

        duration = t1 - t0
        if duration <= 0:
            continue

        vx = (x1 - x0) / duration
        vy = (y1 - y0) / duration

        speed_squared = vx * vx + vy * vy

        if speed_squared == 0:
            tau = 0.0
        else:
            tau = -(x0 * vx + y0 * vy) / speed_squared
            tau = max(0.0, min(duration, tau))

        closest_x = x0 + vx * tau
        closest_y = y0 + vy * tau

        distance = math.hypot(closest_x, closest_y)
        time_cpa = t0 + tau

        if best is None or distance < best["distance_m"]:
            best = {
                "time_s": time_cpa,
                "distance_m": distance,
                "interval": (i, i + 1)
            }

    vertical_m = abs(
        AIRCRAFT["altitude_m"]
        - plan["mission"]["altitude_m"]
    )

    conflict = (
        best["distance_m"] <= HORIZONTAL_THRESHOLD_M
        and vertical_m <= VERTICAL_THRESHOLD_M
    )

    print("=== CLOSEST POINT OF APPROACH ===")
    print(f"Waktu CPA       : {best['time_s']:.2f} s")
    print(f"Jarak horizontal: {best['distance_m']:.2f} m")
    print(f"Selisih vertikal: {vertical_m:.2f} m")
    print(f"Interval       : {best['interval']}")
    print(f"Potensi konflik: {conflict}")


if __name__ == "__main__":
    analyze_cpa()
