
import json
from datetime import datetime, timezone

from opensky_client import get_aircraft_states
from simulator import (
    DRONE_LAT,
    DRONE_LON,
    DRONE_ALT,
    RADIUS_KM,
    MAX_ALTITUDE_M,
)
from conflict_detector import detect_conflicts


def main():
    print("Mengambil data OpenSky dan menjalankan analisis...")

    # 1. Ambil data pesawat dari OpenSky
    data = get_aircraft_states()
    states = data.get("states") or []

    # 2. Jalankan algoritma deteksi konflik
    results = detect_conflicts(
        states,
        DRONE_LAT,
        DRONE_LON,
        DRONE_ALT
    )

    # 3. Pilih data pesawat dengan koordinat dan altitude valid
    valid_states = [
        state for state in states
        if state[5] is not None
        and state[6] is not None
        and state[7] is not None
    ]

    # 4. Tambahkan ketinggian pesawat ke hasil analisis
    for result, state in zip(results, valid_states):
        result["aircraft_altitude_m"] = state[7]

    # 5. Filter radius 70 km dan ketinggian 0-3300 m
    monitored = [
        item for item in results
        if (
            item["horizontal_m"] <= RADIUS_KM * 1000
            and 0 <= item["aircraft_altitude_m"] <= MAX_ALTITUDE_M
        )
    ]

    # 6. Ambil pesawat yang terdeteksi berpotensi konflik
    conflicts = [
        item for item in monitored
        if item["conflict"]
    ]

    # 7. Urutkan berdasarkan jarak horizontal terdekat
    nearest = sorted(
        monitored,
        key=lambda item: item["horizontal_m"]
    )[:5]

    # 8. Buat laporan JSON
    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "opensky_snapshot_time": data.get("time"),

        "drone": {
            "latitude": DRONE_LAT,
            "longitude": DRONE_LON,
            "altitude_m": DRONE_ALT
        },

        "monitoring": {
            "radius_km": RADIUS_KM,
            "max_altitude_m": MAX_ALTITUDE_M,
            "aircraft_received": len(states),
            "aircraft_in_radius_and_altitude": len(monitored),
            "conflicts_detected": len(conflicts)
        },

        "nearest_aircraft": nearest,
        "conflicts": conflicts,

        "limitations": [
            "Snapshot-based proximity detection only",
            "Aircraft altitude is barometric",
            "Vertical separation is indicative only",
            "OpenSky coverage may be incomplete",
            "Not suitable for operational flight safety decisions"
        ]
    }

    # 9. Simpan laporan
    with open(
        "drone_report.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=4)

    # 10. Tampilkan ringkasan
    print("\n=== HASIL ANALISIS ===")
    print(f"Pesawat diterima     : {len(states)}")
    print(f"Memenuhi kedua filter: {len(monitored)}")
    print(f"Potensi konflik      : {len(conflicts)}")
    print("Laporan tersimpan    : drone_report.json")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Terjadi error: {error}")
