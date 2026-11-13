/**
 * Tahap 7C.2: urutkan semua rute hasil CPA, tampilkan PALING BANYAK 6.
 * Semua kandidat tetap dievaluasi di backend memakai satu snapshot yang sama.
 * Tidak satu pun hasil ini berarti izin/jaminan keselamatan penerbangan.
 */

const validNumber = (value, fallback) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
};

function hasCompleteAnalysis(route) {
  return route?.data_quality_status === "COMPLETE_ANALYSIS" &&
    route?.route_coverage_complete === true &&
    validNumber(route?.aircraft_analyzed, 0) > 0;
}

/** Separasi horizontal terkecil dari pesawat yang diprediksi berkonflik. */
function minimumConflictCpa(route) {
  const cpaValues = (route.conflicts || [])
    .map((plane) => Number(plane.horizontal_cpa_m))
    .filter((value) => Number.isFinite(value) && value >= 0);
  return cpaValues.length ? Math.min(...cpaValues) : -1;
}

/**
 * Ranking:
 * 1. Hasil lengkap yang benar-benar lolos kriteria CPA (0 konflik).
 * 2. Hasil lengkap lain, jumlah konflik lebih sedikit lebih baik.
 * 3. Jika jumlah konflik sama dan >0: minimum CPA horizontal terbesar.
 * 4. Tambahan jarak dan waktu lebih kecil.
 * 5. Analisis belum lengkap selalu terakhir, sekalipun 0 konflik.
 */
export function selectBestRouteCandidates(candidates, limit = 6) {
  if (!Array.isArray(candidates)) return [];
  const safeLimit = Math.max(0, Math.floor(validNumber(limit, 6)));

  return [...candidates].sort((a, b) => {
    const classOf = (route) => {
      if (!hasCompleteAnalysis(route)) return 2;
      return route.cpa_candidate_eligible === true &&
        validNumber(route.potential_conflicts, Infinity) === 0 ? 0 : 1;
    };

    const tier = classOf(a) - classOf(b);
    if (tier !== 0) return tier;

    const aConflicts = validNumber(a.potential_conflicts, Infinity);
    const bConflicts = validNumber(b.potential_conflicts, Infinity);
    if (aConflicts !== bConflicts) return aConflicts - bConflicts;

    // Untuk yang masih konflik, jarak horizontal CPA lebih besar lebih baik
    // hanya sebagai pembanding di antara kandidat dengan jumlah konflik sama.
    if (classOf(a) === 1 && aConflicts > 0) {
      const cpaDiff = minimumConflictCpa(b) - minimumConflictCpa(a);
      if (cpaDiff !== 0) return cpaDiff;
    }

    const extraDistance = validNumber(a.extra_distance_m, Infinity) -
      validNumber(b.extra_distance_m, Infinity);
    if (extraDistance !== 0) return extraDistance;

    const extraTime = validNumber(a.extra_duration_s, Infinity) -
      validNumber(b.extra_duration_s, Infinity);
    if (extraTime !== 0) return extraTime;

    return String(a.route_id).localeCompare(String(b.route_id));
  }).slice(0, safeLimit);
}
