
import json
import math
from datetime import datetime, timezone

from config import HORIZONTAL_THRESHOLD_M, VERTICAL_THRESHOLD_M
from opensky_client import get_aircraft_states
from flight_plan import generate_flight_plan
from trajectory_predictor import predict_position


# =====================================================
# KONFIGURASI SIMULASI
# =====================================================

EARTH_RADIUS_M = 6371000.0

RADIUS_KM = 70.0
MAX_ALTITUDE_M = 3300.0

MAX_POSITION_AGE_S = 60.0
MAX_PREDICTION_S = 600.0


# =====================================================
# MENGHITUNG POSISI RELATIF
# =====================================================

def relative_position(
    drone_lat,
    drone_lon,
    aircraft_lat,
    aircraft_lon
):
    """
    Menghitung posisi relatif pesawat terhadap drone
    dalam koordinat lokal East-North (meter).
    """

    mean_lat = math.radians(
        (drone_lat + aircraft_lat) / 2
    )

    delta_lon = (
        aircraft_lon - drone_lon + 180
    ) % 360 - 180

    east = (
        math.radians(delta_lon)
        * EARTH_RADIUS_M
        * math.cos(mean_lat)
    )

    north = (
        math.radians(aircraft_lat - drone_lat)
        * EARTH_RADIUS_M
    )

    return east, north


# =====================================================
# MENGHITUNG CPA PADA SATU INTERVAL
# =====================================================

def calculate_interval_cpa(p0, p1):
    """
    Menghitung pendekatan terdekat pada interval
    antara dua waypoint dengan interpolasi linear.
    """

    duration = p1["time_s"] - p0["time_s"]

    if duration <= 0:
        return None

    x0 = p0["east_m"]
    y0 = p0["north_m"]

    vx = (
        p1["east_m"] - x0
    ) / duration

    vy = (
        p1["north_m"] - y0
    ) / duration

    speed_squared = vx**2 + vy**2

    if speed_squared == 0:
        tau = 0.0
    else:
        tau = -(
            x0 * vx + y0 * vy
        ) / speed_squared

        tau = max(
            0.0,
            min(duration, tau)
        )

    closest_x = x0 + vx * tau
    closest_y = y0 + vy * tau

    return {
        "time_s": p0["time_s"] + tau,
        "horizontal_m": math.hypot(
            closest_x,
            closest_y
        )
    }


# =====================================================
# ANALISIS UTAMA
# =====================================================

def analyze_route_cpa():

    print("=== ROUTE CPA ANALYZER ===")

    # -------------------------------------------------
    # 1. MEMBACA RENCANA PENERBANGAN DRONE
    # -------------------------------------------------

    flight_plan = generate_flight_plan()

    waypoints = flight_plan["waypoints"]
    mission = flight_plan["mission"]

    mission_start = datetime.fromisoformat(
        mission["start_time_utc"]
    ).timestamp()

    total_waypoints = len(waypoints)

    print(f"Waypoint drone : {total_waypoints}")
    print(
        f"Durasi misi    : "
        f"{mission['duration_s']:.2f} s"
    )

    # -------------------------------------------------
    # 2. MENGAMBIL DATA OPENSKY
    # -------------------------------------------------

    data = get_aircraft_states()

    states = data.get("states") or []
    snapshot_time = data.get("time")

    if snapshot_time is None:
        raise ValueError(
            "Timestamp OpenSky tidak tersedia"
        )

    aircraft_results = []
    skipped_aircraft = 0

    # -------------------------------------------------
    # 3. MEMPROSES SETIAP PESAWAT
    # -------------------------------------------------

    for state in states:

        if len(state) < 11:
            skipped_aircraft += 1
            continue

        callsign = (
            state[1] or ""
        ).strip() or "UNKNOWN"

        position_time = state[3]
        lon = state[5]
        lat = state[6]
        altitude = state[7]
        speed = state[9]
        heading = state[10]

        values = (
            position_time,
            lon,
            lat,
            altitude,
            speed,
            heading
        )

        if any(
            value is None
            for value in values
        ):
            skipped_aircraft += 1
            continue

        age = snapshot_time - position_time

        if not (
            0 <= age <= MAX_POSITION_AGE_S
        ):
            skipped_aircraft += 1
            continue

        if not (
            0 <= altitude <= MAX_ALTITUDE_M
        ):
            skipped_aircraft += 1
            continue

        # ---------------------------------------------
        # 4. PREDIKSI POSISI DI SETIAP WAYPOINT
        # ---------------------------------------------

        samples = []
        evaluated_steps = []

        for step_index, waypoint in enumerate(
            waypoints
        ):

            t_abs = datetime.fromisoformat(
                waypoint["time_utc"]
            ).timestamp()

            dt = t_abs - position_time

            # Batasi horizon prediksi
            if not (
                0 <= dt <= MAX_PREDICTION_S
            ):
                continue

            pred_lat, pred_lon = predict_position(
                lat,
                lon,
                speed,
                heading,
                dt
            )

            east, north = relative_position(
                waypoint["latitude"],
                waypoint["longitude"],
                pred_lat,
                pred_lon
            )

            samples.append({
                "step_index": step_index,
                "time_s": t_abs - mission_start,
                "east_m": east,
                "north_m": north
            })

            evaluated_steps.append(step_index)

        if not samples:
            skipped_aircraft += 1
            continue

        # ---------------------------------------------
        # 5. VALIDASI CAKUPAN WAYPOINT
        # ---------------------------------------------

        missing_steps = [
            i for i in range(total_waypoints)
            if i not in evaluated_steps
        ]

        full_mission_coverage = (
            len(missing_steps) == 0
        )

        # ---------------------------------------------
        # 6. MENGHITUNG CPA
        # ---------------------------------------------

        candidates = []

        # Jarak pada setiap waypoint
        for sample in samples:

            horizontal = math.hypot(
                sample["east_m"],
                sample["north_m"]
            )

            candidates.append({
                "time_s": sample["time_s"],
                "horizontal_m": horizontal
            })

        # CPA di antara waypoint berurutan
        for i in range(len(samples) - 1):

            p0 = samples[i]
            p1 = samples[i + 1]

            # Jangan menghubungkan waypoint
            # yang tidak berurutan
            if (
                p1["step_index"]
                != p0["step_index"] + 1
            ):
                continue

            cpa = calculate_interval_cpa(
                p0,
                p1
            )

            if cpa is not None:
                candidates.append(cpa)

        best = min(
            candidates,
            key=lambda item: item["horizontal_m"]
        )

        # ---------------------------------------------
        # 7. DETEKSI POTENSI KONFLIK
        # ---------------------------------------------

        vertical_m = abs(
            altitude - mission["altitude_m"]
        )

        conflict = (
            best["horizontal_m"]
            <= HORIZONTAL_THRESHOLD_M
            and vertical_m
            <= VERTICAL_THRESHOLD_M
        )

        # ---------------------------------------------
        # 8. MENYIMPAN HASIL PESAWAT
        # ---------------------------------------------

        aircraft_results.append({
            "callsign": callsign,

            "time_to_cpa_s": round(
                best["time_s"], 2
            ),

            "horizontal_cpa_m": round(
                best["horizontal_m"], 2
            ),

            "vertical_separation_m": round(
                vertical_m, 2
            ),

            "potential_conflict": conflict,

            "samples_evaluated": len(samples),

            "total_waypoints": total_waypoints,

            "evaluated_steps": evaluated_steps,

            "missing_steps": missing_steps,

            "full_mission_coverage":
                full_mission_coverage
        })

    # -------------------------------------------------
    # 9. MENGURUTKAN HASIL
    # -------------------------------------------------

    aircraft_results.sort(
        key=lambda item: item["horizontal_cpa_m"]
    )

    conflicts = [
        item for item in aircraft_results
        if item["potential_conflict"]
    ]

    incomplete_aircraft = [
        item for item in aircraft_results
        if not item["full_mission_coverage"]
    ]

    # -------------------------------------------------
    # 10. STATUS ANALISIS
    # -------------------------------------------------

    if conflicts:
        analysis_status = "POTENTIAL_CONFLICT"

    elif (
        skipped_aircraft > 0
        or incomplete_aircraft
        or not aircraft_results
    ):
        analysis_status = "INCOMPLETE_ANALYSIS"

    else:
        analysis_status = "NO_CONFLICT_DETECTED"

    # -------------------------------------------------
    # 11. MEMBUAT LAPORAN JSON
    # -------------------------------------------------

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "opensky_snapshot_time": snapshot_time,

        "mission": mission,

        "aircraft_received": len(states),

        "aircraft_analyzed": len(
            aircraft_results
        ),

        "aircraft_skipped": skipped_aircraft,

        "potential_conflicts": len(
            conflicts
        ),

        "analysis_status": analysis_status,

        "coverage": {
            "total_waypoints": total_waypoints,

            "aircraft_with_full_coverage":
                sum(
                    item["full_mission_coverage"]
                    for item in aircraft_results
                ),

            "aircraft_with_incomplete_coverage":
                len(incomplete_aircraft)
        },

        "closest_approaches": aircraft_results,

        "conflicts": conflicts,

        "thresholds": {
            "horizontal_m":
                HORIZONTAL_THRESHOLD_M,

            "vertical_m":
                VERTICAL_THRESHOLD_M
        },

        "limitations": [
            "Constant-speed and constant-heading prediction",
            "Aircraft altitude assumed constant",
            "Horizontal CPA estimated by linear interpolation",
            "Only consecutive valid waypoint intervals are assessed",
            "Some aircraft or waypoints may be excluded",
            "Aircraft barometric altitude and drone altitude may use different references",
            "OpenSky coverage may be incomplete",
            "Research simulation only; not for operational flight decisions"
        ]
    }

    with open(
        "route_cpa_report.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            indent=4
        )

    # -------------------------------------------------
    # 12. MENAMPILKAN HASIL
    # -------------------------------------------------

    print("\n=== HASIL ANALISIS ===")

    print(
        f"Pesawat diterima  : {len(states)}"
    )

    print(
        f"Pesawat dianalisis: "
        f"{len(aircraft_results)}"
    )

    print(
        f"Pesawat dilewati : {skipped_aircraft}"
    )

    print(
        f"Potensi konflik  : {len(conflicts)}"
    )

    print(
        f"Status analisis  : {analysis_status}"
    )

    print("\n=== VALIDASI CAKUPAN ===")

    for item in aircraft_results:

        print(
            f"{item['callsign']:<10} | "
            f"Sampel: "
            f"{item['samples_evaluated']}"
            f"/{total_waypoints} | "
            f"Missing: "
            f"{item['missing_steps']} | "
            f"Full: "
            f"{item['full_mission_coverage']}"
        )

    print("\n=== CPA TERDEKAT ===")

    for item in aircraft_results[:5]:

        print(
            f"{item['callsign']:<10} | "
            f"CPA: "
            f"{item['horizontal_cpa_m']:8.2f} m | "
            f"Vertikal: "
            f"{item['vertical_separation_m']:8.2f} m | "
            f"t="
            f"{item['time_to_cpa_s']:7.2f} s | "
            f"Konflik: "
            f"{item['potential_conflict']}"
        )

    print(
        "\nLaporan tersimpan: "
        "route_cpa_report.json"
    )


# =====================================================
# MENJALANKAN PROGRAM
# =====================================================

if __name__ == "__main__":

    try:
        analyze_route_cpa()

    except Exception as error:
        print(
            f"Terjadi error: {error}"
        )
