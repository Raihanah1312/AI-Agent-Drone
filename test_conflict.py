
from conflict_detector import detect_conflicts
from config import HORIZONTAL_THRESHOLD_M
from simulator import DRONE_LAT, DRONE_LON, DRONE_ALT

# Membuat data pesawat simulasi
def make_aircraft(callsign, lat, lon, altitude):
    state = [None] * 17
    state[1] = callsign
    state[5] = lon
    state[6] = lat
    state[7] = altitude
    return state


test_aircraft = [
    # Pesawat sangat dekat, selisih ketinggian kecil
    make_aircraft(
        "TEST001", DRONE_LAT + 0.005,
        DRONE_LON, 250
    ),

    # Pesawat jauh, tetapi ketinggiannya dekat
    make_aircraft(
        "TEST002", DRONE_LAT + (HORIZONTAL_THRESHOLD_M + 1000) / 111_195,
        DRONE_LON, 200
    ),

    # Pesawat dekat, tetapi jauh lebih tinggi
    make_aircraft(
        "TEST003", DRONE_LAT + 0.005,
        DRONE_LON, 1200
    ),

    # Pesawat dekat dan pada ketinggian hampir sama
    make_aircraft(
        "TEST004", DRONE_LAT + 0.002,
        DRONE_LON, 160
    ),
]

results = detect_conflicts(
    test_aircraft, DRONE_LAT, DRONE_LON, DRONE_ALT
)

print("=== PENGUJIAN KONFLIK DRONE ===")

for item in results:
    status = (
        "POTENSI KONFLIK"
        if item["conflict"]
        else "TIDAK KONFLIK"
    )

    print(
        f"{item['callsign']} | "
        f"Horizontal: {item['horizontal_m']:.2f} m | "
        f"Vertikal: {item['vertical_m']:.2f} m | "
        f"{status}"
    )

# Verifikasi otomatis
expected = {
    "TEST001": True,
    "TEST002": False,
    "TEST003": False,
    "TEST004": True,
}

for item in results:
    assert item["conflict"] == expected[item["callsign"]], (
        f"Hasil tidak sesuai untuk {item['callsign']}"
    )

print("\nSEMUA PENGUJIAN BERHASIL")
