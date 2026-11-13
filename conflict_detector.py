
from simulator import (
    DRONE_LAT,
    DRONE_LON,
    DRONE_ALT,
    haversine_km,
)
from opensky_client import get_aircraft_states

from config import HORIZONTAL_THRESHOLD_M, VERTICAL_THRESHOLD_M

def detect_conflicts(states, drone_lat, drone_lon, drone_alt):
    results = []

    for state in states:
        lat = state[6]
        lon = state[5]
        alt = state[7]

        if lat is None or lon is None or alt is None:
            continue

        callsign = (state[1] or "").strip() or "UNKNOWN"

        horizontal_m = haversine_km(
            drone_lat, drone_lon, lat, lon
        ) * 1000

        vertical_m = abs(alt - drone_alt)

        conflict = (
            horizontal_m <= HORIZONTAL_THRESHOLD_M
            and vertical_m <= VERTICAL_THRESHOLD_M
        )

        results.append({
            "callsign": callsign,
            "horizontal_m": round(horizontal_m, 2),
            "vertical_m": round(vertical_m, 2),
            "conflict": conflict,
        })

    return results


def main():
    print("=== AIRSPACE CONFLICT DETECTOR ===")

    data = get_aircraft_states()
    states = data.get("states") or []

    results = detect_conflicts(
        states, DRONE_LAT, DRONE_LON, DRONE_ALT
    )

    conflicts = [
        item for item in results if item["conflict"]
    ]

    print(f"Jumlah pesawat dianalisis: {len(results)}")
    print(f"Potensi konflik terdeteksi: {len(conflicts)}")
    print()

    if conflicts:
        for item in conflicts:
            print(
                f"PERINGATAN: {item['callsign']} | "
                f"Horizontal: {item['horizontal_m']} m | "
                f"Vertikal: {item['vertical_m']} m"
            )
    else:
        print("Tidak ada konflik berdasarkan ambang simulasi.")

    print("\n=== PESAWAT TERDEKAT ===")
    nearest = sorted(
        results,
        key=lambda item: item["horizontal_m"]
    )[:5]

    for item in nearest:
        print(
            f"{item['callsign']:<10} | "
            f"Horizontal: {item['horizontal_m']:8.2f} m | "
            f"Vertikal: {item['vertical_m']:8.2f} m | "
            f"Konflik: {item['conflict']}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Terjadi error: {error}")
