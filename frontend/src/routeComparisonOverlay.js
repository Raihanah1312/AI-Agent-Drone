/**
 * Tahap 7B.3: visualisasi SATU kandidat rute pada MapLibre.
 * Hanya menggambar hasil evaluasi CPA dari backend.
 * Hijau = kandidat lolos kriteria CPA terbatas (BUKAN izin/rute aman).
 * Oranye = masih terdapat potensi konflik.
 * Abu-abu = penilaian tidak lengkap.
 */
const SOURCE_ID = "route-comparison-source";
const LINE_ID = "route-comparison-line";

function emptyCollection() {
  return { type: "FeatureCollection", features: [] };
}

function validLine(feature) {
  return feature?.type === "Feature" &&
    feature.geometry?.type === "LineString" &&
    Array.isArray(feature.geometry.coordinates) &&
    feature.geometry.coordinates.length >= 2 &&
    feature.geometry.coordinates.every((position) =>
      Array.isArray(position) && position.length >= 2 &&
      Number.isFinite(position[0]) && Number.isFinite(position[1]));
}

export function syncRouteComparisonOverlay(map, evaluation, candidate) {
  if (!map || !map.getSource("route")) return;

  if (!map.getSource(SOURCE_ID)) {
    map.addSource(SOURCE_ID, { type: "geojson", data: emptyCollection() });
  }
  if (!map.getLayer(LINE_ID)) {
    map.addLayer({
      id: LINE_ID,
      type: "line",
      source: SOURCE_ID,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": ["get", "color"],
        "line-width": 5,
        "line-dasharray": [2, 1.5],
        "line-opacity": 0.95,
      },
    });
  }

  const originalConflicts = Boolean(evaluation?.original_route?.potential_conflicts > 0);
  // Rute asli berubah merah hanya saat ada hasil evaluasi baseline yang relevan.
  map.setPaintProperty(
    "route-line", "line-color",
    evaluation && originalConflicts ? "#ef4444" : "#13b8f5"
  );
  map.setPaintProperty(
    "route-line", "line-dasharray",
    evaluation && originalConflicts ? [2, 1.5] : [1, 0]
  );

  const eligible = candidate?.cpa_candidate_eligible === true;
  const inConflict = (candidate?.potential_conflicts ?? 0) > 0;
  const color = eligible ? "#22c55e" : inConflict ? "#fb923c" : "#94a3b8";
  const feature = candidate?.route_geojson;
  const source = map.getSource(SOURCE_ID);
  source.setData(
    evaluation && validLine(feature)
      ? {
          type: "FeatureCollection",
          features: [{
            ...feature,
            properties: { ...(feature.properties || {}), color },
          }],
        }
      : emptyCollection()
  );
}
