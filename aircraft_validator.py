
from collections import Counter
from opensky_client import get_aircraft_states

MAX_ALTITUDE_M = 3300.0
MAX_POSITION_AGE_S = 60.0


def classify_aircraft(state, snapshot_time):
    """
    Mengklasifikasikan pesawat berdasarkan kelengkapan
    data dan kriteria ketinggian simulasi.
    """

    if not isinstance(state, (list, tuple)) or len(state) < 11:
        return "UNANALYZABLE", "INVALID_STATE_FORMAT"

    position_time = state[3]
    longitude = state[5]
    latitude = state[6]
    altitude = state[7]
    velocity = state[9]
    heading = state[10]

    required = {
        "position_time": position_time,
        "longitude": longitude,
        "latitude": latitude,
        "altitude": altitude,
        "velocity": velocity,
        "heading": heading,
    }

    missing = [
        name for name, value in required.items()
        if value is None
    ]

    if missing:
        return "UNANALYZABLE", "MISSING_" + ",".join(missing)

    age = snapshot_time - position_time

    if age < 0 or age > MAX_POSITION_AGE_S:
        return "UNANALYZABLE", "STALE_OR_INVALID_POSITION"

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return "UNANALYZABLE", "INVALID_COORDINATES"

    if velocity < 0 or not (0 <= heading <= 360):
        return "UNANALYZABLE", "INVALID_MOVEMENT_DATA"

    if altitude < 0 or altitude > MAX_ALTITUDE_M:
        return "EXCLUDED", "OUTSIDE_ALTITUDE_FILTER"

    return "ANALYZED", "VALID"


def main():
    data = get_aircraft_states()

    states = data.get("states") or []
    snapshot_time = data.get("time")

    if snapshot_time is None:
        raise ValueError("Timestamp OpenSky tidak tersedia")

    results = []

    for index, state in enumerate(states):
        callsign = "UNKNOWN"

        if isinstance(state, (list, tuple)) and len(state) > 1:
            callsign = (state[1] or "").strip() or "UNKNOWN"

        status, reason = classify_aircraft(state, snapshot_time)

        results.append({
            "index": index,
            "callsign": callsign,
            "status": status,
            "reason": reason
        })

    counts = Counter(item["status"] for item in results)

    print("=== AIRCRAFT DATA VALIDATION ===")
    print(f"Pesawat diterima   : {len(states)}")
    print(f"ANALYZED           : {counts['ANALYZED']}")
    print(f"EXCLUDED           : {counts['EXCLUDED']}")
    print(f"UNANALYZABLE       : {counts['UNANALYZABLE']}")

    print("\n=== DETAIL KLASIFIKASI ===")

    for item in results:
        print(
            f"{item['callsign']:<12} | "
            f"{item['status']:<13} | "
            f"{item['reason']}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Terjadi error: {error}")
