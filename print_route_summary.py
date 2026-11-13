"""Ringkas JSON Route Evaluator agar tidak perlu menyalin ribuan baris.

Contoh:
    python print_route_summary.py route_evaluation_adaptive_demo.json
"""
from __future__ import annotations
import json
import sys
from pathlib import Path


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "route_evaluation_adaptive_demo.json")
    if not path.is_file():
        raise SystemExit(f"File tidak ditemukan: {path}")
    with path.open(encoding="utf-8") as handle:
        report = json.load(handle)

    baseline = report.get("original_route", {})
    print("=== HASIL EVALUASI RUTE ADAPTIF ===")
    print("Status:", report.get("status"))
    print("Mode:", report.get("search_mode"))
    print("Konflik rute awal:", baseline.get("potential_conflicts"))
    print("Kandidat diuji:", report.get("candidate_count"))
    print("Kandidat lolos CPA:", report.get("eligible_candidate_count"))
    print("Rekomendasi:", report.get("recommended_route_id") or "BELUM ADA")
    print("Cakupan geografis lengkap:", report.get("geographic_coverage_complete"))
    print("-" * 95)
    for c in report.get("candidates", []):
        print(
            f"{c['route_id']:<22} | konflik={c['potential_conflicts']:<2} | "
            f"tambah={c['extra_distance_m']:>8.1f} m | "
            f"durasi={c['duration_s']:>7.1f} s | "
            f"{c['evaluation_status']}"
        )
    print("-" * 95)
    print("Catatan: nol konflik CPA bukan jaminan keselamatan atau izin terbang.")


if __name__ == "__main__":
    main()
