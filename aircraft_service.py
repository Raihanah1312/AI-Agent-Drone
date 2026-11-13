import math
import threading
import time
from datetime import datetime, timezone

from opensky_client import get_aircraft_states
from simulator import haversine_km

# Pengaturan monitoring
CACHE_TTL_SECONDS = 15
MIN_DISPLAY_COVERAGE_KM = 100.0
EXTRA_DISPLAY_KM = 25.0
CACHE_SPARE_KM = 15.0
MAX_MONITORING_RADIUS_KM = 150.0

_cache_lock = threading.Lock()
_cached_data = None
_cached_bbox = None
_cached_at = 0.0


def make_bbox(lat, lon, radius_km):
    """Membuat bounding box untuk permintaan OpenSky."""

    if not all(
        math.isfinite(v)
        for v in (lat, lon, radius_km)
    ):
        raise ValueError("Koordinat atau radius tidak valid")

    if not (-85 <= lat <= 85 and -180 <= lon <= 180):
        raise ValueError("Koordinat pusat tidak didukung")

    if not (0 < radius_km <= 200):
        raise ValueError(
            "Cakupan OpenSky harus antara 0 dan 200 km"
        )

    lat_delta = radius_km * 1.03 / 110.57

    extreme_lat = min(
        89.0,
        abs(lat) + lat_delta
    )

    lon_delta = (
        radius_km * 1.03 /
        (
            111.32 *
            math.cos(math.radians(extreme_lat))
        )
    )

    if (
        lon - lon_delta < -180
        or lon + lon_delta > 180
    ):
        raise ValueError(
            "Wilayah yang melintasi bujur 180 derajat "
            "belum didukung"
        )

    return {
        "lamin": round(lat - lat_delta, 6),
        "lamax": round(lat + lat_delta, 6),
        "lomin": round(lon - lon_delta, 6),
        "lomax": round(lon + lon_delta, 6),
    }


def covers(outer, inner):
    """Mengecek cakupan cache terhadap area baru."""

    if outer is None:
        return False

    return (
        outer["lamin"] <= inner["lamin"]
        and outer["lamax"] >= inner["lamax"]
        and outer["lomin"] <= inner["lomin"]
        and outer["lomax"] >= inner["lomax"]
    )


def get_snapshot(center_lat, center_lon, radius_km):
    """
    Mengambil wilayah lebih luas daripada radius.

    Tujuan: pesawat di luar lingkaran pemantauan
    tetap tersedia untuk ditampilkan di dashboard.
    """

    global _cached_data, _cached_bbox, _cached_at

    display_km = max(
        MIN_DISPLAY_COVERAGE_KM,
        radius_km + EXTRA_DISPLAY_KM
    )

    required_bbox = make_bbox(
        center_lat,
        center_lon,
        display_km
    )

    with _cache_lock:

        age = time.monotonic() - _cached_at

        if (
            _cached_data is not None
            and age < CACHE_TTL_SECONDS
            and covers(_cached_bbox, required_bbox)
        ):
            return (
                _cached_data,
                _cached_bbox,
                round(age, 1),
                True,
            )

        fetch_bbox = make_bbox(
            center_lat,
            center_lon,
            display_km + CACHE_SPARE_KM
        )

        data = get_aircraft_states(
            bbox=fetch_bbox
        )

        _cached_data = data
        _cached_bbox = fetch_bbox
        _cached_at = time.monotonic()

        return data, fetch_bbox, 0.0, False


def valid_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def get_nearby_aircraft(
    center_lat=-6.1754,
    center_lon=106.8272,
    drone_altitude_m=150.0,
    radius_km=70.0,
    max_altitude_m=3300.0,
):
    """
    Semua pesawat dengan posisi valid tetap dikembalikan.

    in_radius:
        Posisi horizontal di dalam radius drone.

    monitored:
        Di dalam radius DAN memenuhi filter altitude.
    """

    parameters = (
        center_lat,
        center_lon,
        drone_altitude_m,
        radius_km,
        max_altitude_m,
    )

    if not all(valid_number(v) for v in parameters):
        raise ValueError(
            "Parameter monitoring harus berupa angka valid"
        )

    if not (
        1 <= radius_km <= MAX_MONITORING_RADIUS_KM
    ):
        raise ValueError(
            "Radius pemantauan harus 1–150 km"
        )

    if not (0 <= max_altitude_m <= 3300):
        raise ValueError(
            "Batas ketinggian harus 0–3300 meter"
        )

    data, bbox, cache_age, cached = get_snapshot(
        center_lat,
        center_lon,
        radius_km
    )

    states = data.get("states") or []
    aircraft = []

    for state in states:

        if (
            not isinstance(state, (list, tuple))
            or len(state) < 11
        ):
            continue

        lon = state[5]
        lat = state[6]
        alt = state[7]

        # Posisi tidak tersedia: tidak bisa dipetakan
        if not (
            valid_number(lat)
            and valid_number(lon)
        ):
            continue

        if not (
            -90 <= lat <= 90
            and -180 <= lon <= 180
        ):
            continue

        altitude = (
            alt if valid_number(alt) else None
        )

        distance_km = haversine_km(
            center_lat,
            center_lon,
            lat,
            lon
        )

        # Klasifikasi, bukan menghapus pesawat
        in_radius = distance_km <= radius_km

        within_altitude_limit = (
            altitude is not None
            and 0 <= altitude <= max_altitude_m
        )

        monitored = (
            in_radius and within_altitude_limit
        )

        vertical_distance = (
            round(
                abs(altitude - drone_altitude_m),
                2
            )
            if altitude is not None
            else None
        )

        aircraft.append({
            "icao24": state[0],
            "callsign": (
                (state[1] or "").strip()
                or "UNKNOWN"
            ),
            "latitude": lat,
            "longitude": lon,
            "altitude_m": altitude,
            "altitude_type": "barometric",
            "velocity_mps": (
                state[9]
                if valid_number(state[9])
                else None
            ),
            "true_track_deg": (
                state[10]
                if valid_number(state[10])
                else None
            ),
            "on_ground": bool(state[8]),
            "last_contact_unix": state[4],
            "distance_km": round(distance_km, 3),
            "vertical_distance_m": vertical_distance,

            # Status monitoring
            "in_radius": in_radius,
            "within_altitude_limit": within_altitude_limit,
            "monitored": monitored,
        })

    # Pesawat yang lolos filter ditampilkan di atas daftar
    aircraft.sort(
        key=lambda plane: (
            not plane["monitored"],
            plane["distance_km"]
        )
    )

    monitored_count = sum(
        plane["monitored"]
        for plane in aircraft
    )

    in_radius_count = sum(
        plane["in_radius"]
        for plane in aircraft
    )

    snapshot_unix = data.get("time")

    snapshot_utc = (
        datetime.fromtimestamp(
            snapshot_unix,
            timezone.utc
        ).isoformat()
        if snapshot_unix is not None
        else None
    )

    return {
        "source": "OpenSky Network",
        "coverage": "moving_bbox_larger_than_monitoring_radius",
        "query_bbox": bbox,
        "snapshot_time_utc": snapshot_utc,
        "cached": cached,
        "cache_age_s": cache_age,
        "refresh_interval_s": CACHE_TTL_SECONDS,

        "center": {
            "latitude": center_lat,
            "longitude": center_lon,
        },

        "filters": {
            "radius_km": radius_km,
            "max_altitude_m": max_altitude_m,
            "drone_altitude_m": drone_altitude_m,
        },

        # Total yang dikembalikan OpenSky
        "total_received": len(states),

        # Semua pesawat yang bisa ditampilkan di peta
        "total_valid_positions": len(aircraft),
        "visible_count": len(aircraft),

        # Jumlah dalam radius dan yang memenuhi filter
        "in_radius_count": in_radius_count,
        "count": monitored_count,
        "outside_count": (
            len(aircraft) - in_radius_count
        ),
        "outside_filter_count": (
            len(aircraft) - monitored_count
        ),

        # Semua pesawat, bukan hanya yang dalam radius
        "aircraft": aircraft,
    }
