"""Pembangkit kandidat rute drone berbasis waypoint (simulasi).

Fokus tahap ini hanya geometri dan penjadwalan rute.
Tidak memanggil OpenSky, CPA, Hermes, atau API eksternal.

Output setiap flight_plan kompatibel secara struktur dengan flight_plan.py:
  {"mission": {...}, "waypoints": [{"elapsed_s", "latitude", ...}, ...]}

Penting:
* Titik belok selalu ada dalam `waypoints` (tidak terlewat oleh time step).
* Seluruh kandidat menggunakan waktu keberangkatan identik untuk perbandingan CPA adil.
* Tidak ada klaim rute aman sebelum kandidat dinilai oleh CPA + data airspace.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Iterable

EARTH_RADIUS_M = 6_371_000.0
DEFAULT_OFFSETS_M = (500.0, 1_000.0, 1_500.0)
ADAPTIVE_OFFSETS_M = (500.0, 1_000.0, 1_500.0, 2_000.0, 2_500.0)
ADAPTIVE_BEND_FRACTIONS = (0.3, 0.5, 0.7)
MAX_ROUTE_CANDIDATES = 60
MAX_OUTPUT_WAYPOINTS = 10_000


def _finite_number(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} harus berupa angka")
    if not math.isfinite(value):
        raise ValueError(f"{label} harus bernilai hingga (finite)")
    return float(value)


def _validate_point(lat: float, lon: float) -> tuple[float, float]:
    lat = _finite_number(lat, "latitude")
    lon = _finite_number(lon, "longitude")
    if not (-90 <= lat <= 90):
        raise ValueError("Latitude harus -90 sampai 90")
    if not (-180 <= lon <= 180):
        raise ValueError("Longitude harus -180 sampai 180")
    return lat, lon


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Jarak geodesik permukaan bumi dalam meter."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Arah dari titik awal menuju akhir, searah jarum jam dari utara."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    east = math.sin(dl) * math.cos(p2)
    north = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(east, north)) + 360) % 360


def destination_point(
    lat: float, lon: float, bearing_deg: float, distance_m: float
) -> tuple[float, float]:
    """Proyeksi titik baru dari posisi, arah, dan jarak (great-circle)."""
    lat, lon = _validate_point(lat, lon)
    distance_m = _finite_number(distance_m, "distance_m")
    if distance_m < 0:
        raise ValueError("distance_m tidak boleh negatif")
    b = math.radians(bearing_deg)
    d = distance_m / EARTH_RADIUS_M
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    p2 = math.asin(
        math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b)
    )
    l2 = l1 + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(p1),
        math.cos(d) - math.sin(p1) * math.sin(p2),
    )
    return math.degrees(p2), ((math.degrees(l2) + 540) % 360) - 180


def _departure_time(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("departure_time_utc harus datetime ISO dengan zona waktu")
    return value.astimezone(timezone.utc)


def build_route_flight_plan(
    control_points: list[tuple[float, float]] | list[list[float]],
    altitude_m: float = 150.0,
    speed_mps: float = 10.0,
    time_step_s: float = 30.0,
    departure_time_utc: datetime | str | None = None,
    route_id: str = "CUSTOM",
) -> dict:
    """Buat flight plan melewati semua control_points berurutan.

    Time step membagi setiap SEGMEN, sehingga titik belok selalu menjadi waypoint.
    Menggunakan kecepatan dan ketinggian konstan untuk simulasi tahap awal.
    """
    if len(control_points) < 2:
        raise ValueError("Minimal dua control point diperlukan")
    points = [_validate_point(float(p[0]), float(p[1])) for p in control_points]
    altitude_m = _finite_number(altitude_m, "altitude_m")
    speed_mps = _finite_number(speed_mps, "speed_mps")
    time_step_s = _finite_number(time_step_s, "time_step_s")
    if not (0 <= altitude_m <= 3300):
        raise ValueError("altitude_m harus antara 0 dan 3300")
    if not (0 < speed_mps <= 100):
        raise ValueError("speed_mps harus antara 0 dan 100")
    if not (0 < time_step_s <= 300):
        raise ValueError("time_step_s harus antara 0 dan 300")

    distances = [haversine_m(*a, *b) for a, b in zip(points, points[1:])]
    if any(distance < 0.01 for distance in distances):
        raise ValueError("Control point yang berurutan tidak boleh sama")

    total_distance = sum(distances)
    total_duration = total_distance / speed_mps
    departure = _departure_time(departure_time_utc)

    samples: list[tuple[float, float, float]] = [(0.0, *points[0])]
    elapsed_before = 0.0

    for seg_index, (a, b, segment_m) in enumerate(
        zip(points, points[1:], distances)
    ):
        segment_duration = segment_m / speed_mps
        segment_bearing = initial_bearing_deg(*a, *b)
        steps = math.ceil(segment_duration / time_step_s)
        if len(samples) + steps > MAX_OUTPUT_WAYPOINTS:
            raise ValueError(
                "Terlalu banyak waypoint. Naikkan time_step_s / speed_mps "
                "atau perpendek rute."
            )
        for step in range(1, steps + 1):
            local_elapsed = min(step * time_step_s, segment_duration)
            absolute_elapsed = elapsed_before + local_elapsed
            if step == steps:
                # Koordinat waypoint akhir segmen tepat pada control point.
                lat, lon = b
            else:
                lat, lon = destination_point(
                    *a, segment_bearing, speed_mps * local_elapsed
                )
            samples.append((absolute_elapsed, lat, lon))
        elapsed_before += segment_duration

    waypoints = []
    for i, (elapsed_s, lat, lon) in enumerate(samples):
        dt = departure + timedelta(seconds=elapsed_s)
        waypoints.append({
            "step": i,
            "time_utc": dt.isoformat(),
            "elapsed_s": round(elapsed_s, 2),
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "altitude_m": altitude_m,
        })

    return {
        "mission": {
            "route_id": route_id,
            "start": list(points[0]),
            "destination": list(points[-1]),
            "control_points": [list(p) for p in points],
            "altitude_m": altitude_m,
            "speed_mps": speed_mps,
            "time_step_s": time_step_s,
            "distance_m": round(total_distance, 2),
            "duration_s": round(total_duration, 2),
            "start_time_utc": departure.isoformat(),
        },
        "waypoints": waypoints,
    }


def _format_id_number(value: float) -> str:
    """Kode ID stabil, termasuk untuk pecahan tidak bulat."""
    return f"{value:.8f}".rstrip("0").rstrip(".").replace(".", "P")


def generate_route_candidates(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    altitude_m: float = 150.0,
    speed_mps: float = 10.0,
    time_step_s: float = 30.0,
    offsets_m: Iterable[float] = DEFAULT_OFFSETS_M,
    bend_fraction: float = 0.5,
    departure_time_utc: datetime | str | None = None,
    *,
    bend_fractions: Iterable[float] | None = None,
) -> dict:
    """Buat kandidat satu atau banyak posisi belokan tanpa menganalisis konflik.

    Mode lama (kompatibel): bend_fractions=None -> bend_fraction saja.
    Mode adaptif: bend_fractions=(0.3, 0.5, 0.7) dan 5 offsets -> 30 kandidat.

    ID mode lama: LEFT_500_M
    ID mode adaptif: LEFT_500_M_F30 (30% dari lintasan awal).
    """
    start = _validate_point(start_lat, start_lon)
    end = _validate_point(end_lat, end_lon)

    offsets = tuple(_finite_number(v, "offset_m") for v in offsets_m)
    if not offsets or len(offsets) > 10 or any(not (0 < v <= 10_000) for v in offsets):
        raise ValueError("offsets_m harus berisi 1-10 jarak dengan nilai >0 hingga 10.000 m")
    if len(set(offsets)) != len(offsets):
        raise ValueError("offsets_m tidak boleh duplikat")

    if bend_fractions is None:
        fractions = (_finite_number(bend_fraction, "bend_fraction"),)
        multi_fraction_mode = False
    else:
        fractions = tuple(_finite_number(v, "bend_fraction") for v in bend_fractions)
        multi_fraction_mode = True
    if not fractions or len(fractions) > 5:
        raise ValueError("bend_fractions harus berisi 1 sampai 5 nilai")
    if any(not (0.1 <= v <= 0.9) for v in fractions):
        raise ValueError("Semua bend_fraction harus antara 0.1 sampai 0.9")
    if len(set(fractions)) != len(fractions):
        raise ValueError("bend_fractions tidak boleh duplikat")
    if 2 * len(offsets) * len(fractions) > MAX_ROUTE_CANDIDATES:
        raise ValueError(f"Jumlah kandidat maksimal {MAX_ROUTE_CANDIDATES}")

    departure = _departure_time(departure_time_utc)
    original = build_route_flight_plan(
        [start, end], altitude_m, speed_mps, time_step_s, departure, "ORIGINAL"
    )
    baseline_m = original["mission"]["distance_m"]
    baseline_duration_s = original["mission"]["duration_s"]

    direction = initial_bearing_deg(*start, *end)
    base_distance_m = haversine_m(*start, *end)
    candidates = []
    for fraction in fractions:
        midpoint = destination_point(*start, direction, base_distance_m * fraction)
        for side, delta_deg in (("LEFT", -90), ("RIGHT", 90)):
            for offset_m in offsets:
                bend = destination_point(*midpoint, direction + delta_deg, offset_m)
                route_id = f"{side}_{_format_id_number(offset_m)}_M"
                if multi_fraction_mode:
                    route_id += f"_F{_format_id_number(fraction * 100)}"
                flight_plan = build_route_flight_plan(
                    [start, bend, end],
                    altitude_m, speed_mps, time_step_s, departure, route_id,
                )
                candidates.append({
                    "route_id": route_id,
                    "side": side.lower(),
                    "offset_m": offset_m,
                    "bend_fraction": fraction,
                    "bend_point": [round(bend[0], 6), round(bend[1], 6)],
                    "distance_m": flight_plan["mission"]["distance_m"],
                    "duration_s": flight_plan["mission"]["duration_s"],
                    "extra_distance_m": round(
                        flight_plan["mission"]["distance_m"] - baseline_m, 2
                    ),
                    "extra_duration_s": round(
                        flight_plan["mission"]["duration_s"] - baseline_duration_s, 2
                    ),
                    "evaluation_status": "NOT_EVALUATED",
                    "flight_plan": flight_plan,
                })

    return {
        "status": "CANDIDATES_GENERATED",
        "note": (
            "Kandidat belum diuji CPA, cakupan data, medan, atau restriksi airspace. "
            "Jangan disebut rute aman sebelum evaluasi tambahan."
        ),
        "original_route": original,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "search_mode": "ADAPTIVE" if multi_fraction_mode else "SINGLE_BEND_FRACTION",
        "bend_fraction": fractions[0] if not multi_fraction_mode else None,
        "bend_fractions": list(fractions),
        "offsets_m": list(offsets),
        "departure_time_utc": departure.isoformat(),
    }


if __name__ == "__main__":
    report = generate_route_candidates(
        start_lat=-6.1754,
        start_lon=106.8272,
        end_lat=-6.1600,
        end_lon=106.8500,
        altitude_m=150,
        speed_mps=10,
        time_step_s=30,
        offsets_m=ADAPTIVE_OFFSETS_M,
        bend_fractions=ADAPTIVE_BEND_FRACTIONS,
    )
    print("=== ADAPTIVE ROUTE GENERATOR: DEMO TANPA OPENSKY ===")
    original = report["original_route"]["mission"]
    print(f"Rute awal: {original['distance_m']:.2f} m / {original['duration_s']:.2f} s")
    print(f"Kandidat: {report['candidate_count']}")
    print("-" * 82)
    for item in report["candidates"]:
        print(
            f"{item['route_id']:<22} | "
            f"{item['distance_m']:>9.2f} m | "
            f"+{item['extra_distance_m']:>8.2f} m | "
            f"+{item['extra_duration_s']:>7.2f} s | "
            f"{item['evaluation_status']}"
        )
    print("\nSemua status NOT_EVALUATED: belum diuji CPA atau batas ruang udara.")
    # File JSON contoh agar mudah diperiksa bila diinginkan.
    with open("route_candidates_adaptive_demo.json", "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
    print("Tersimpan: route_candidates_demo.json")
