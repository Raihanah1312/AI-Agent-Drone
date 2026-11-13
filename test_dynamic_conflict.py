
from config import HORIZONTAL_THRESHOLD_M, VERTICAL_THRESHOLD_M
from flight_plan import generate_flight_plan
from simulator import haversine_km
from trajectory_predictor import predict_position


def check_conflict(drone, aircraft_lat, aircraft_lon, aircraft_alt):
    horizontal_m = haversine_km(
        drone["latitude"],
        drone["longitude"],
        aircraft_lat,
        aircraft_lon
    ) * 1000

    vertical_m = abs(
        drone["altitude_m"] - aircraft_alt
    )

    return {
        "horizontal_m": horizontal_m,
        "vertical_m": vertical_m,
        "conflict": (
            horizontal_m <= HORIZONTAL_THRESHOLD_M
            and vertical_m <= VERTICAL_THRESHOLD_M
        )
    }


def main():
    flight_plan = generate_flight_plan()
    waypoints = flight_plan["waypoints"]

    # Pesawat sintetis bergerak dari barat ke timur.
    # Semua nilai di bawah hanya untuk simulasi.
    aircraft = {
        "callsign": "SIM-MOVING-001",
        "latitude": -6.1678,
        "longitude": 106.8000,
        "altitude_m": 200.0,
        "speed_mps": 25.0,
        "heading_deg": 90.0
    }

    print("=== TEST KONFLIK DINAMIS ===")

    conflict_steps = []

    for waypoint in waypoints:
        dt_s = waypoint["elapsed_s"]

        aircraft_lat, aircraft_lon = predict_position(
            aircraft["latitude"],
            aircraft["longitude"],
            aircraft["speed_mps"],
            aircraft["heading_deg"],
            dt_s
        )

        result = check_conflict(
            waypoint,
            aircraft_lat,
            aircraft_lon,
            aircraft["altitude_m"]
        )

        status = (
            "POTENSI KONFLIK"
            if result["conflict"]
            else "TIDAK KONFLIK"
        )

        print(
            f"Step {waypoint['step']:02d} | "
            f"t={dt_s:6.1f}s | "
            f"Horizontal={result['horizontal_m']:8.2f}m | "
            f"Vertikal={result['vertical_m']:6.2f}m | "
            f"{status}"
        )

        if result["conflict"]:
            conflict_steps.append(waypoint["step"])

    assert conflict_steps, (
        "Skenario tidak menghasilkan konflik. "
        "Periksa parameter pesawat sintetis."
    )

    print("\nPENGUJIAN BERHASIL")
    print(f"Konflik terdeteksi pada step: {conflict_steps}")


if __name__ == "__main__":
    main()
