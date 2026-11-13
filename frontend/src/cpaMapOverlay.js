/*
 * CPA Map Overlay — visualisasi berbasis HASIL BACKEND, bukan hitung ulang CPA.
 * Masukkan file ini di frontend/src/cpaMapOverlay.js.
 * Warna merah = prediksi konflik pada snapshot CPA terakhir.
 */
import * as maplibregl from "maplibre-gl";

const empty = () => ({ type: "FeatureCollection", features: [] });

function feature(geometry, properties) {
  return { type: "Feature", geometry, properties };
}

function lonLat(point) {
  if (!point) return null;
  const lat = Number(point.latitude);
  const lon = Number(point.longitude);
  return Number.isFinite(lat) && Number.isFinite(lon)
    ? [lon, lat]
    : null;
}

function addLayerIfMissing(map, definition) {
  if (!map.getLayer(definition.id)) map.addLayer(definition);
}

/** Dipanggil setelah sumber "route" MapLibre tersedia. */
export function setupCpaOverlay(map) {
  if (!map?.getSource("route")) return;
  if (map.getSource("cpa-predicted-lines")) return;

  map.addSource("cpa-predicted-lines", { type: "geojson", data: empty() });
  map.addSource("cpa-connecting-lines", { type: "geojson", data: empty() });
  map.addSource("cpa-predicted-points", { type: "geojson", data: empty() });

  addLayerIfMissing(map, {
    id: "cpa-aircraft-track", type: "line", source: "cpa-predicted-lines",
    paint: { "line-color": "#dc2626", "line-width": 3,
      "line-opacity": 0.9, "line-dasharray": [2.5, 2] },
  });
  addLayerIfMissing(map, {
    id: "cpa-closest-link", type: "line", source: "cpa-connecting-lines",
    paint: { "line-color": "#f59e0b", "line-width": 2,
      "line-opacity": 0.9, "line-dasharray": [1, 2] },
  });
  addLayerIfMissing(map, {
    id: "cpa-point-drone", type: "circle", source: "cpa-predicted-points",
    filter: ["==", ["get", "point_role"], "drone_cpa"],
    paint: { "circle-radius": 8, "circle-color": "#2563eb",
      "circle-stroke-color": "#ffffff", "circle-stroke-width": 2.5 },
  });
  addLayerIfMissing(map, {
    id: "cpa-point-aircraft", type: "circle", source: "cpa-predicted-points",
    filter: ["==", ["get", "point_role"], "aircraft_cpa"],
    paint: { "circle-radius": 10, "circle-color": "#dc2626",
      "circle-opacity": 0.75, "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2.5 },
  });
  addLayerIfMissing(map, {
    id: "cpa-point-demo", type: "circle", source: "cpa-predicted-points",
    filter: ["==", ["get", "point_role"], "demo_aircraft_now"],
    paint: { "circle-radius": 9, "circle-color": "#ef4444",
      "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 },
  });

  // Popup secara aman: data callsign ditulis dengan textContent, bukan HTML.
  const popupOnClick = (event) => {
    const props = event.features?.[0]?.properties;
    if (!props) return;
    const container = document.createElement("div");
    container.style.cssText = "font:13px/1.6 Arial;max-width:270px";
    const rows = [
      `${props.callsign || "UNKNOWN"}${props.demo === "true" ? " — DATA SIMULASI" : ""}`,
      props.point_role === "demo_aircraft_now" ? "Pesawat demo pada awal analisis" :
        (props.point_role === "drone_cpa" ? "Posisi drone saat CPA" : "Posisi pesawat saat CPA"),
      `Menuju CPA: ${Number(props.time_to_cpa_s).toFixed(1)} detik`,
      `CPA horizontal: ${Number(props.horizontal_cpa_m).toFixed(1)} m`,
      `Selisih vertikal: ${Number(props.vertical_separation_m).toFixed(1)} m`,
      "Estimasi model arah/kecepatan konstan, bukan posisi live.",
    ];
    rows.forEach((str, i) => {
      const line = document.createElement(i === 0 ? "strong" : "div");
      line.textContent = str;
      container.appendChild(line);
    });
    new maplibregl.Popup({ offset: 14 })
      .setLngLat(event.lngLat)
      .setDOMContent(container)
      .addTo(map);
  };
  for (const layerId of ["cpa-point-drone", "cpa-point-aircraft", "cpa-point-demo"]) {
    map.on("click", layerId, popupOnClick);
    map.on("mouseenter", layerId, () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", layerId, () => { map.getCanvas().style.cursor = ""; });
  }
}

/**
 * Sinkronkan geometry dan warna marker sesuai TAB CPA yang terlihat.
 * Jangan pakai hasil CPA yang sumbernya tidak sesuai selector.
 */
export function syncCpaOverlay(map, result, aircraftMarkers, selectedSource) {
  if (!map?.getSource("route")) return;
  setupCpaOverlay(map);

  const validResult = result?.source === selectedSource ? result : null;
  const conflicts = validResult?.conflicts || [];
  const conflictIds = new Set(
    conflicts.filter((x) => x.potential_conflict === true)
      .map((x) => String(x.icao24 || "").trim().toLowerCase())
      .filter(Boolean)
  );

  // Jika demo, JANGAN mewarnai pesawat asli OpenSky.
  for (const { marker, plane } of aircraftMarkers.values()) {
    const icao = String(plane.icao24 || "").trim().toLowerCase();
    const warning = selectedSource === "opensky" && conflictIds.has(icao);
    const element = marker.getElement();
    element.classList.toggle("conflict-aircraft", warning);
    element.title = warning
      ? `POTENSI KONFLIK (snapshot CPA): ${plane.callsign || icao}`
      : (plane.callsign || "UNKNOWN");
  }

  const trackFeatures = [];
  const linkFeatures = [];
  const pointFeatures = [];

  for (const item of (validResult?.conflict_visualizations || []).slice(0, 12)) {
    const drone = lonLat(item.drone_at_cpa);
    const aircraft = lonLat(item.aircraft_at_cpa);
    const now = lonLat(item.aircraft_at_analysis);
    const track = item.predicted_track_lonlat;
    if (!drone || !aircraft || !now || !Array.isArray(track)) continue;

    const props = {
      icao24: item.icao24 || "",
      callsign: item.callsign || "UNKNOWN",
      time_to_cpa_s: Number(item.time_to_cpa_s),
      horizontal_cpa_m: Number(item.horizontal_cpa_m),
      vertical_separation_m: Number(item.vertical_separation_m),
      demo: selectedSource === "demo" ? "true" : "false",
    };

    if (track.length >= 2) {
      trackFeatures.push(feature({ type: "LineString", coordinates: track }, props));
    }
    linkFeatures.push(feature({ type: "LineString", coordinates: [drone, aircraft] }, props));
    pointFeatures.push(feature({ type: "Point", coordinates: drone }, { ...props, point_role: "drone_cpa" }));
    pointFeatures.push(feature({ type: "Point", coordinates: aircraft }, { ...props, point_role: "aircraft_cpa" }));

    // Pada Demo, tunjukkan posisi pesawat sintetis tanpa mengaku sebagai OpenSky.
    if (selectedSource === "demo") {
      pointFeatures.push(feature({ type: "Point", coordinates: now }, { ...props, point_role: "demo_aircraft_now" }));
    }
  }

  map.getSource("cpa-predicted-lines")?.setData({ ...empty(), features: trackFeatures });
  map.getSource("cpa-connecting-lines")?.setData({ ...empty(), features: linkFeatures });
  map.getSource("cpa-predicted-points")?.setData({ ...empty(), features: pointFeatures });
}
