
import math
import json
from datetime import datetime, timezone, timedelta

from simulator import haversine_km


# =====================================================
# DEFAULT MISSION PARAMETERS
# =====================================================

START_LAT = -6.1754
START_LON = 106.8272

END_LAT = -6.1600
END_LON = 106.8500

ALTITUDE_M = 150.0
SPEED_MPS = 10.0
TIME_STEP_S = 30.0


# =====================================================
# FLIGHT PLAN GENERATOR
# =====================================================

def generate_flight_plan(
    start_lat=START_LAT,
    start_lon=START_LON,
    end_lat=END_LAT,
    end_lon=END_LON,
    altitude_m=ALTITUDE_M,
    speed_mps=SPEED_MPS,
    time_step_s=TIME_STEP_S
):
    """
    Membuat rencana penerbangan drone berdasarkan
    koordinat awal, tujuan, ketinggian, dan kecepatan.

    Semua posisi drone merupakan hasil simulasi.
    """

    # -------------------------------------------------
    # 1. VALIDASI INPUT
    # -------------------------------------------------

    values = [
        start_lat,
        start_lon,
        end_lat,
        end_lon,
        altitude_m,
        speed_mps,
        time_step_s
    ]

    if not all(math.isfinite(value) for value in values):
        raise ValueError(
            "Seluruh parameter harus berupa angka yang valid"
        )

    if not (-90 <= start_lat <= 90):
        raise ValueError("Start latitude tidak valid")

    if not (-90 <= end_lat <= 90):
        raise ValueError("Destination latitude tidak valid")

    if not (-180 <= start_lon <= 180):
        raise ValueError("Start longitude tidak valid")

    if not (-180 <= end_lon <= 180):
        raise ValueError("Destination longitude tidak valid")

    if not (0 <= altitude_m <= 3300):
        raise ValueError(
            "Ketinggian harus antara 0 dan 3300 meter"
        )

    if not (0 < speed_mps <= 100):
        raise ValueError(
            "Kecepatan harus lebih dari 0 dan maksimal 100 m/s"
        )

    if not (0 < time_step_s <= 300):
        raise ValueError(
            "Time step harus lebih dari 0 dan maksimal 300 detik"
        )

    # -------------------------------------------------
    # 2. HITUNG JARAK PENERBANGAN
    # -------------------------------------------------

    distance_m = haversine_km(
        start_lat,
        start_lon,
        end_lat,
        end_lon
    ) * 1000

    # -------------------------------------------------
    # 3. HITUNG DURASI DAN JUMLAH WAYPOINT
    # -------------------------------------------------

    duration_s = distance_m / speed_mps

    steps = math.ceil(duration_s / time_step_s)

    if steps > 10000:
        raise ValueError(
            "Rute terlalu panjang atau time step terlalu kecil"
        )

    # -------------------------------------------------
    # 4. TENTUKAN WAKTU MULAI
    # -------------------------------------------------

    start_time = datetime.now(timezone.utc)

    waypoints = []

    # -------------------------------------------------
    # 5. GENERATE WAYPOINT
    # -------------------------------------------------

    for step in range(steps + 1):

        elapsed_s = min(
            step * time_step_s,
            duration_s
        )

        progress = (
            elapsed_s / duration_s
            if duration_s > 0
            else 1.0
        )

        latitude = (
            start_lat +
            (end_lat - start_lat) * progress
        )

        longitude = (
            start_lon +
            (end_lon - start_lon) * progress
        )

        waypoint_time = (
            start_time +
            timedelta(seconds=elapsed_s)
        )

        waypoints.append({
            "step": step,
            "time_utc": waypoint_time.isoformat(),
            "elapsed_s": round(elapsed_s, 2),
            "latitude": round(latitude, 6),
            "longitude": round(longitude, 6),
            "altitude_m": altitude_m
        })

    # -------------------------------------------------
    # 6. RETURN FLIGHT PLAN
    # -------------------------------------------------

    return {
        "mission": {
            "start": [
                start_lat,
                start_lon
            ],
            "destination": [
                end_lat,
                end_lon
            ],
            "altitude_m": altitude_m,
            "speed_mps": speed_mps,
            "time_step_s": time_step_s,
            "distance_m": round(distance_m, 2),
            "duration_s": round(duration_s, 2),
            "start_time_utc": start_time.isoformat()
        },
        "waypoints": waypoints
    }


# =====================================================
# TESTING TANPA FASTAPI
# =====================================================

if __name__ == "__main__":

    flight_plan = generate_flight_plan()

    with open(
        "flight_plan.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            flight_plan,
            file,
            indent=4
        )

    mission = flight_plan["mission"]

    print("=== SIMULASI RENCANA PENERBANGAN DRONE ===")

    print(
        f"Jarak rute    : "
        f"{mission['distance_m']:.2f} m"
    )

    print(
        f"Durasi        : "
        f"{mission['duration_s']:.2f} detik"
    )

    print(
        f"Jumlah titik  : "
        f"{len(flight_plan['waypoints'])}"
    )

    print("Laporan       : flight_plan.json")

    print("\n=== WAYPOINT ===")

    for point in flight_plan["waypoints"]:

        print(
            f"Step {point['step']:02d} | "
            f"t={point['elapsed_s']:6.1f}s | "
            f"Lat={point['latitude']:.6f} | "
            f"Lon={point['longitude']:.6f} | "
            f"Alt={point['altitude_m']:.1f}m"
        )
