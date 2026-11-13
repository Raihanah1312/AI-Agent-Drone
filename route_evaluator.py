"""Tahap 7B.2 — Bandingkan enam rute alternatif dengan CPA.

Semua rute memakai snapshot pesawat dan epoch keberangkatan yang SAMA.
Hasil adalah evaluasi simulasi, BUKAN jaminan keselamatan terbang.

Kebutuhan di folder proyek:
    route_generator.py
    cpa_api_service.py
    aircraft_service.py (hanya diperlukan untuk source='opensky')

Entrypoint utama: evaluate_route_candidates(...).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Callable, Iterable

from route_generator import (
    DEFAULT_OFFSETS_M,
    ADAPTIVE_OFFSETS_M,
    ADAPTIVE_BEND_FRACTIONS,
    generate_route_candidates,
    haversine_m,
)

MAX_SCAN_RADIUS_KM = 150.0  # batas pemindaian dalam API proyek saat ini


def _route_geojson(plan: dict) -> dict:
    """GeoJSON LineString menggunakan [longitude, latitude] (MapLibre)."""
    return {
        "type": "Feature",
        "properties": {
            "route_id": plan["mission"].get("route_id", "UNKNOWN")
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [p["longitude"], p["latitude"]]
                for p in plan["waypoints"]
            ],
        },
    }


def _result_summary(plan: dict, analysis: dict) -> dict:
    """Susun ringkasan CPA tanpa mengubah nilai hasil dari analyzer."""
    counted = int(analysis.get("potential_conflicts", len(analysis.get("conflicts", []))))
    analyzed = int(analysis.get("aircraft_analyzed", 0))
    received = int(analysis.get("aircraft_received", 0))
    quality = analysis.get("data_quality_status", "UNKNOWN")
    status = analysis.get("analysis_status", "UNKNOWN")
    full = bool(analysis.get("route_coverage_complete", True))

    # Zero-conflict hanya layak DIUSULKAN jika seluruh penilaian valid.
    # Tidak berarti aman secara operasional atau lolos restriksi ruang udara.
    eligible = (
        counted == 0
        and status == "NO_CONFLICT_DETECTED"
        and quality == "COMPLETE_ANALYSIS"
        and full
        and analyzed > 0
        and received > 0
    )

    return {
        "route_id": plan["mission"].get("route_id", "UNKNOWN"),
        "distance_m": plan["mission"]["distance_m"],
        "duration_s": plan["mission"]["duration_s"],
        "potential_conflicts": counted,
        "aircraft_received": received,
        "aircraft_analyzed": analyzed,
        "aircraft_skipped": int(analysis.get("aircraft_skipped", 0)),
        "analysis_status": status,
        "data_quality_status": quality,
        "route_coverage_complete": full,
        "cpa_candidate_eligible": eligible,
        "conflicts": analysis.get("conflicts", []),
        "closest_approaches": analysis.get("closest_approaches", [])[:3],
    }


def _required_scan_radius_km(group: dict, center_lat: float, center_lon: float,
                             radius_km: float) -> float:
    """Wilayah scan tunggal mencakup seluruh waypoint semua kandidat + radius."""
    plans = [group["original_route"]] + [
        c["flight_plan"] for c in group["candidates"]
    ]
    max_offset_km = max(
        haversine_m(center_lat, center_lon, p["latitude"], p["longitude"]) / 1000
        for plan in plans for p in plan["waypoints"]
    )
    return radius_km + max_offset_km


def evaluate_route_candidates(
    start_lat: float = -6.1754,
    start_lon: float = 106.8272,
    end_lat: float = -6.1600,
    end_lon: float = 106.8500,
    altitude_m: float = 150.0,
    speed_mps: float = 10.0,
    time_step_s: float = 30.0,
    radius_km: float = 70.0,
    source: str = "demo",
    offsets_m: Iterable[float] = DEFAULT_OFFSETS_M,
    bend_fraction: float = 0.5,
    *,
    snapshot: dict | None = None,
    departure_epoch: float | None = None,
    analysis_fn: Callable | None = None,
    snapshot_provider: Callable | None = None,
    demo_builder: Callable | None = None,
    bend_fractions: Iterable[float] | None = None,
) -> dict:
    """Evaluasi rute asli dan semua kandidat, tanpa memilih rute yang tak valid.

    Parameter injeksi `snapshot`, `analysis_fn`, dan lain-lain memudahkan unit test.
    Dalam pemakaian biasa, semua fungsi otomatis memakai modul proyek.

    source='demo'    : satu skenario pesawat dibuat dari ORIGINAL sekali saja.
    source='opensky' : satu snapshot OpenSky dipakai ulang untuk semua kandidat.
    """
    if source not in {"demo", "opensky"}:
        raise ValueError("source harus 'demo' atau 'opensky'")
    if not isinstance(radius_km, (float, int)) or isinstance(radius_km, bool):
        raise ValueError("radius_km harus berupa angka")
    if not math.isfinite(radius_km) or not (1 <= radius_km <= MAX_SCAN_RADIUS_KM):
        raise ValueError("radius_km harus 1 sampai 150 km")
    if departure_epoch is not None and (
        not isinstance(departure_epoch, (int, float))
        or isinstance(departure_epoch, bool)
        or not math.isfinite(departure_epoch)
    ):
        raise ValueError("departure_epoch harus berupa Unix timestamp finite")

    # Simpan offset sekali agar generator dapat digunakan ulang setelah fetch OpenSky.
    offsets = tuple(offsets_m)
    fractions = tuple(bend_fractions) if bend_fractions is not None else None
    if analysis_fn is None:
        from cpa_api_service import analyze_flight_plan
        analysis_fn = analyze_flight_plan

    def generate(epoch: float) -> dict:
        return generate_route_candidates(
            start_lat=start_lat,
            start_lon=start_lon,
            end_lat=end_lat,
            end_lon=end_lon,
            altitude_m=altitude_m,
            speed_mps=speed_mps,
            time_step_s=time_step_s,
            offsets_m=offsets,
            bend_fraction=bend_fraction,
            bend_fractions=fractions,
            departure_time_utc=datetime.fromtimestamp(epoch, tz=timezone.utc),
        )

    epoch = (float(departure_epoch) if departure_epoch is not None
             else datetime.now(timezone.utc).timestamp())
    group = generate(epoch)
    cached = False
    center_lat = (start_lat + end_lat) / 2
    center_lon = (start_lon + end_lon) / 2
    required_scan_km = _required_scan_radius_km(group, center_lat, center_lon, radius_km)
    geographic_coverage_complete = required_scan_km <= MAX_SCAN_RADIUS_KM

    if snapshot is None:
        if source == "demo":
            if demo_builder is None:
                from cpa_api_service import make_demo_snapshot
                demo_builder = make_demo_snapshot
            snapshot = demo_builder(group["original_route"], epoch)
        else:
            if snapshot_provider is None:
                from aircraft_service import get_snapshot
                snapshot_provider = get_snapshot
            # Satu fetch per evaluasi, BUKAN satu fetch untuk setiap rute.
            snapshot, _, _, cached = snapshot_provider(
                center_lat, center_lon, min(required_scan_km, MAX_SCAN_RADIUS_KM)
            )
            if departure_epoch is None:
                # Waktu rencana keberangkatan diselaraskan setelah snapshot tiba.
                epoch = datetime.now(timezone.utc).timestamp()
                group = generate(epoch)

    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("states"), list):
        raise ValueError("Snapshot harus mempunyai daftar 'states' pesawat")
    if not isinstance(snapshot.get("time"), (int, float)):
        raise ValueError("Snapshot harus mempunyai timestamp Unix 'time'")

    plans = [group["original_route"]] + [c["flight_plan"] for c in group["candidates"]]
    results = []
    for plan in plans:
        analysis = analysis_fn(
            plan,
            snapshot,
            source=source,
            departure_epoch=epoch,
            coverage_complete=geographic_coverage_complete,
            cached=cached,
        )
        results.append(_result_summary(plan, analysis))

    baseline = results[0]
    candidates = []
    for metadata, result in zip(group["candidates"], results[1:]):
        candidate = {**result}
        candidate.update({
            "side": metadata["side"],
            "offset_m": metadata["offset_m"],
            "bend_fraction": metadata["bend_fraction"],
            "bend_point": metadata["bend_point"],
            "extra_distance_m": metadata["extra_distance_m"],
            "extra_duration_s": metadata["extra_duration_s"],
            "flight_plan": metadata["flight_plan"],
            "route_geojson": _route_geojson(metadata["flight_plan"]),
            "evaluation_status": (
                "ZERO_CONFLICT_CPA_CANDIDATE"
                if result["cpa_candidate_eligible"] else
                "POTENTIAL_CONFLICT" if result["potential_conflicts"] > 0 else
                "INCOMPLETE_ANALYSIS"
            ),
        })
        candidates.append(candidate)

    # Ranking hanya di antara kandidat dengan 0 konflik & analisis lengkap.
    eligible = sorted(
        (c for c in candidates if c["cpa_candidate_eligible"]),
        key=lambda c: (c["extra_distance_m"], c["extra_duration_s"], c["route_id"]),
    )

    chosen = None
    if baseline["potential_conflicts"] > 0 and baseline["data_quality_status"] == "COMPLETE_ANALYSIS" and baseline["route_coverage_complete"]:
        if eligible:
            chosen = eligible[0]
            outcome = "RECOMMENDATION_AVAILABLE"
        else:
            outcome = "NO_ELIGIBLE_ALTERNATIVE"
    elif baseline["cpa_candidate_eligible"]:
        outcome = "NO_REROUTE_NEEDED"
    else:
        outcome = "BASELINE_INCOMPLETE"

    return {
        "status": outcome,
        "source": source,
        "evaluation_mode": "PRE_FLIGHT_CPA_COMPARISON",
        "search_mode": group["search_mode"],
        "bend_fractions": group["bend_fractions"],
        "offsets_m": group["offsets_m"],
        "reference_departure_time_utc": datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(),
        "snapshot_time_utc": datetime.fromtimestamp(snapshot["time"], tz=timezone.utc).isoformat(),
        "cached_snapshot": cached,
        "aircraft_snapshot_count": len(snapshot["states"]),
        "monitoring_radius_km": float(radius_km),
        "required_scan_radius_km": round(required_scan_km, 2),
        "geographic_coverage_complete": geographic_coverage_complete,
        "original_route": {
            **baseline,
            "flight_plan": group["original_route"],
            "route_geojson": _route_geojson(group["original_route"]),
        },
        "candidate_count": len(candidates),
        "eligible_candidate_count": len(eligible),
        "recommended_route_id": chosen["route_id"] if chosen else None,
        "recommended_route": chosen,  # None jika belum ada yang memenuhi syarat
        "candidates": candidates,
        "decision_explanation": (
            "Ada kandidat dengan nol konflik terdeteksi, cakupan CPA lengkap, "
            "dan tambahan jarak terpendek di antara kandidat yang memenuhi syarat."
            if chosen else
            "Rute awal tidak menunjukkan konflik terdeteksi pada data yang lengkap; "
            "perubahan rute belum diperlukan menurut CPA simulasi."
            if outcome == "NO_REROUTE_NEEDED" else
            "Belum ada kandidat dengan nol konflik dan analisis lengkap. "
            "Perlu memperluas kandidat atau memperbaiki data, bukan mengklaim rute aman."
        ),
        "limitations": [
            "Hanya CPA simulasi, bukan jaminan keselamatan atau izin terbang",
            "Tidak memeriksa zona larangan, NOTAM, terrain, cuaca, dan batas manuver UAV",
            "Pesawat diasumsikan berkecepatan, berarah, dan berketinggian konstan",
            "OpenSky dapat memiliki data tidak lengkap/terlambat dan cakupan penerima terbatas",
            "Nol konflik hanya untuk data dan horizon prediksi yang dievaluasi",
            "Seluruh kandidat dibandingkan dengan snapshot dan epoch keberangkatan sama",
        ],
    }


if __name__ == "__main__":
    import json
    result = evaluate_route_candidates(
        offsets_m=ADAPTIVE_OFFSETS_M,
        bend_fractions=ADAPTIVE_BEND_FRACTIONS,
    )
    print("=== ADAPTIVE ROUTE EVALUATOR (DEMO) ===")
    print("Status:", result["status"])
    print("Pesawat pada snapshot:", result["aircraft_snapshot_count"])
    print("Baseline conflicts:", result["original_route"]["potential_conflicts"])
    for c in result["candidates"]:
        print(f"{c['route_id']:<23} | konflik={c['potential_conflicts']:<2} | "
              f"kualitas={c['data_quality_status']:<20} | "
              f"tambahan={c['extra_distance_m']:>8.2f} m | "
              f"{c['evaluation_status']}")
    print("Rekomendasi:", result["recommended_route_id"] or "BELUM ADA")
    with open("route_evaluation_adaptive_demo.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print("Laporan: route_evaluation_demo.json")
