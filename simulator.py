
import math
from opensky_client import get_aircraft_states

# Posisi awal drone (Monas, Jakarta)
DRONE_LAT = -6.1754
DRONE_LON = 106.8272
DRONE_ALT = 150.0  # meter

RADIUS_KM = 70.0
MAX_ALTITUDE_M = 3300.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Menghitung jarak horizontal dua koordinat dalam km."""
    radius_bumi = 6371.0

    lat1, lon1, lat2, lon2 = map(
        math.radians, [lat1, lon1, lat2, lon2]
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return 2 * radius_bumi * math.asin(
        min(1.0, math.sqrt(a))
    )


def main():
    print("=== SIMULASI PEMANTAUAN DRONE ===")
    print(f"Posisi drone : {DRONE_LAT}, {DRONE_LON}")
    print(f"Ketinggian  : {DRONE_ALT} m")
    print(f"Radius      : {RADIUS_KM} km")
    print(f"Batas alt   : {MAX_ALTITUDE_M} m")
    print()

    data = get_aircraft_states()
    states = data.get("states") or []

    results = []

    for state in states:
        callsign = (state[1] or "").strip() or "UNKNOWN"
        lon = state[5]
        lat = state[6]

        # state[7] = barometric altitude
        altitude = state[7]

        if lat is None or lon is None or altitude is None:
            continue

        distance_km = haversine_km(
            DRONE_LAT, DRONE_LON, lat, lon
        )

        if distance_km <= RADIUS_KM and 0 <= altitude <= MAX_ALTITUDE_M:
            results.append({
                "callsign": callsign,
                "distance_km": distance_km,
                "altitude_m": altitude,
                "vertical_distance_m": abs(altitude - DRONE_ALT),
            })

    results.sort(key=lambda x: x["distance_km"])

    print(f"Pesawat dari OpenSky : {len(states)}")
    print(f"Memenuhi filter      : {len(results)}")
    print()

    for aircraft in results:
        print(
            f"{aircraft['callsign']:<10} | "
            f"Jarak: {aircraft['distance_km']:6.2f} km | "
            f"Alt: {aircraft['altitude_m']:7.2f} m | "
            f"Selisih vertikal: "
            f"{aircraft['vertical_distance_m']:7.2f} m"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Terjadi error: {error}")
