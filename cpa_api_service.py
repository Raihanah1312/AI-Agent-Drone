"""CPA untuk simulasi pre-flight drone.

Menggunakan rute pengguna dan data OpenSky atau demo.
Tidak ditujukan untuk pengambilan keputusan
keselamatan penerbangan secara operasional.
"""

import math
from datetime import datetime, timezone

from trajectory_predictor import predict_position

from route_cpa_analyzer import (
    relative_position,
    calculate_interval_cpa,
    HORIZONTAL_THRESHOLD_M,
    VERTICAL_THRESHOLD_M,
    MAX_PREDICTION_S,
)


MAX_POSITION_AGE_S = 120.0
MAX_SNAPSHOT_AGE_S = 120.0


def valid_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


# ==========================================
# INTERPOLASI POSISI DRONE
# ==========================================

def interpolate_waypoint(waypoints, t):
    if t <= waypoints[0]["elapsed_s"]:
        return waypoints[0]

    if t >= waypoints[-1]["elapsed_s"]:
        return waypoints[-1]

    for a, b in zip(waypoints, waypoints[1:]):
        if a["elapsed_s"] <= t <= b["elapsed_s"]:

            f = (
                (t - a["elapsed_s"])
                / (b["elapsed_s"] - a["elapsed_s"])
            )

            return {
                "latitude": (
                    a["latitude"]
                    + f * (b["latitude"] - a["latitude"])
                ),
                "longitude": (
                    a["longitude"]
                    + f * (b["longitude"] - a["longitude"])
                ),
                "altitude_m": (
                    a["altitude_m"]
                    + f * (b["altitude_m"] - a["altitude_m"])
                ),
            }

    raise ValueError(
        "Tidak dapat menginterpolasi waypoint"
    )


# ==========================================
# MEMBUAT DATA PESAWAT DEMO
# ==========================================

def make_demo_snapshot(flight_plan, reference_epoch):
    """
    Membuat pesawat simulasi yang sengaja
    berpapasan dengan drone di tengah rute.

    Tidak mengambil data OpenSky.
    """

    waypoints = flight_plan["waypoints"]

    halfway_s = (
        float(flight_plan["mission"]["duration_s"]) / 2
    )

    midpoint = interpolate_waypoint(
        waypoints,
        halfway_s
    )

    # Pesawat bergerak ke timur 25 m/s.
    # Posisi awal ditarik mundur dari
    # titik pertemuan di tengah rute.
    lat, lon = predict_position(
        midpoint["latitude"],
        midpoint["longitude"],
        25.0,
        270.0,
        halfway_s,
    )

    crossing_aircraft = [
        "dem001",                    # ICAO24
        "DEMO-CROSS",                # Callsign
        "SIM",                       # Origin country
        reference_epoch,            # Time position
        reference_epoch,            # Last contact
        lon,                        # Longitude
        lat,                        # Latitude
        midpoint["altitude_m"],     # Barometric altitude
        False,                      # On ground
        25.0,                       # Speed m/s
        90.0,                       # Heading east
    ]

    # Pesawat kedua berada jauh secara vertikal
    high_aircraft = [
        "dem002",
        "DEMO-HIGH",
        "SIM",
        reference_epoch,
        reference_epoch,
        midpoint["longitude"],
        midpoint["latitude"],
        midpoint["altitude_m"] + 1500,
        False,
        0.0,
        0.0,
    ]

    return {
        "time": int(reference_epoch),
        "states": [
            crossing_aircraft,
            high_aircraft,
        ],
    }


# ==========================================
# ANALISIS CPA
# ==========================================

def analyze_flight_plan(
    flight_plan,
    snapshot,
    *,
    source,
    departure_epoch=None,
    coverage_complete=True,
    cached=False,
):
    """
    Menghitung CPA setiap pesawat terhadap
    keseluruhan rute drone.

    Asumsi:
    - Drone berangkat pada departure_epoch.
    - Pesawat bergerak dengan kecepatan,
      heading, dan altitude konstan.
    """

    if departure_epoch is None:
        departure_epoch = (
            datetime.now(timezone.utc).timestamp()
        )

    waypoints = flight_plan["waypoints"]

    if len(waypoints) < 2:
        raise ValueError(
            "Flight plan memerlukan minimal 2 waypoint"
        )

    snapshot_epoch = snapshot.get("time")

    if not valid_number(snapshot_epoch):
        raise ValueError(
            "Snapshot OpenSky tidak memiliki timestamp"
        )

    snapshot_age = (
        departure_epoch - snapshot_epoch
    )

    # Jangan menganalisis snapshot OpenSky terlalu lama
    if source == "opensky":
        if (
            snapshot_age < -10
            or snapshot_age > MAX_SNAPSHOT_AGE_S
        ):
            raise ValueError(
                "Snapshot OpenSky tidak cukup baru. "
                f"Usia: {snapshot_age:.1f} detik"
            )

    states = snapshot.get("states") or []

    aircraft_results = []
    skipped = []

    # ======================================
    # LOOP SETIAP PESAWAT
    # ======================================

    for index, state in enumerate(states):

        callsign = "UNKNOWN"

        if (
            isinstance(state, (list, tuple))
            and len(state) > 1
        ):
            callsign = (
                str(state[1] or "").strip()
                or "UNKNOWN"
            )

        identity = {
            "callsign": callsign,
            "index": index,
        }

        if (
            not isinstance(state, (list, tuple))
            or len(state) < 11
        ):
            skipped.append({
                **identity,
                "reason": "INVALID_STATE_STRUCTURE",
            })
            continue

        # Pesawat di darat tidak dianalisis
        if state[8]:
            skipped.append({
                **identity,
                "reason": "ON_GROUND",
                "excluded": True,
            })
            continue

        lon = state[5]
        lat = state[6]
        altitude = state[7]

        speed = state[9]
        heading = state[10]

        # OpenSky time_position, bukan last_contact
        position_epoch = state[3]

        required = (
            lon,
            lat,
            altitude,
            speed,
            heading,
            position_epoch,
        )

        if not all(valid_number(v) for v in required):
            skipped.append({
                **identity,
                "reason": "MISSING_POSITION_OR_MOTION",
            })
            continue

        if not (
            -90 <= lat <= 90
            and -180 <= lon <= 180
            and speed >= 0
        ):
            skipped.append({
                **identity,
                "reason": "INVALID_POSITION_OR_SPEED",
            })
            continue

        position_age = (
            departure_epoch - position_epoch
        )

        if not (
            -10 <= position_age <= MAX_POSITION_AGE_S
        ):
            skipped.append({
                **identity,
                "reason": "STALE_POSITION",
            })
            continue

        samples = []
        valid_steps = []

        # ==================================
        # PREDIKSI TIAP WAYPOINT DRONE
        # ==================================

        for i, waypoint in enumerate(waypoints):

            elapsed_s = float(
                waypoint["elapsed_s"]
            )

            # Sinkronisasi waktu drone dan pesawat
            dt = (
                departure_epoch
                + elapsed_s
                - position_epoch
            )

            if not (
                0 <= dt <= MAX_PREDICTION_S
            ):
                continue

            pred_lat, pred_lon = predict_position(
                lat,
                lon,
                speed,
                heading,
                dt,
            )

            # Jarak relatif East-North
            east, north = relative_position(
                waypoint["latitude"],
                waypoint["longitude"],
                pred_lat,
                pred_lon,
            )

            samples.append({
                "step_index": i,
                "time_s": elapsed_s,
                "east_m": east,
                "north_m": north,
            })

            valid_steps.append(i)

        if not samples:
            skipped.append({
                **identity,
                "reason": "NO_VALID_PREDICTION_SAMPLES",
            })
            continue

        # ==================================
        # HITUNG MINIMUM HORIZONTAL CPA
        # ==================================

        candidates = []

        # Kandidat dari posisi tiap waypoint
        for sample in samples:
            candidates.append({
                "time_s": sample["time_s"],
                "horizontal_m": math.hypot(
                    sample["east_m"],
                    sample["north_m"],
                ),
            })

        # Kandidat di antara dua waypoint
        for p0, p1 in zip(
            samples,
            samples[1:],
        ):
            if (
                p1["step_index"]
                != p0["step_index"] + 1
            ):
                continue

            cpa = calculate_interval_cpa(p0, p1)

            if cpa is not None:
                candidates.append(cpa)

        closest = min(
            candidates,
            key=lambda item: item["horizontal_m"],
        )

        vertical = abs(
            altitude
            - flight_plan["mission"]["altitude_m"]
        )

        missing_steps = (
            len(waypoints) - len(valid_steps)
        )

        # ==================================
        # KLASIFIKASI POTENSI KONFLIK
        # ==================================

        conflict = (
            closest["horizontal_m"]
            <= HORIZONTAL_THRESHOLD_M
            and vertical <= VERTICAL_THRESHOLD_M
        )

        aircraft_results.append({
            "callsign": callsign,
            "icao24": state[0],

            "time_to_cpa_s": round(
                closest["time_s"], 2
            ),

            "horizontal_cpa_m": round(
                closest["horizontal_m"], 2
            ),

            "vertical_separation_m": round(
                vertical, 2
            ),

            "potential_conflict": conflict,

            "samples_evaluated": len(samples),
            "total_waypoints": len(waypoints),

            "full_mission_coverage": (
                missing_steps == 0
            ),

            "position_age_s": round(
                position_age, 1
            ),
        })

    # ======================================
    # BUAT LAPORAN
    # ======================================

    aircraft_results.sort(
        key=lambda p: p["horizontal_cpa_m"]
    )

    conflicts = [
        p for p in aircraft_results
        if p["potential_conflict"]
    ]

    incomplete = (
        not coverage_complete
        or not aircraft_results
        or any(
            not p["full_mission_coverage"]
            for p in aircraft_results
        )
        or any(
            not p.get("excluded")
            for p in skipped
        )
    )

    if conflicts:
        analysis_status = "POTENTIAL_CONFLICT"
    elif incomplete:
        analysis_status = "INCOMPLETE_ANALYSIS"
    else:
        analysis_status = "NO_CONFLICT_DETECTED"

    return {
        "source": source,

        "analysis_mode": "PRE_FLIGHT_DEPART_NOW",

        "analysis_status": analysis_status,

        "data_quality_status": (
            "INCOMPLETE_ANALYSIS"
            if incomplete
            else "COMPLETE_ANALYSIS"
        ),

        "assumed_departure_time_utc": (
            datetime.fromtimestamp(
                departure_epoch,
                tz=timezone.utc,
            ).isoformat()
        ),

        "snapshot_time_utc": (
            datetime.fromtimestamp(
                snapshot_epoch,
                tz=timezone.utc,
            ).isoformat()
        ),

        "snapshot_age_s": round(
            snapshot_age, 1
        ),

        "cached_snapshot": cached,

        "route_coverage_complete": coverage_complete,

        "mission": flight_plan["mission"],

        "aircraft_received": len(states),

        "aircraft_analyzed": len(aircraft_results),

        "aircraft_skipped": len(skipped),

        "potential_conflicts": len(conflicts),

        "conflicts": conflicts,

        "closest_approaches": aircraft_results,

        "skipped": skipped,

        "thresholds": {
            "horizontal_m": HORIZONTAL_THRESHOLD_M,
            "vertical_m": VERTICAL_THRESHOLD_M,
            "max_prediction_s": MAX_PREDICTION_S,
        },

        "limitations": [
            "Drone diasumsikan berangkat saat analisis",
            "Prediksi pesawat menggunakan speed dan heading konstan",
            "Ketinggian pesawat diasumsikan konstan",
            "Posisi pesawat menggunakan time_position OpenSky",
            "CPA horizontal dihitung dengan interpolasi linear",
            "Referensi altitude barometrik dan drone bisa berbeda",
            "Data OpenSky dapat tidak lengkap atau terlambat",
            "Bukan izin atau jaminan keselamatan penerbangan",
        ],
    }
