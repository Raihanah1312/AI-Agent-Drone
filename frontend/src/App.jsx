import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";
import "./App.css";
import { syncCpaOverlay } from "./cpaMapOverlay";
import { syncRouteComparisonOverlay } from "./routeComparisonOverlay";
import { selectBestRouteCandidates } from "./routeRanking";

maplibregl.setWorkerUrl(workerUrl);

const API = "http://127.0.0.1:8000";
const MAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";
const INITIAL_FORM = {
  start_lat: "-6.1754", start_lon: "106.8272",
  end_lat: "-6.1600", end_lon: "106.8500",
  altitude_m: "150", speed_mps: "10", time_step_s: "30",
};

const DRONE_SVG = `
<svg viewBox="0 0 64 64" width="38" height="38" aria-hidden="true">
  <g fill="none" stroke="#e0f2fe" stroke-width="5" stroke-linecap="round">
    <path d="M25 26 L13 14 M39 26 L51 14 M25 38 L13 50 M39 38 L51 50"/>
  </g>
  <g fill="#38bdf8" stroke="#fff" stroke-width="3">
    <circle cx="11" cy="12" r="8"/><circle cx="53" cy="12" r="8"/>
    <circle cx="11" cy="52" r="8"/><circle cx="53" cy="52" r="8"/>
  </g>
  <rect x="22" y="22" width="20" height="20" rx="6"
    fill="#0369a1" stroke="#fff" stroke-width="3"/>
  <circle cx="32" cy="32" r="4" fill="#fff"/>
</svg>`;

function droneAtTime(points, t) {
  if (!points?.length) return null;
  if (t <= 0) return points[0];
  const last = points[points.length - 1];
  if (t >= last.elapsed_s) return last;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    if (t <= b.elapsed_s) {
      const f = (t - a.elapsed_s) / (b.elapsed_s - a.elapsed_s);
      return {
        latitude: a.latitude + (b.latitude - a.latitude) * f,
        longitude: a.longitude + (b.longitude - a.longitude) * f,
        altitude_m: a.altitude_m + (b.altitude_m - a.altitude_m) * f,
      };
    }
  }
  return last;
}

function monitoringCircle(lat, lon, radiusKm) {
  const lat1 = lat * Math.PI / 180;
  const lon1 = lon * Math.PI / 180;
  const ang = radiusKm / 6371;
  const coordinates = [];
  for (let i = 0; i <= 96; i++) {
    const bearing = i * 2 * Math.PI / 96;
    const lat2 = Math.asin(
      Math.sin(lat1) * Math.cos(ang) +
      Math.cos(lat1) * Math.sin(ang) * Math.cos(bearing)
    );
    const lon2 = lon1 + Math.atan2(
      Math.sin(bearing) * Math.sin(ang) * Math.cos(lat1),
      Math.cos(ang) - Math.sin(lat1) * Math.sin(lat2)
    );
    coordinates.push([lon2 * 180 / Math.PI, lat2 * 180 / Math.PI]);
  }
  return {
    type: "Feature", properties: { radius_km: radiusKm },
    geometry: { type: "Polygon", coordinates: [coordinates] },
  };
}

// Pergerakan antar-snapshot: hanya untuk animasi peta, bukan CPA.
function displayPosition(plane, nowSeconds) {
  const lat = Number(plane.latitude), lon = Number(plane.longitude);
  const speed = Number(plane.velocity_mps);
  const heading = Number(plane.true_track_deg);
  const contact = Number(plane.last_contact_unix);
  if (
    plane.on_ground || plane.velocity_mps == null ||
    plane.true_track_deg == null || !Number.isFinite(speed) ||
    !Number.isFinite(heading) || !Number.isFinite(contact) ||
    contact <= 0 || speed <= 0
  ) return [lon, lat];
  const dt = Math.max(0, Math.min(35, nowSeconds - contact));
  const d = speed * dt / 6371000;
  const b = heading * Math.PI / 180;
  const phi = lat * Math.PI / 180;
  const lambda = lon * Math.PI / 180;
  const phi2 = Math.asin(
    Math.sin(phi) * Math.cos(d) +
    Math.cos(phi) * Math.sin(d) * Math.cos(b)
  );
  const lambda2 = lambda + Math.atan2(
    Math.sin(b) * Math.sin(d) * Math.cos(phi),
    Math.cos(d) - Math.sin(phi) * Math.sin(phi2)
  );
  return [((lambda2 * 180 / Math.PI + 540) % 360) - 180,
    phi2 * 180 / Math.PI];
}

function fitRoute(map, plan, aircraft = []) {
  if (!map || !plan?.waypoints?.length) return;
  const bounds = new maplibregl.LngLatBounds();
  for (const p of plan.waypoints) bounds.extend([p.longitude, p.latitude]);
  for (const p of aircraft) {
    if (Number.isFinite(p.latitude) && Number.isFinite(p.longitude)) {
      bounds.extend([p.longitude, p.latitude]);
    }
  }
  const ne = bounds.getNorthEast(), sw = bounds.getSouthWest();
  if (ne.lat === sw.lat && ne.lng === sw.lng) {
    map.easeTo({ center: bounds.getCenter(), zoom: 13, duration: 400 });
  } else {
    map.fitBounds(bounds, { padding: 65, maxZoom: 13, duration: 600 });
  }
}

function fitRadius(map, position, radiusKm) {
  if (!map || !position) return;
  const bounds = new maplibregl.LngLatBounds();
  const circle = monitoringCircle(position.latitude, position.longitude, radiusKm);
  for (const p of circle.geometry.coordinates[0]) bounds.extend(p);
  map.fitBounds(bounds, { padding: 45, duration: 600 });
}

function formatTime(iso) {
  if (!iso) return "-";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("id-ID", { timeZone: "Asia/Jakarta" }) + " WIB";
}

function formatMeters(value) {
  if (value == null || !Number.isFinite(Number(value))) return "-";
  return Number(value).toLocaleString("id-ID", {
    maximumFractionDigits: 1,
  }) + " m";
}

function drawAircraft(map, planes, markers) {
  for (const item of markers.values()) item.marker.remove();
  markers.clear();
  planes.forEach((p, index) => {
    if (!Number.isFinite(p.latitude) || !Number.isFinite(p.longitude)) return;
    const el = document.createElement("div");
    el.className = `aircraft-marker ${p.in_radius ? "" : "outside-range"}`;
    el.textContent = "✈";
    el.title = p.callsign || "UNKNOWN";
    const content = document.createElement("div");
    content.className = "plane-popup";
    const title = document.createElement("strong");
    title.textContent = p.callsign || "UNKNOWN";
    content.appendChild(title);
    const rows = [
      `ICAO24: ${p.icao24 || "-"}`,
      `Ketinggian barometrik: ${p.altitude_m ?? "-"} m`,
      `Kecepatan: ${p.velocity_mps ?? "-"} m/s`,
      `Arah: ${p.true_track_deg ?? "-"}°`,
      `Jarak dari pusat scan: ${p.distance_km ?? "-"} km`,
      `Dalam radius saat scan: ${p.in_radius ? "YA" : "TIDAK"}`,
      "Animasi posisi hanya estimasi visual",
    ];
    for (const lineText of rows) {
      const line = document.createElement("div");
      line.textContent = lineText;
      content.appendChild(line);
    }
    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([p.longitude, p.latitude])
      .setPopup(new maplibregl.Popup({ offset: 18 }).setDOMContent(content))
      .addTo(map);
    markers.set(`${p.icao24 || "unknown"}-${index}`, { marker, plane: p });
  });
}

function statusLabel(result) {
  const status = result?.analysis_status;
  if (!status) return "BELUM DIANALISIS";
  if (status === "POTENTIAL_CONFLICT") return "POTENSI KONFLIK";
  if (status === "INCOMPLETE_ANALYSIS") return "DATA BELUM LENGKAP";
  if (status === "NO_CONFLICT_DETECTED") return "TIDAK TERDETEKSI";
  if (status === "MISSION_COMPLETED") return "MISI SELESAI";
  return status;
}

function CpaResult({ result, loading, error, hint, isFlight, liveStatus, receivedAt }) {
  const nearest = result?.conflicts?.[0] || result?.closest_approaches?.[0];
  const incomplete = result?.data_quality_status === "INCOMPLETE_ANALYSIS";
  const reasons = Object.entries((result?.skipped || []).reduce((acc, p) => {
    acc[p.reason || "OTHER"] = (acc[p.reason || "OTHER"] || 0) + 1;
    return acc;
  }, {}));

  return (
    <>
      {hint && <p className="cpa-hint">{hint}</p>}
      {isFlight && result && !liveStatus && (
        <div className="cpa-history-note">
          Hasil ini adalah snapshot sebelumnya, bukan peringatan kondisi terkini.
          Marker merah dan garis CPA sementara disembunyikan hingga analisis baru tersedia.
        </div>
      )}
      {error && <p className="error-text">CPA: {error}</p>}
      {loading && <p className="cpa-empty">Menghitung prediksi dan CPA...</p>}

      {!result && !loading && !error && (
        <p className="cpa-empty">
          {isFlight
            ? "Tekan Start untuk mengaktifkan pemantauan sisa rute."
            : "Klik Generate Flight Plan untuk melakukan pre-flight CPA."}
        </p>
      )}

      {result && (
        <>
          <div className="cpa-metrics compact">
            <div className="cpa-metric-line">
              <span className="metric-label">
                {isFlight && !liveStatus ? "Konflik saat scan" : "Potensi konflik"}
              </span>
              <strong className="metric-value">{result.potential_conflicts ?? "-"}</strong>
            </div>

            <div className="cpa-metric-line">
              <span className="metric-label">Dianalisis</span>
              <strong className="metric-value">
                {result.aircraft_analyzed ?? "-"}/{result.aircraft_received ?? "-"}
              </strong>
            </div>

            <div className="cpa-metric-line">
              <span className="metric-label">Dilewati</span>
              <strong className="metric-value">{result.aircraft_skipped ?? "-"}</strong>
            </div>

            <div className="cpa-metric-line">
              <span className="metric-label">Kualitas data</span>
              <strong className="metric-value">
                {incomplete
                  ? "Belum lengkap"
                  : result.analysis_status === "MISSION_COMPLETED"
                  ? "Misi selesai"
                  : "Lengkap"}
              </strong>
            </div>
          </div>

          <div
            className={`cpa-summary ${
              isFlight && !liveStatus
                ? "cpa-historical"
                : result.potential_conflicts > 0
                ? "cpa-danger"
                : incomplete
                ? "cpa-warning"
                : "cpa-ok"
            }`}
          >
            {isFlight && !liveStatus
              ? "Hasil CPA terakhir disimpan sebagai riwayat. Perbarui analisis untuk mengetahui kondisi terkini."
              : result.analysis_status === "MISSION_COMPLETED"
              ? "Misi simulasi selesai. Pemantauan sisa rute dihentikan."
              : result.potential_conflicts > 0
              ? `Ada ${result.potential_conflicts} potensi konflik berdasarkan data yang dianalisis.`
              : incomplete
              ? "Tidak ditemukan konflik pada data yang dianalisis, tetapi data belum lengkap. Bukan pernyataan aman."
              : "Tidak ditemukan konflik dalam data dan horizon prediksi yang dianalisis."}
          </div>

          {nearest && (
            <div className="cpa-nearest cpa-nearest-card">
              <div className="cpa-nearest-title">
                {nearest.potential_conflict ? "Pesawat berpotensi konflik" : "CPA terdekat"}:{" "}
                <strong>{nearest.callsign || "UNKNOWN"}</strong>
              </div>

              <div className="cpa-nearest-grid">
                <span>Horizontal: {formatMeters(nearest.horizontal_cpa_m)}</span>
                <span>Vertikal: {formatMeters(nearest.vertical_separation_m)}</span>
                <span>Menuju CPA: {Number(nearest.time_to_cpa_s).toFixed(1)} s</span>
              </div>
            </div>
          )}

          {result.aircraft_skipped > 0 && (
            <details className="cpa-skipped">
              <summary>{result.aircraft_skipped} pesawat dilewati — lihat alasan</summary>
              {reasons.map(([reason, count]) => (
                <p key={reason}>
                  {reason}: {count} pesawat
                </p>
              ))}
            </details>
          )}

          <small className="cpa-footnote">
            {receivedAt ? `Diterima: ${formatTime(new Date(receivedAt).toISOString())} · ` : ""}
            Sumber: {result.source === "demo" ? "Demo sintetis" : "OpenSky"} · Snapshot:{" "}
            {formatTime(result.snapshot_time_utc)}
            {isFlight &&
              ` · Posisi simulasi saat scan: ${Number(
                result.simulation_elapsed_s || 0
              ).toFixed(1)} s; sisa misi ${Number(
                result.remaining_duration_s || 0
              ).toFixed(1)} s.`}
            {" · "}Hasil CPA adalah prediksi dari snapshot analisis, bukan posisi live. Bukan izin atau jaminan keselamatan penerbangan.
          </small>
        </>
      )}
    </>
  );
}

function App() {
  const mapDiv = useRef(null);
  const mapRef = useRef(null);
  const droneMarkerRef = useRef(null);
  const aircraftMarkersRef = useRef(new Map());
  const trafficRef = useRef([]);
  const pickModeRef = useRef(null);
  const draftMarkersRef = useRef({ start: null, destination: null });
  const lastFrameRef = useRef(null);
  const lastCircleRef = useRef({ time: 0, radius: 70 });
  const elapsedRef = useRef(0);
  const radiusRef = useRef(70);
  const appliedMissionRef = useRef(null);
  const originalSimulationRef = useRef(null);
  const inflightAdviceAbortRef = useRef(null);
  const inflightAdvisedSignatureRef = useRef("");
  const inflightLastAiTimeRef = useRef(0);
  const preflightAbortRef = useRef(null);
  const preflightSequenceRef = useRef(0);

  const [plan, setPlan] = useState(null);
  const [form, setForm] = useState(INITIAL_FORM);
  const [formError, setFormError] = useState("");
  const [creating, setCreating] = useState(false);
  const [pickMode, setPickMode] = useState(null);
  const [draftNotice, setDraftNotice] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [flightStarted, setFlightStarted] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [radiusKm, setRadiusKm] = useState(70);
  const [radiusInput, setRadiusInput] = useState("70");
  const [refreshSeconds, setRefreshSeconds] = useState(30);
  const [scanNonce, setScanNonce] = useState(0);
  const [traffic, setTraffic] = useState(null);
  const [trafficError, setTrafficError] = useState("");
  const [trafficLoading, setTrafficLoading] = useState(false);

  // CPA: dua panel terpisah, sehingga pre-flight tidak tertimpa hasil in-flight.
  const [advisorTab, setAdvisorTab] = useState("preflight");
  const [analysisSource, setAnalysisSource] = useState("demo");
  const [preflight, setPreflight] = useState(null);
  const [preflightMeta, setPreflightMeta] = useState(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [preflightError, setPreflightError] = useState("");
  const [inflight, setInflight] = useState(null);
  const [inflightLoading, setInflightLoading] = useState(false);
  const [inflightError, setInflightError] = useState("");
  const [inflightMeta, setInflightMeta] = useState(null);
  // Jam UI untuk otomatis menandai hasil CPA yang sudah kedaluwarsa.
  const [nowMs, setNowMs] = useState(Date.now());

  // Tahap 7B.3: evaluasi rute alternatif, terpisah dari CPA pre/in-flight.
  const routeAbortRef = useRef(null);
  const [routeEvaluation, setRouteEvaluation] = useState(null);
  const [routeMeta, setRouteMeta] = useState(null);
  const [routeLoading, setRouteLoading] = useState(false);
  const [routeError, setRouteError] = useState("");
  const [selectedRouteId, setSelectedRouteId] = useState(null);

  // Tahap 8A — Hermes hanya menjelaskan hasil CPA; bukan kalkulator atau pilot.
  const hermesAbortRef = useRef(null);
  const [hermesAdvice, setHermesAdvice] = useState(null);
  const [hermesMeta, setHermesMeta] = useState(null);
  const [hermesLoading, setHermesLoading] = useState(false);
  const [hermesError, setHermesError] = useState("");

  // Tahap 8B: Hermes mengusulkan tool; Python mengevaluasi CPA sebenarnya.
  const agentPlanAbortRef = useRef(null);
  const [agentPlanResult, setAgentPlanResult] = useState(null);
  const [agentPlanMeta, setAgentPlanMeta] = useState(null);
  const [agentPlanLoading, setAgentPlanLoading] = useState(false);
  const [agentPlanError, setAgentPlanError] = useState("");
  const [agentSelectedId, setAgentSelectedId] = useState(null);
  const [applyingAgent, setApplyingAgent] = useState(false);
  const [appliedMitigation, setAppliedMitigation] = useState(null);
  const [inflightAdvice, setInflightAdvice] = useState(null);
  const [inflightAdviceError, setInflightAdviceError] = useState("");
  const [inflightAdviceLoading, setInflightAdviceLoading] = useState(false);

  function clearAgentPlan() {
    agentPlanAbortRef.current?.abort();
    setAgentPlanResult(null);
    setAgentPlanMeta(null);
    setAgentPlanLoading(false);
    setAgentPlanError("");
    setAgentSelectedId(null);
  }


  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const parsedRadius = Number(radiusInput);
  const radiusValid = radiusInput.trim() !== "" &&
    Number.isFinite(parsedRadius) && parsedRadius >= 1 && parsedRadius <= 150;
  function applyRadius() {
    if (radiusValid) setRadiusKm(parsedRadius);
  }

  const duration = plan?.mission.duration_s ?? 0;
  const progress = duration > 0 ? Math.min(100, elapsed / duration * 100) : 0;
  const current = plan ? droneAtTime(plan.waypoints, elapsed) : null;
  const traveled = (plan?.mission.distance_m || 0) * progress / 100;
  const status = !plan ? "LOADING" : playing ? "FLYING" :
    duration > 0 && elapsed >= duration ? "COMPLETED" :
    elapsed > 0 ? "PAUSED" : "READY";
  elapsedRef.current = elapsed;
  radiusRef.current = radiusKm;

  // ==============================================
  // DEFAULT PLAN
  // ==============================================
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API}/api/flight-plan`, { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(`Flight plan HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        const m = data.mission;
        const payload = {
          start_lat: m.start[0], start_lon: m.start[1],
          end_lat: m.destination[0], end_lon: m.destination[1],
          altitude_m: m.altitude_m, speed_mps: m.speed_mps,
          time_step_s: m.time_step_s,
        };
        appliedMissionRef.current = payload;
        setForm(Object.fromEntries(Object.entries(payload).map(
          ([key, value]) => [key, String(value)]
        )));
        setPlan(data);
      })
      .catch((e) => { if (e.name !== "AbortError") setFormError(e.message); });
    return () => controller.abort();
  }, []);

  useEffect(() => () => {
    preflightSequenceRef.current += 1;
    preflightAbortRef.current?.abort();
    routeAbortRef.current?.abort();
    hermesAbortRef.current?.abort();
    agentPlanAbortRef.current?.abort();
    inflightAdviceAbortRef.current?.abort();
  }, []);

  // ==============================================
  // PRE-FLIGHT CPA (on Generate / manual)
  // ==============================================
  async function runPreflight(payload, source, radius) {
    if (!payload) return;
    preflightAbortRef.current?.abort();
    const controller = new AbortController();
    preflightAbortRef.current = controller;
    const sequence = ++preflightSequenceRef.current;
    // Analisis baseline baru membatalkan hasil perbandingan rute yang lama.
    clearAgentPlan();
    hermesAbortRef.current?.abort();
    setHermesAdvice(null);
    setHermesMeta(null);
    setHermesLoading(false);
    setHermesError("");
    routeAbortRef.current?.abort();
    setRouteEvaluation(null);
    setRouteMeta(null);
    setRouteLoading(false);
    setRouteError("");
    setSelectedRouteId(null);
    setPreflight(null);
    setPreflightMeta(null);
    setPreflightError("");
    setPreflightLoading(true);
    try {
      const response = await fetch(`${API}/api/conflict-analysis`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...payload, source, radius_km: radius }),
        signal: controller.signal,
      });
      const body = await response.json();
      if (!response.ok) throw new Error(
        typeof body.detail === "string" ? body.detail : `CPA HTTP ${response.status}`
      );
      if (sequence === preflightSequenceRef.current) {
        setPreflight(body);
        setPreflightMeta({ source, radius });
      }
    } catch (e) {
      if (sequence === preflightSequenceRef.current && e.name !== "AbortError") {
        setPreflightError(e.message);
      }
    } finally {
      if (sequence === preflightSequenceRef.current) setPreflightLoading(false);
    }
  }

  async function createPlan(event) {
    event.preventDefault();
    setFormError("");
    if (!radiusValid) {
      setFormError("Radius harus 1–150 km.");
      return;
    }
    const payload = {};
    for (const [key, value] of Object.entries(form)) {
      if (!value.trim() || !Number.isFinite(Number(value))) {
        setFormError(`Input ${key} belum valid.`);
        return;
      }
      payload[key] = Number(value);
    }
    setCreating(true);
    originalSimulationRef.current = null;
    setAppliedMitigation(null);
    clearAgentPlan();
    hermesAbortRef.current?.abort();
    setHermesAdvice(null);
    setHermesMeta(null);
    setHermesLoading(false);
    setHermesError("");
    routeAbortRef.current?.abort();
    setRouteEvaluation(null);
    setRouteMeta(null);
    setRouteLoading(false);
    setRouteError("");
    setSelectedRouteId(null);
    preflightSequenceRef.current += 1;
    preflightAbortRef.current?.abort();
    setPreflight(null);
    setPreflightError("");
    setInflight(null);
    setInflightMeta(null);
    setInflightError("");
    setInflightAdvice(null);
    setInflightAdviceError("");
    inflightAdvisedSignatureRef.current = "";
    try {
      const response = await fetch(`${API}/api/flight-plan`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(
        typeof body.detail === "string" ? body.detail : `Flight plan HTTP ${response.status}`
      );
      setPlaying(false);
      setFlightStarted(false);
      setElapsed(0);
      elapsedRef.current = 0;
      lastFrameRef.current = null;
      setRadiusKm(parsedRadius);
      setPickMode(null);
      pickModeRef.current = null;
      setDraftNotice("");
      setTraffic(null);
      trafficRef.current = [];
      appliedMissionRef.current = payload;
      setAdvisorTab("preflight");
      setPlan(body);
      void runPreflight(payload, analysisSource, parsedRadius);
    } catch (e) {
      setFormError(e.message);
    } finally {
      setCreating(false);
    }
  }

  async function evaluateAlternatives() {
    if (appliedMitigation || !plan || !appliedMissionRef.current || missionChanged || flightStarted ||
        preflightOutdated || !radiusValid || parsedRadius !== radiusKm ||
        routeLoading || preflightLoading) return;

    routeAbortRef.current?.abort();
    clearAgentPlan();
    hermesAbortRef.current?.abort();
    setHermesAdvice(null);
    setHermesMeta(null);
    setHermesLoading(false);
    setHermesError("");
    const controller = new AbortController();
    routeAbortRef.current = controller;
    setRouteLoading(true);
    setRouteError("");
    setRouteEvaluation(null);
    setRouteMeta(null);
    setSelectedRouteId(null);
    try {
      const response = await fetch(`${API}/api/route-recommendation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          ...appliedMissionRef.current,
          radius_km: radiusKm,
          source: analysisSource,
          // Backend menguji semua 30; frontend hanya menampilkan 6 yang terbaik.
          offsets_m: [500, 1000, 1500, 2000, 2500],
          bend_fractions: [0.3, 0.5, 0.7],
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        const detail = body?.detail;
        const message = typeof detail === "string" ? detail : `Evaluasi HTTP ${response.status}`;
        throw new Error(message);
      }
      if (!controller.signal.aborted) {
        setRouteEvaluation(body);
        setRouteMeta({ plan, source: analysisSource, radius: radiusKm });
        // Jangan memilih jalur belum layak sebagai rekomendasi otomatis.
        const shortlist = selectBestRouteCandidates(body.candidates, 6);
        const eligibleId = shortlist.some((item) => item.route_id === body.recommended_route_id)
          ? body.recommended_route_id : null;
        setSelectedRouteId(eligibleId);
      }
    } catch (error) {
      if (!controller.signal.aborted) setRouteError(error.message);
    } finally {
      if (!controller.signal.aborted) setRouteLoading(false);
    }
  }

  async function requestAgentPlan() {
    if (appliedMitigation || !routeResultShown || !appliedMissionRef.current || flightStarted ||
        agentPlanLoading || creating || routeLoading || preflightLoading ||
        missionChanged || preflightOutdated) return;
    agentPlanAbortRef.current?.abort();
    const controller = new AbortController();
    agentPlanAbortRef.current = controller;
    setAgentPlanLoading(true);
    setAgentPlanError("");
    setAgentPlanResult(null);
    setAgentPlanMeta(null);
    setAgentSelectedId(null);
    setSelectedRouteId(null); // Hapus pratinjau ranking lama selama evaluasi agent.
    try {
      const response = await fetch(`${API}/api/agent-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          ...appliedMissionRef.current,
          radius_km: radiusKm,
          source: analysisSource,
          max_steps: 3,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(typeof body.detail === "string"
          ? body.detail : `Agent Planner HTTP ${response.status}`);
      }
      if (!controller.signal.aborted) {
        setAgentPlanResult(body);
        setAgentPlanMeta({ plan, source: analysisSource,
          radius: radiusKm, evaluation: routeResultShown });
        const suggestion = body.recommended_action;
        // Pilih otomatis aksi rekomendasi, termasuk altitude dan delay.
        setAgentSelectedId(suggestion?.attempt_id || null);
      }
    } catch (error) {
      if (!controller.signal.aborted && error.name !== "AbortError") {
        setAgentPlanError(error.message);
      }
    } finally {
      if (!controller.signal.aborted) setAgentPlanLoading(false);
    }
  }

  function previewAgentAttempt(attempt) {
    setAgentSelectedId(attempt.attempt_id);
    setSelectedRouteId(null);
    if (attempt?.route_geojson?.geometry?.coordinates) {
      const map = mapRef.current;
      const coordinates = attempt.route_geojson.geometry.coordinates;
      if (map?.getSource("route")) {
        const bounds = new maplibregl.LngLatBounds();
        for (const [lon, lat] of coordinates) bounds.extend([lon, lat]);
        map.fitBounds(bounds, { padding: 65, maxZoom: 13, duration: 500 });
      }
    }
  }

  async function applyAgentToSimulation() {
    const attempt = selectedAgentAttempt;
    if (!attempt || !agentPlanShown || flightStarted || playing || applyingAgent) return;
    if (attempt.cpa_candidate_eligible !== true ||
        attempt.data_quality_status !== "COMPLETE_ANALYSIS" ||
        attempt.route_coverage_complete !== true ||
        agentPlanShown.geographic_coverage_complete !== true) {
      setAgentPlanError("Hanya kandidat yang lolos CPA dengan data lengkap yang dapat diterapkan ke simulasi.");
      return;
    }
    if (!Array.isArray(attempt.control_points) || attempt.control_points.length < 2) {
      setAgentPlanError("Waypoint hasil Hermes tidak ditemukan. Evaluasi ulang sebelum menerapkan.");
      return;
    }
    const previousPlan = plan;
    const previousPayload = { ...appliedMissionRef.current };
    const payload = {
      ...previousPayload,
      altitude_m: Number(attempt.altitude_m),
      control_points: attempt.control_points,
      delay_s: Number(attempt.delay_s || 0),
      // Kunci skenario Demo pada pesawat yang dibentuk dari rencana asli.
      demo_reference_altitude_m: Number(previousPayload.altitude_m),
      demo_reference_control_points: previousPlan?.mission?.control_points || [
        [Number(previousPayload.start_lat), Number(previousPayload.start_lon)],
        [Number(previousPayload.end_lat), Number(previousPayload.end_lon)],
      ],
    };
    setApplyingAgent(true);
    setAgentPlanError("");
    try {
      const response = await fetch(`${API}/api/flight-plan`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(
        typeof body.detail === "string" ? body.detail : `Menerapkan plan HTTP ${response.status}`
      );
      if (!originalSimulationRef.current) {
        originalSimulationRef.current = { plan: previousPlan, payload: previousPayload };
      }
      setPlaying(false);
      setFlightStarted(false);
      setElapsed(0);
      elapsedRef.current = 0;
      lastFrameRef.current = null;
      setInflight(null);
      setInflightMeta(null);
      setInflightError("");
      setInflightAdvice(null);
      setInflightAdviceError("");
      inflightAdvisedSignatureRef.current = "";
      appliedMissionRef.current = payload;
      setForm((prev) => ({ ...prev, altitude_m: String(attempt.altitude_m) }));
      setPlan(body);
      setAdvisorTab("preflight");
      setAppliedMitigation({
        attempt_id: attempt.attempt_id,
        tool: attempt.tool,
        altitude_m: Number(attempt.altitude_m),
        delay_s: Number(attempt.delay_s || 0),
        status: "MENGHITUNG ULANG CPA",
      });
      void runPreflight(payload, analysisSource, radiusKm);
    } catch (error) {
      setAgentPlanError(error.message);
    } finally {
      setApplyingAgent(false);
    }
  }

  function restoreOriginalSimulation() {
    const original = originalSimulationRef.current;
    if (!original || playing || flightStarted) return;
    setPlaying(false);
    setFlightStarted(false);
    setElapsed(0);
    elapsedRef.current = 0;
    appliedMissionRef.current = original.payload;
    setForm((prev) => ({ ...prev, altitude_m: String(original.payload.altitude_m) }));
    setPlan(original.plan);
    setAppliedMitigation(null);
    originalSimulationRef.current = null;
    setAdvisorTab("preflight");
    setInflight(null);
    setInflightMeta(null);
    setInflightAdvice(null);
    inflightAdvisedSignatureRef.current = "";
    void runPreflight(original.payload, analysisSource, radiusKm);
  }

  async function requestHermesAdvice() {
    if (!routeResultShown || !topSixRoutes.length || flightStarted ||
        hermesLoading || creating || routeLoading || missionChanged) return;

    hermesAbortRef.current?.abort();
    const controller = new AbortController();
    hermesAbortRef.current = controller;
    setHermesAdvice(null);
    setHermesMeta(null);
    setHermesError("");
    setHermesLoading(true);

    // KIRIM HANYA RINGKASAN CPA, bukan 30 flight_plan / koordinat lengkap.
    const slimRoute = (route) => ({
      route_id: route?.route_id,
      side: route?.side,
      offset_m: route?.offset_m,
      bend_fraction: route?.bend_fraction,
      extra_distance_m: route?.extra_distance_m,
      extra_duration_s: route?.extra_duration_s,
      potential_conflicts: route?.potential_conflicts,
      aircraft_received: route?.aircraft_received,
      aircraft_analyzed: route?.aircraft_analyzed,
      aircraft_skipped: route?.aircraft_skipped,
      data_quality_status: route?.data_quality_status,
      route_coverage_complete: route?.route_coverage_complete,
      cpa_candidate_eligible: route?.cpa_candidate_eligible,
      conflicts: (route?.conflicts || []).slice(0, 6).map((plane) => ({
        callsign: plane.callsign,
        horizontal_cpa_m: plane.horizontal_cpa_m,
        vertical_separation_m: plane.vertical_separation_m,
        time_to_cpa_s: plane.time_to_cpa_s,
      })),
    });
    try {
      const response = await fetch(`${API}/api/agent-advice`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          source: routeResultShown.source,
          evaluation_status: routeResultShown.status,
          snapshot_time_utc: routeResultShown.snapshot_time_utc,
          reference_departure_time_utc: routeResultShown.reference_departure_time_utc,
          candidate_count: routeResultShown.candidate_count,
          eligible_candidate_count: routeResultShown.eligible_candidate_count,
          recommended_route_id: routeResultShown.recommended_route_id,
          original_route: slimRoute(routeResultShown.original_route),
          top_routes: topSixRoutes.map(slimRoute),
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(typeof body.detail === "string"
          ? body.detail : `Hermes HTTP ${response.status}`);
      }
      if (!controller.signal.aborted) {
        setHermesAdvice(body);
        setHermesMeta({ evaluation: routeResultShown, plan, source: analysisSource });
      }
    } catch (error) {
      if (!controller.signal.aborted && error.name !== "AbortError") {
        setHermesError(error.message);
      }
    } finally {
      if (!controller.signal.aborted) setHermesLoading(false);
    }
  }

  function previewAlternative(candidate) {
    setAgentSelectedId(null);
    setSelectedRouteId(candidate.route_id);
    const map = mapRef.current;
    if (map?.getSource("route")) fitRoute(map, plan, candidate.flight_plan?.waypoints || []);
  }

  function choosePoint(mode) {
    const next = pickModeRef.current === mode ? null : mode;
    pickModeRef.current = next;
    setPickMode(next);
    if (mapRef.current) mapRef.current.getCanvas().style.cursor = next ? "crosshair" : "";
  }

  // ==============================================
  // OPENSKY FOR MAP (same refresh cycle as before)
  // ==============================================
  useEffect(() => {
    if (!plan) return;
    let active = true, pending = false, controller = null;
    setTrafficError("");
    async function scan() {
      if (!active || pending) return;
      pending = true;
      controller = new AbortController();
      setTrafficLoading(true);
      const position = droneAtTime(plan.waypoints, elapsedRef.current);
      if (!position) { pending = false; setTrafficLoading(false); return; }
      const query = new URLSearchParams({
        center_lat: String(position.latitude),
        center_lon: String(position.longitude),
        drone_altitude_m: String(position.altitude_m),
        radius_km: String(radiusKm),
        max_altitude_m: "3300",
      });
      try {
        const r = await fetch(`${API}/api/aircraft?${query}`, {
          signal: controller.signal,
        });
        const body = await r.json();
        if (!r.ok) throw new Error(
          typeof body.detail === "string" ? body.detail : `OpenSky HTTP ${r.status}`
        );
        if (active) { setTraffic(body); setTrafficError(""); }
      } catch (e) {
        if (active && e.name !== "AbortError") setTrafficError(e.message);
      } finally {
        pending = false;
        if (active) setTrafficLoading(false);
      }
    }
    void scan();
    const timer = setInterval(scan, refreshSeconds * 1000);
    return () => { active = false; clearInterval(timer); controller?.abort(); };
  }, [plan, radiusKm, refreshSeconds, scanNonce]);

  // ==============================================
  // IN-FLIGHT CPA (starts on Start, re-runs periodically)
  // ==============================================
  useEffect(() => {
    if (!plan || !playing || !flightStarted || !appliedMissionRef.current) return;
    let active = true, pending = false, controller = null;
    setInflightError("");

    async function analyze() {
      if (!active || pending) return;
      const elapsedAtScan = Math.min(elapsedRef.current, plan.mission.duration_s);
      if (elapsedAtScan >= plan.mission.duration_s) return;
      pending = true;
      controller = new AbortController();
      setInflightLoading(true);
      try {
        const response = await fetch(`${API}/api/inflight-analysis`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...appliedMissionRef.current,
            elapsed_s: elapsedAtScan,
            radius_km: radiusKm,
            source: analysisSource,
          }),
          signal: controller.signal,
        });
        const body = await response.json();
        if (!response.ok) throw new Error(
          typeof body.detail === "string" ? body.detail : `In-flight CPA HTTP ${response.status}`
        );
        if (active) {
          setInflight(body);
          setInflightMeta({
            source: analysisSource,
            radius: radiusKm,
            receivedAt: Date.now(),
            simulationElapsedS: elapsedAtScan,
          });
          setInflightError("");
        }
      } catch (e) {
        if (active && e.name !== "AbortError") setInflightError(e.message);
      } finally {
        pending = false;
        if (active) setInflightLoading(false);
      }
    }

    void analyze();
    const timer = setInterval(analyze, refreshSeconds * 1000);
    return () => {
      active = false;
      clearInterval(timer);
      controller?.abort();
      setInflightLoading(false);
    };
  }, [plan, playing, flightStarted, radiusKm, refreshSeconds, analysisSource, scanNonce]);

  // ==============================================
  // MAP
  // ==============================================
  useEffect(() => {
    if (!plan || !mapDiv.current) return;
    const route = plan.waypoints.map((p) => [p.longitude, p.latitude]);
    if (!route.length) return;
    const map = new maplibregl.Map({
      container: mapDiv.current, style: MAP_STYLE, center: route[0], zoom: 12,
    });
    mapRef.current = map;
    const staticMarkers = [];
    lastCircleRef.current = { time: 0, radius: radiusRef.current };
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("click", (event) => {
      const mode = pickModeRef.current;
      if (!mode) return;
      const isStart = mode === "start";
      setForm((old) => ({
        ...old,
        [isStart ? "start_lat" : "end_lat"]: event.lngLat.lat.toFixed(6),
        [isStart ? "start_lon" : "end_lon"]: event.lngLat.lng.toFixed(6),
      }));
      draftMarkersRef.current[mode]?.remove();
      draftMarkersRef.current[mode] = new maplibregl.Marker({ color: "#a855f7" })
        .setLngLat([event.lngLat.lng, event.lngLat.lat])
        .setPopup(new maplibregl.Popup().setText("Titik baru belum diterapkan"))
        .addTo(map);
      setDraftNotice("Koordinat terisi. Klik Generate Flight Plan untuk menerapkan rute.");
      pickModeRef.current = null;
      setPickMode(null);
      map.getCanvas().style.cursor = "";
    });

    map.on("load", () => {
      const initial = droneAtTime(plan.waypoints, elapsedRef.current) || plan.waypoints[0];
      map.addSource("monitor-radius", {
        type: "geojson",
        data: monitoringCircle(initial.latitude, initial.longitude, radiusRef.current),
      });
      map.addLayer({
        id: "monitor-fill", type: "fill", source: "monitor-radius",
        paint: { "fill-color": "#0ea5e9", "fill-opacity": 0.07 },
      });
      map.addLayer({
        id: "monitor-outline", type: "line", source: "monitor-radius",
        paint: {
          "line-color": "#0284c7", "line-width": 2,
          "line-opacity": 0.8, "line-dasharray": [3, 3],
        },
      });
      map.addSource("route", {
        type: "geojson",
        data: { type: "Feature", properties: {},
          geometry: { type: "LineString", coordinates: route } },
      });
      map.addLayer({
        id: "route-line", type: "line", source: "route",
        paint: { "line-color": "#13b8f5", "line-width": 4 },
      });
      staticMarkers.push(
        new maplibregl.Marker({ color: "#22c55e" })
          .setLngLat(route[0])
          .setPopup(new maplibregl.Popup().setText("Titik awal"))
          .addTo(map),
        new maplibregl.Marker({ color: "#f59e0b" })
          .setLngLat(route[route.length - 1])
          .setPopup(new maplibregl.Popup().setText("Titik tujuan"))
          .addTo(map)
      );
      const element = document.createElement("div");
      element.className = "quadcopter-marker";
      element.innerHTML = DRONE_SVG;
      droneMarkerRef.current = new maplibregl.Marker({ element })
        .setLngLat([initial.longitude, initial.latitude]).addTo(map);
      fitRoute(map, plan); // Fokus ke rute; jangan auto zoom out ke pesawat.
      if (trafficRef.current.length) {
        drawAircraft(map, trafficRef.current, aircraftMarkersRef.current);
      }
    });

    return () => {
      Object.values(draftMarkersRef.current).forEach((marker) => marker?.remove());
      draftMarkersRef.current = { start: null, destination: null };
      for (const item of aircraftMarkersRef.current.values()) item.marker.remove();
      aircraftMarkersRef.current.clear();
      staticMarkers.forEach((marker) => marker.remove());
      droneMarkerRef.current?.remove();
      droneMarkerRef.current = null;
      map.remove();
      if (mapRef.current === map) mapRef.current = null;
    };
  }, [plan]);

  useEffect(() => {
    const planes = traffic?.aircraft || [];
    trafficRef.current = planes;
    const map = mapRef.current;
    if (map?.getSource("route")) {
      drawAircraft(map, planes, aircraftMarkersRef.current);
    }
  }, [traffic, plan]);

  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now() / 1000;
      for (const { marker, plane } of aircraftMarkersRef.current.values()) {
        marker.setLngLat(displayPosition(plane, now));
      }
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // ==============================================
  // DRONE ANIMATION
  // ==============================================
  useEffect(() => {
    if (!playing || !plan) return;
    let frame;
    function animate(timestamp) {
      if (lastFrameRef.current === null) lastFrameRef.current = timestamp;
      const dt = (timestamp - lastFrameRef.current) / 1000;
      lastFrameRef.current = timestamp;
      setElapsed((old) => Math.min(plan.mission.duration_s, old + dt * speed));
      frame = requestAnimationFrame(animate);
    }
    frame = requestAnimationFrame(animate);
    return () => { cancelAnimationFrame(frame); lastFrameRef.current = null; };
  }, [playing, plan, speed]);

  useEffect(() => {
    if (playing && elapsed >= duration) setPlaying(false);
  }, [playing, elapsed, duration]);

  useEffect(() => {
    const map = mapRef.current;
    if (!current || !map) return;
    droneMarkerRef.current?.setLngLat([current.longitude, current.latitude]);
    const source = map.getSource("monitor-radius");
    if (!source) return;
    const now = Date.now();
    const force = elapsed === 0 || lastCircleRef.current.radius !== radiusKm;
    if (!force && now - lastCircleRef.current.time < 200) return;
    source.setData(monitoringCircle(current.latitude, current.longitude, radiusKm));
    lastCircleRef.current = { time: now, radius: radiusKm };
  }, [current?.latitude, current?.longitude, radiusKm, plan]);

  function start() {
    if (!plan) return;
    clearAgentPlan();
    hermesAbortRef.current?.abort();
    setHermesAdvice(null);
    setHermesMeta(null);
    setHermesLoading(false);
    setHermesError("");
    setInflightAdvice(null);
    setInflightAdviceError("");
    inflightAdvisedSignatureRef.current = "";
    if (elapsed >= duration) {
      setElapsed(0);
      elapsedRef.current = 0;
      setInflight(null);
      setInflightMeta(null);
      setInflightError("");
    }
    lastFrameRef.current = null;
    setFlightStarted(true);
    setAdvisorTab("inflight");
    setPlaying(true);
  }

  function reset() {
    inflightAdviceAbortRef.current?.abort();
    setInflightAdvice(null);
    setInflightAdviceError("");
    setInflightAdviceLoading(false);
    inflightAdvisedSignatureRef.current = "";
    clearAgentPlan();
    hermesAbortRef.current?.abort();
    setHermesAdvice(null);
    setHermesMeta(null);
    setHermesLoading(false);
    setHermesError("");
    setPlaying(false);
    setFlightStarted(false);
    setElapsed(0);
    elapsedRef.current = 0;
    lastFrameRef.current = null;
    setInflight(null);
    setInflightMeta(null);
    setInflightError("");
    setInflightLoading(false);
    setAdvisorTab("preflight");
  }

  function viewMap(mode) {
    const map = mapRef.current;
    if (!map?.getSource("route") || !plan) return;
    if (mode === "radius") fitRadius(map, current, radiusKm);
    else fitRoute(map, plan, mode === "all" ? trafficRef.current : []);
  }

  const missionChanged = !!appliedMissionRef.current &&
    Object.entries(form).some(([key, value]) =>
      Number(value) !== Number(appliedMissionRef.current[key])
    );
  const preflightOutdated = !!preflightMeta &&
    (preflightMeta.source !== analysisSource || preflightMeta.radius !== radiusKm);
  const viewingFlight = advisorTab === "inflight";

  // Hasil in-flight hanya dapat dianggap AKTIF jika:
  // - sumber/radius masih cocok dengan pilihan terkini,
  // - monitoring sedang berjalan,
  // - tidak ada error update,
  // - hasil dan (untuk OpenSky) timestamp snapshot belum kedaluwarsa.
  const inflightMatches = Boolean(
    inflight && inflightMeta &&
    inflightMeta.source === analysisSource &&
    inflightMeta.radius === radiusKm &&
    inflight.source === analysisSource
  );
  const maxResultAgeS = Math.min(120, Math.max(45, 2 * refreshSeconds + 10));
  const resultAgeS = inflightMeta
    ? Math.max(0, (nowMs - inflightMeta.receivedAt) / 1000)
    : Infinity;
  const snapshotTimestampMs = inflight?.snapshot_time_utc
    ? Date.parse(inflight.snapshot_time_utc)
    : NaN;
  const snapshotAgeS = Number.isFinite(snapshotTimestampMs)
    ? Math.max(0, (nowMs - snapshotTimestampMs) / 1000)
    : Infinity;
  // Pada 10x, 30 detik waktu nyata setara 300 detik perjalanan.
  // Hasil scan harus juga kedaluwarsa ketika drone simulasi sudah jauh
  // dari posisi yang digunakan sebagai titik awal evaluasi CPA.
  const maxSimLagS = Math.min(60, Math.max(
    30, Number(plan?.mission.time_step_s || 30) * 1.5
  ));
  const simulationLagS = inflightMeta
    ? Math.abs(elapsed - inflightMeta.simulationElapsedS)
    : Infinity;
  const inflightFresh = inflightMatches &&
    resultAgeS <= maxResultAgeS &&
    simulationLagS <= maxSimLagS &&
    (analysisSource === "demo" || snapshotAgeS <= maxResultAgeS);
  const inflightLive = Boolean(
    viewingFlight && playing && flightStarted &&
    elapsed < duration && !missionChanged &&
    !inflightError && inflightFresh
  );
  const displayedResult = viewingFlight
    ? (inflightMatches ? inflight : null)
    : (missionChanged || preflightOutdated ? null : preflight);

  // TIDAK tampilkan peringatan lama di peta saat Pause, data stale,
  // mengubah sumber, atau membuka kembali tab Pre-Flight setelah terbang.
  const mapCpaResult = viewingFlight
    ? (inflightLive ? inflight : null)
    : (!flightStarted && !missionChanged && !preflightOutdated &&
       !preflightError ? preflight : null);

  const routeResultValid = Boolean(
    routeEvaluation && routeMeta && routeMeta.plan === plan &&
    routeMeta.source === analysisSource && routeMeta.radius === radiusKm &&
    !flightStarted && !missionChanged && !preflightOutdated &&
    !preflightLoading && !creating
  );
  const routeResultShown = routeResultValid ? routeEvaluation : null;
  // Hanya enam alternatif terbaik yang ditampilkan, tetapi backend menguji 30.
  const topSixRoutes = selectBestRouteCandidates(routeResultShown?.candidates, 6);
  const chosenRoute = topSixRoutes.find((item) => item.route_id === selectedRouteId) || null;
  const hermesShown = Boolean(
    hermesAdvice && hermesMeta && hermesMeta.evaluation === routeResultShown &&
    hermesMeta.plan === plan && hermesMeta.source === analysisSource &&
    !flightStarted && !missionChanged && !viewingFlight
  ) ? hermesAdvice : null;
  const agentPlanShown = Boolean(
    agentPlanResult && agentPlanMeta && agentPlanMeta.plan === plan &&
    agentPlanMeta.source === analysisSource && agentPlanMeta.radius === radiusKm &&
    agentPlanMeta.evaluation === routeResultShown && !flightStarted &&
    !missionChanged && !preflightOutdated && !viewingFlight
  ) ? agentPlanResult : null;
  const selectedAgentAttempt = agentPlanShown?.attempts?.find(
    (item) => item.attempt_id === agentSelectedId
  ) || null;
  const selectedAgentRoute = selectedAgentAttempt?.tool === "evaluate_route" &&
    selectedAgentAttempt?.route_geojson ? selectedAgentAttempt : null;
  const routeMapResult = !viewingFlight
    ? (selectedAgentRoute ? { original_route: agentPlanShown.original_route } : routeResultShown)
    : null;
  const routeMapCandidate = !viewingFlight ? (selectedAgentRoute || chosenRoute) : null;

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const updateRouteOverlay = () => {
      if (!map.getSource("route")) return;
      syncRouteComparisonOverlay(map, routeMapResult, routeMapCandidate);
    };
    updateRouteOverlay();
    map.on("load", updateRouteOverlay);
    return () => map.off("load", updateRouteOverlay);
  }, [plan, routeMapResult, routeMapCandidate]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const updateOverlay = () => {
      // Source `route` tersedia setelah event load MapLibre.
      if (!map.getSource("route")) return;

      syncCpaOverlay(
        map,
        mapCpaResult,
        aircraftMarkersRef.current,
        analysisSource
      );
    };

    updateOverlay();
    map.on("load", updateOverlay);

    return () => {
      map.off("load", updateOverlay);
    };
  }, [mapCpaResult, analysisSource, traffic, plan]);

  // Hermes automatically explains a NEW active CPA conflict (not every refresh).
  // The deterministic CPA warning does not wait for the language model.
  useEffect(() => {
    if (!flightStarted || !playing || !inflightLive ||
        !inflight || inflight.potential_conflicts < 1) return;
    const aircraftKey = (inflight.conflicts || []).slice(0, 5)
      .map((c) => c.icao24 || c.callsign || "unknown").sort().join("|");
    const signature = `${plan?.mission?.route_id}|${analysisSource}|${aircraftKey}`;
    const currentTime = Date.now();
    if (inflightAdvisedSignatureRef.current === signature &&
        currentTime - inflightLastAiTimeRef.current < 60000) return;
    if (inflightAdviceAbortRef.current) inflightAdviceAbortRef.current.abort();
    inflightAdvisedSignatureRef.current = signature;
    inflightLastAiTimeRef.current = currentTime;
    const controller = new AbortController();
    inflightAdviceAbortRef.current = controller;
    setInflightAdvice(null);
    setInflightAdviceError("");
    setInflightAdviceLoading(true);
    const payload = {
      source: analysisSource,
      analysis_status: String(inflight.analysis_status || "UNKNOWN"),
      data_quality_status: String(inflight.data_quality_status || "UNKNOWN"),
      potential_conflicts: inflight.potential_conflicts || 0,
      aircraft_received: inflight.aircraft_received || 0,
      aircraft_analyzed: inflight.aircraft_analyzed || 0,
      aircraft_skipped: inflight.aircraft_skipped || 0,
      simulation_elapsed_s: inflight.simulation_elapsed_s || 0,
      remaining_duration_s: inflight.remaining_duration_s || 0,
      snapshot_time_utc: inflight.snapshot_time_utc || null,
      conflicts: (inflight.conflicts || []).slice(0, 5).map((c) => ({
        callsign: c.callsign || null,
        icao24: c.icao24 || null,
        horizontal_cpa_m: c.horizontal_cpa_m ?? null,
        vertical_separation_m: c.vertical_separation_m ?? null,
        time_to_cpa_s: c.time_to_cpa_s ?? null,
      })),
    };
    fetch(`${API}/api/inflight-advice`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      signal: controller.signal, body: JSON.stringify(payload),
    }).then(async (response) => {
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string"
        ? body.detail : `Hermes In-Flight HTTP ${response.status}`);
      return body;
    }).then((body) => {
      if (!controller.signal.aborted) setInflightAdvice(body);
    }).catch((error) => {
      if (!controller.signal.aborted && error.name !== "AbortError") {
        setInflightAdviceError(error.message);
      }
    }).finally(() => {
      if (!controller.signal.aborted) setInflightAdviceLoading(false);
    });
    // Jangan abort tiap scan CPA berikutnya: respons model gratis bisa >15 detik.
    // Permintaan lama dibatalkan saat konflik berbeda, Reset, atau unmount.
  }, [inflight, inflightMeta, inflightLive, plan, analysisSource, playing, flightStarted]);

  const displayedLoading = viewingFlight ? inflightLoading : preflightLoading;
  const displayedError = viewingFlight ? inflightError : preflightError;
  const inflightExpired = inflightMatches && !inflightFresh;
  const inflightStatusText = !flightStarted
    ? "BELUM DIMULAI"
    : elapsed >= duration
    ? "MISI SELESAI"
    : !playing
    ? "SNAPSHOT LAMA"
    : inflightError
    ? "UPDATE GAGAL"
    : !inflightMatches
    ? "MENUNGGU DATA"
    : inflightExpired
    ? "DATA KEDALUWARSA"
    : statusLabel(inflight);
  const inflightStatusClass = !playing && flightStarted
    ? "SNAPSHOT"
    : inflightError
    ? "UPDATE_FAILED"
    : inflightExpired
    ? "STALE"
    : inflight?.analysis_status || "";
  const hint = viewingFlight
    ? !flightStarted
      ? "In-flight belum aktif. Tekan Start pada Drone Simulation."
      : !playing
      ? "Monitoring dihentikan. Hasil terakhir disimpan sebagai riwayat, bukan status live."
      : inflightError
      ? "Pemindaian CPA terbaru gagal. Status terakhir tidak dipakai sebagai peringatan aktif."
      : inflightExpired
      ? `Hasil CPA tidak lagi terkini (batas usia ${maxResultAgeS} s atau pergeseran simulasi ${maxSimLagS} s). Menunggu pemindaian berikutnya; tidak ada kesimpulan aman.`
      : "In-flight menggunakan waktu dan posisi simulasi (evaluasi what-if), bukan operasi penerbangan nyata."
    : missionChanged
    ? "Input misi berubah. Klik Generate Flight Plan untuk menganalisis rute baru."
    : preflightOutdated
    ? "Sumber atau radius berubah. Klik Analisis Ulang untuk memperbarui hasil."
    : flightStarted
    ? "Hasil Pre-Flight ini bersifat historis dan bukan status konflik saat drone bergerak."
    : "";

  return (
    <div className="dashboard">
      <header className="header">
        <h1>AI Airspace Conflict Advisor</h1>
        <span>SIMULATION MODE</span>
      </header>

      <main className="layout">
        <aside className="left-panel">
          <form className="mission-form" onSubmit={createPlan}>
            <h2>Mission Planner</h2>
            {[
              ["start", "Titik Awal", "start_lat", "start_lon"],
              ["destination", "Titik Tujuan", "end_lat", "end_lon"],
            ].map(([mode, title, latKey, lonKey]) => (
              <div className="coordinate-group" key={mode}>
                <div className="group-title">{title}</div>
                <div className="form-grid">
                  {[[latKey, "Latitude"], [lonKey, "Longitude"]].map(([name, label]) => (
                    <label className="input-field" key={name}>
                      <span>{label}</span>
                      <input type="number" step="any" value={form[name]}
                        onChange={(e) => setForm((old) => ({ ...old, [name]: e.target.value }))} />
                    </label>
                  ))}
                </div>
                <button type="button"
                  className={`pick-button ${pickMode === mode ? "active" : ""}`}
                  onClick={() => choosePoint(mode)}>
                  {pickMode === mode ? "✕ Batal memilih" :
                    `⌖ Pilih ${mode === "start" ? "titik awal" : "titik tujuan"} di peta`}
                </button>
              </div>
            ))}

            <div className="form-grid compact-parameters">
              {[
                ["altitude_m", "Altitude (m)"],
                ["speed_mps", "Speed (m/s)"],
                ["time_step_s", "Time Step (s)"],
              ].map(([name, label]) => (
                <label className="input-field" key={name}>
                  <span>{label}</span>
                  <input type="number" step="any" value={form[name]}
                    onChange={(e) => setForm((old) => ({ ...old, [name]: e.target.value }))} />
                </label>
              ))}
              <label className="input-field">
                <span>Radius (km)</span>
                <input type="number" min="1" max="150" step="any"
                  value={radiusInput} aria-invalid={!radiusValid}
                  onChange={(e) => setRadiusInput(e.target.value)}
                  onBlur={applyRadius} />
              </label>
            </div>

            {!radiusValid && <p className="error-text">Radius harus 1–150 km.</p>}
            <button type="submit" className="generate-button" disabled={creating}>
              {creating ? "Generating..." : "Generate Flight Plan"}
            </button>
            {draftNotice && <p className="draft-notice">{draftNotice}</p>}
            {formError && <p className="error-text">{formError}</p>}
          </form>

          {appliedMitigation && (
            <div className="applied-agent-mission">
              <strong>Rencana simulasi aktif: {appliedMitigation.attempt_id}</strong>
              <span>{appliedMitigation.tool === "evaluate_route" ? "Rute waypoint Hermes" :
                appliedMitigation.tool === "evaluate_altitude" ? "Skenario ketinggian konstan" : "Skenario keberangkatan ditunda"}
                {` · ${appliedMitigation.altitude_m} m`}
                {appliedMitigation.delay_s > 0 ? ` · tunda ${appliedMitigation.delay_s} detik` : ""}
              </span>
              <small>CPA dihitung ulang pada snapshot terbaru; ini bukan izin terbang.</small>
              <button type="button" disabled={playing || flightStarted || creating}
                onClick={restoreOriginalSimulation}>↶ Kembali ke rencana awal</button>
            </div>
          )}

          <section className="simulation-panel">
            <h2>Drone Simulation</h2>
            <div className="sim-buttons">
              <button onClick={start} disabled={!plan || playing}>▶ Start</button>
              <button onClick={() => setPlaying(false)} disabled={!playing}>Ⅱ Pause</button>
              <button onClick={reset} disabled={!plan}>↺ Reset</button>
            </div>
            <div className="speed-row">
              <label htmlFor="sim-speed">Simulation Speed</label>
              <select id="sim-speed" value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}>
                {[1, 2, 5, 10].map((n) =>
                  <option key={n} value={n}>{n}×</option>
                )}
              </select>
            </div>
            <input className="progress-slider" type="range" min="0"
              max={duration || 1} step="0.1" value={elapsed}
              disabled={!plan} onChange={(e) => setElapsed(Number(e.target.value))} />
            <div className="progress-label">
              {elapsed.toFixed(1)} / {duration.toFixed(1)} s · {progress.toFixed(1)}%
            </div>
          </section>
        </aside>

        <section className="center-panel">
          <div className="map-view">
            <div className="map" ref={mapDiv} />
            {pickMode && <div className="map-pick-hint">
              Klik di peta untuk memilih {pickMode === "start" ? "TITIK AWAL" : "TITIK TUJUAN"}
            </div>}
            <div className="map-tools">
              <button onClick={() => viewMap("all")}>Lihat semua pesawat</button>
              <button onClick={() => viewMap("route")}>Fokus rute</button>
              <button onClick={() => viewMap("radius")}>Lihat radius</button>
            </div>
            <div className="radius-tag">Jangkauan drone: {radiusKm} km</div>
            {!viewingFlight && selectedAgentAttempt && selectedAgentAttempt.tool !== "evaluate_route" && (
              <div className="map-mitigation-tag">
                Pratinjau Hermes: {selectedAgentAttempt.tool === "evaluate_altitude"
                  ? `ALT ${selectedAgentAttempt.altitude_m} m (garis 2D tidak berubah)`
                  : `TUNDA ${selectedAgentAttempt.delay_s} s (rute tetap)`}
              </div>
            )}
            <div className="map-legend">
              <span><b className="legend-dot drone-dot" />Drone</span>
              <span><b className="legend-dot plane-dot" />Dalam radius</span>
              <span><b className="legend-dot conflict-dot" />Konflik CPA</span>
              <span><b className="legend-dot outside-dot" />Luar radius</span>
              <span><b className="legend-dot range-dot" />Batas radius</span>
            </div>
          </div>

          <section className="advisor-dock advisor-cpa">
            <div className="advisor-heading">
              <span>✦ AI Advisor — Conflict Monitoring</span>
              <span className="advisor-state">CPA + HERMES (PRE-FLIGHT + IN-FLIGHT)</span>
            </div>

            <div className="advisor-mode-tabs enhanced">
              <button
                type="button"
                className={`mode-tab preflight ${advisorTab === "preflight" ? "selected" : ""}`}
                onClick={() => setAdvisorTab("preflight")}
              >
                <span className="mode-tab-title">Pre-Flight</span>
                <span className="mode-tab-sub">Analisis sebelum terbang</span>
              </button>

              <button
                type="button"
                className={`mode-tab inflight ${advisorTab === "inflight" ? "selected" : ""}`}
                onClick={() => setAdvisorTab("inflight")}
              >
                <span className="mode-tab-title">In-Flight</span>
                <span className="mode-tab-sub">Monitoring saat simulasi</span>
              </button>
            </div>

            <div className="advisor-controls advisor-controls-enhanced">
              <div className="advisor-controls-left">
                <label htmlFor="analysis-source">Sumber analisis</label>
                <select
                  id="analysis-source"
                  value={analysisSource}
                  onChange={(e) => setAnalysisSource(e.target.value)}
                >
                  <option value="demo">Demo sintetis</option>
                  <option value="opensky">OpenSky aktual</option>
                </select>

                {!viewingFlight && (
                  <button
                    type="button"
                    disabled={!plan || creating || preflightLoading || !radiusValid}
                    onClick={() => {
                      applyRadius();
                      void runPreflight(appliedMissionRef.current, analysisSource, parsedRadius);
                    }}
                  >
                    ↻ Analisis Ulang
                  </button>
                )}
              </div>

              <div className="advisor-controls-right">
                <span
                  className={`cpa-status ${
                    viewingFlight
                      ? inflightStatusClass
                      : displayedResult?.analysis_status || ""
                  }`}
                >
                  {viewingFlight
                    ? inflightStatusText
                    : displayedLoading
                    ? "MEMPROSES"
                    : statusLabel(displayedResult)}
                </span>

                {viewingFlight && (
                  <span className={`cpa-monitor-label ${playing ? "active" : "idle"}`}>
                    {playing ? "● Monitoring berjalan" : "○ Monitoring tidak aktif"}
                  </span>
                )}
              </div>
            </div>

            <CpaResult result={displayedResult} loading={displayedLoading}
              error={displayedError} hint={hint} isFlight={viewingFlight}
              liveStatus={viewingFlight ? inflightLive : !flightStarted}
              receivedAt={viewingFlight ? inflightMeta?.receivedAt : null} />

            {viewingFlight && flightStarted && (
              <section className="inflight-hermes-box" aria-label="Hermes In-Flight Advisor">
                <h3>✦ Hermes — Respons In-Flight (Simulasi)</h3>
                <p>Deteksi dan peringatan tetap dilakukan CPA Python. Saat ada konflik baru,
                  Hermes otomatis diminta menjelaskan hasilnya; Hermes tidak mengendalikan drone.</p>
                {inflightLive && inflight?.potential_conflicts > 0 && (
                  <div className="inflight-warning-strong">
                    Potensi konflik terdeteksi: {inflight.potential_conflicts}.
                    {inflight.aircraft_skipped > 0 && ` ${inflight.aircraft_skipped} pesawat belum dapat dianalisis.`}
                    {" "}Jangan anggap lintasan saat ini aman.
                  </div>
                )}
                {inflightAdviceLoading && <p>Hermes sedang memberi penjelasan berdasarkan snapshot CPA...</p>}
                {inflightAdviceError && <p className="error-text">Hermes tidak tersedia: {inflightAdviceError}. Peringatan CPA tetap berlaku.</p>}
                {inflightAdvice && (
                  <div className="inflight-ai-answer">
                    {inflightLive ? inflightAdvice.advice : "Penjelasan Hermes sebelumnya kini merupakan riwayat, bukan saran kondisi terkini."}
                    <small>Belum menguji mitigasi sisa rute dan tidak mengubah flight plan secara otomatis.</small>
                  </div>
                )}
                {!inflightAdvice && !inflightAdviceLoading && !inflightAdviceError && (
                  <p>Hermes akan dipanggil saat CPA aktif mendeteksi potensi konflik.</p>
                )}
              </section>
            )}

            {!viewingFlight && (
              <>
              <section className="route-evaluation-section" aria-label="Evaluasi rute alternatif">
                <div className="route-evaluation-header">
                  <div>
                    <h3>Alternatif Rute — CPA Evaluator</h3>
                    <p>Backend menilai 30 alternatif menggunakan satu snapshot, lalu menampilkan hanya 6 rute terbaik.</p>
                  </div>
                  <span className="route-engine-label">ALGORITMA CPA · BUKAN HERMES</span>
                </div>

                <div className="route-evaluation-actions">
                  <span className="route-top6-description">30 kandidat dievaluasi · hanya 6 terbaik ditampilkan</span>
                  <button type="button" onClick={evaluateAlternatives}
                    disabled={!!appliedMitigation || !plan || creating || flightStarted || routeLoading ||
                      preflightLoading || missionChanged || preflightOutdated ||
                      !radiusValid || parsedRadius !== radiusKm}>
                    {routeLoading ? "Mengevaluasi 30 kandidat..." : "↻ Cari 6 Jalur Terbaik"}
                  </button>
                </div>
                {flightStarted && <p className="route-help">
                  Evaluasi ini untuk Pre-Flight. Klik Reset sebelum menguji rute baru.
                </p>}
                {(missionChanged || preflightOutdated || parsedRadius !== radiusKm) && (
                  <p className="route-help">Input/sumber berubah. Terapkan flight plan atau perbarui analisis CPA dahulu.</p>
                )}
                {routeError && <p className="error-text">Route Evaluator: {routeError}</p>}
                {routeLoading && <p className="route-help">Menguji 30 kandidat dengan CPA untuk memilih 6 yang paling baik...</p>}

                {routeResultShown && (
                  <>
                    <div className="route-evaluation-summary">
                      <div><span>Konflik rute awal</span><strong>{routeResultShown.original_route?.potential_conflicts ?? "-"}</strong></div>
                      <div><span>Dievaluasi / Tampil</span><strong>{routeResultShown.candidate_count ?? 0} / {topSixRoutes.length}</strong></div>
                      <div><span>Kandidat lolos CPA</span><strong>{routeResultShown.eligible_candidate_count ?? 0}</strong></div>
                    </div>
                    <div className={`route-evaluation-message ${routeResultShown.status === "RECOMMENDATION_AVAILABLE" ? "eligible" : "caution"}`}>
                      {routeResultShown.status === "RECOMMENDATION_AVAILABLE"
                        ? `Kandidat ${routeResultShown.recommended_route_id} memenuhi kriteria CPA yang diuji. Belum divalidasi untuk operasi nyata.`
                        : routeResultShown.status === "NO_REROUTE_NEEDED"
                        ? "Rute awal tidak terdeteksi konflik pada skenario yang dievaluasi; pengalihan rute belum diperlukan."
                        : routeResultShown.status === "BASELINE_INCOMPLETE"
                        ? "Analisis rute awal belum lengkap. Belum dapat menentukan rekomendasi."
                        : "Belum ada kandidat lolos CPA. Enam rute di bawah masih berpotensi konflik atau belum lengkap; ini hanya peringkat perbandingan, bukan rute aman."}
                    </div>

                    <div className="route-candidates-grid route-candidates-grid-top6" aria-label="Enam kandidat rute terbaik">
                      {topSixRoutes.map((candidate, index) => {
                        const active = chosenRoute?.route_id === candidate.route_id;
                        const eligible = candidate.cpa_candidate_eligible === true;
                        const conflict = Number(candidate.potential_conflicts) > 0;
                        return (
                          <button type="button" key={candidate.route_id}
                            className={`route-candidate-button ${active ? "selected" : ""} ${eligible ? "eligible" : conflict ? "conflict" : "uncertain"}`}
                            onClick={() => previewAlternative(candidate)}
                            aria-pressed={active}>
                            <span className="route-candidate-name">#{index + 1} · {candidate.side === "left" ? "Kiri" : "Kanan"} {Number(candidate.offset_m).toLocaleString("id-ID")} m · {Math.round(Number(candidate.bend_fraction ?? 0.5) * 100)}%</span>
                            <span className="route-candidate-stat">{candidate.potential_conflicts} konflik · +{formatMeters(candidate.extra_distance_m)} · CPA {candidate.conflicts?.length ? formatMeters(Math.min(...candidate.conflicts.map((c) => Number(c.horizontal_cpa_m)))) : "—"}</span>
                            <span className="route-candidate-quality">{eligible ? "Lolos kriteria CPA" : conflict ? "Masih berkonflik" : "Data belum lengkap"}</span>
                          </button>
                        );
                      })}
                    </div>

                    {chosenRoute && (
                      <div className="route-preview-detail">
                        <div className="route-preview-heading">
                          <strong>Pratinjau: {chosenRoute.route_id}</strong>
                          <button type="button" onClick={() => setSelectedRouteId(null)}>
                            Sembunyikan garis
                          </button>
                        </div>
                        <div className="route-preview-values">
                          <span>Konflik: <strong>{chosenRoute.potential_conflicts}</strong></span>
                          <span>Tambah jarak: <strong>+{formatMeters(chosenRoute.extra_distance_m)}</strong></span>
                          <span>Tambah waktu: <strong>+{Number(chosenRoute.extra_duration_s).toFixed(1)} s</strong></span>
                          <span>CPA konflik terdekat: <strong>{chosenRoute.conflicts?.length ? formatMeters(Math.min(...chosenRoute.conflicts.map((c) => Number(c.horizontal_cpa_m)))) : "Tidak ada"}</strong></span>
                        </div>
                        <p className="route-preview-note">
                          {chosenRoute.cpa_candidate_eligible
                            ? "Garis hijau = kandidat lolos kriteria CPA simulasi saja; batas ruang udara, cuaca dan manuver belum diperiksa."
                            : chosenRoute.potential_conflicts > 0
                            ? "Garis oranye = rute alternatif yang MASIH berpotensi konflik; jangan dianggap sebagai rekomendasi aman."
                            : "Garis abu-abu = analisis tidak lengkap; belum ada kesimpulan aman."}
                        </p>
                      </div>
                    )}
                    <p className="route-evaluation-footnote">
                      Sumber: {routeResultShown.source === "demo" ? "Demo sintetis" : "OpenSky aktual"} ·
                      Snapshot: {formatTime(routeResultShown.snapshot_time_utc)} ·
                      Evaluasi ini adalah simulasi Pre-Flight dan bukan izin terbang.
                    </p>
                  </>
                )}
              </section>

              <section className="hermes-advisor-section" aria-label="Analisis Hermes AI Agent">
                <div className="hermes-advisor-heading">
                  <div>
                    <h3>✦ Hermes AI Advisor</h3>
                    <p>Analisis konflik dan rekomendasi mitigasi.</p>
                  </div>
                  <span className="hermes-label">AI · LOCAL GATEWAY</span>
                </div>
                <button type="button" className="hermes-advice-button"
                  disabled={!routeResultShown || topSixRoutes.length === 0 ||
                    flightStarted || routeLoading || hermesLoading || creating}
                  onClick={requestHermesAdvice}>
                  {hermesLoading ? "Hermes sedang menganalisis..." : "✦ Analisis dengan Hermes"}
                </button>
                {!routeResultShown && (
                  <p className="hermes-help">Jalankan “Cari 6 Jalur Terbaik” dahulu untuk menyiapkan data CPA.</p>
                )}
                {hermesError && (
                  <p className="error-text" role="alert">Hermes: {hermesError}</p>
                )}
                {hermesShown && (
                  <div className="hermes-answer" aria-live="polite">
                    <div className="hermes-answer-header">
                      <strong>Hasil penjelasan Hermes</strong>
                      <span>Model via OpenRouter</span>
                    </div>
                    <div className="hermes-facts">
                      <span>Konflik awal: <strong>{hermesShown.facts?.original_conflicts ?? "-"}</strong></span>
                      <span>Kandidat diuji: <strong>{hermesShown.facts?.evaluated_candidates ?? "-"}</strong></span>
                      <span>Kandidat lolos: <strong>{hermesShown.facts?.eligible_candidate_count ?? "-"}</strong></span>
                    </div>
                    <div className="hermes-answer-text">{hermesShown.advice}</div>
                    <p className="hermes-disclaimer">
                      Hasil AI hanya penjelasan. Simulasi bukan izin terbang.
                    </p>
                  </div>
                )}
              </section>

              <section className="agentic-planner-section" aria-label="Hermes Agentic Flight Planner">
                <div className="hermes-advisor-heading">
                  <div>
                    <h3>✦ Hermes Flight Planner · Agentic</h3>
                    <p>Rekomendasi Agent berdasarkan mitigasi terbaik.</p>
                  </div>
                  <span className="hermes-label">AGENT → CPA</span>
                </div>
                <button type="button" className="hermes-advice-button"
                  onClick={requestAgentPlan}
                  disabled={!!appliedMitigation || !routeResultShown || flightStarted || agentPlanLoading ||
                    preflightLoading || routeLoading || creating || missionChanged || preflightOutdated}>
                  {agentPlanLoading ? "Hermes sedang menguji usulan (maks. 3 langkah)..." :
                    "✦ Cari Mitigasi dengan Hermes"}
                </button>
                {!routeResultShown && (
                  <p className="hermes-help">Jalankan “Cari 6 Jalur Terbaik” dahulu. Jika mitigasi sudah diterapkan, kembali ke rencana awal untuk membandingkan kandidat baru.</p>
                )}
                {agentPlanError && <p className="error-text" role="alert">Agent Planner: {agentPlanError}</p>}
                {agentPlanShown && (
                  <div className="agentic-result" aria-live="polite">
                    <div className="agentic-result-summary">
                      <span>Konflik awal: <strong>{agentPlanShown.original_route?.potential_conflicts ?? "-"}</strong></span>
                      <span>Usulan: <strong>{agentPlanShown.attempt_count ?? 0}</strong></span>
                      <span>Lolos CPA: <strong>{agentPlanShown.eligible_count ?? 0}</strong></span>
                    </div>
                    <p className={`agentic-result-notice ${agentPlanShown.recommended_action ? "eligible" : "caution"}`}>
                      {agentPlanShown.summary}
                    </p>
                    <div className="agentic-actions-list">
                      {(agentPlanShown.attempts || []).map((attempt) => {
                        const good = attempt.cpa_candidate_eligible === true;
                        const exists = typeof attempt.potential_conflicts === "number";
                        const name = attempt.tool === "evaluate_route" ? "Ubah jalur" :
                          attempt.tool === "evaluate_altitude" ? "Ubah ketinggian" :
                          attempt.tool === "evaluate_delay" ? "Tunda keberangkatan" : "Gagal merancang usulan";
                        const chosen = agentSelectedId === attempt.attempt_id;
                        return (
                          <button type="button" key={attempt.attempt_id}
                            className={`agentic-action-card ${chosen ? "selected" : ""} ${good ? "eligible" : exists ? "conflict" : "uncertain"}`}
                            onClick={() => previewAgentAttempt(attempt)}
                            disabled={!exists}
                            aria-pressed={chosen}>
                            <strong>{attempt.attempt_id} · {name}</strong>
                            {exists ? (
                              <span>{attempt.potential_conflicts} konflik · Alt {attempt.altitude_m} m ·
                                {attempt.delay_s > 0 ? ` Delay ${attempt.delay_s} s ·` : ""}
                                {attempt.extra_distance_m > 0 ? ` +${formatMeters(attempt.extra_distance_m)} ·` : ""}
                                {good ? " Lolos CPA" : " Belum lolos CPA"}</span>
                            ) : <span>Usulan ditolak: {attempt.error || "Hasil tidak tersedia"}</span>}
                            {attempt.reason && <small>Usulan Hermes: {attempt.reason}</small>}
                          </button>
                        );
                      })}
                    </div>
                    {selectedAgentAttempt && (
                      <p className="agentic-detail-note">
                        {selectedAgentRoute
                          ? "Garis pilihan di peta adalah hasil waypoint Hermes yang SUDAH dihitung Python; warnanya mengikuti CPA, bukan klaim AI."
                          : "Mitigasi ketinggian/penundaan tidak mengubah bentuk rute horizontal. Hasilnya terdapat pada kartu; rute pada peta tetap rute awal."}
                      </p>
                    )}
                    {selectedAgentAttempt && (
                      <div className="agent-apply-panel">
                        <strong>Pratinjau: {selectedAgentAttempt.attempt_id}</strong>
                        {selectedAgentAttempt.tool === "evaluate_route" && <p>Rute alternatif digambar di peta. Jika diterapkan, waypoint ini menggantikan lintasan simulasi awal.</p>}
                        {selectedAgentAttempt.tool === "evaluate_altitude" && <p>Garis peta tetap sama karena koordinat horizontal tidak berubah. Altitude simulasi akan menjadi {selectedAgentAttempt.altitude_m} m secara konstan; transisi naik/turun belum dimodelkan.</p>}
                        {selectedAgentAttempt.tool === "evaluate_delay" && <p>Garis peta tetap sama. Simulasi akan berhenti di titik awal selama {selectedAgentAttempt.delay_s} detik sebelum bergerak.</p>}
                        <button type="button" className="agent-apply-button"
                          disabled={applyingAgent || !selectedAgentAttempt.cpa_candidate_eligible ||
                            selectedAgentAttempt.data_quality_status !== "COMPLETE_ANALYSIS" ||
                            !selectedAgentAttempt.route_coverage_complete ||
                            !agentPlanShown.geographic_coverage_complete ||
                            flightStarted || creating}
                          onClick={applyAgentToSimulation}>
                          {applyingAgent ? "Menerapkan rencana..." : "✓ Terapkan ke Simulasi (CPA ulang)"}
                        </button>
                        {!selectedAgentAttempt.cpa_candidate_eligible && <small>Kandidat ini belum memenuhi kriteria CPA, jadi hanya boleh dipratinjau.</small>}
                      </div>
                    )}
                    <p className="hermes-disclaimer">
                      Status berasal dari CPA Python, bukan Hermes. Snapshot:
                      {" "}{formatTime(agentPlanShown.snapshot_time_utc)}. Bukan izin terbang;
                      restriksi ruang udara, cuaca, terrain, kemampuan manuver dan
                      profil pendakian belum dievaluasi.
                    </p>
                  </div>
                )}
              </section>
              </>
            )}
          </section>
        </section>

        <aside className="right-panel">
          <section className="telemetry-section">
            <h2>Flight Telemetry</h2>
            {[
              ["Status", status],
              ["Latitude", current?.latitude?.toFixed(6) ?? "-"],
              ["Longitude", current?.longitude?.toFixed(6) ?? "-"],
              ["Altitude", current ? `${Number(current.altitude_m).toFixed(1)} m` : "-"],
              ["Distance Traveled", `${traveled.toFixed(1)} m`],
              ["Total Distance", `${plan?.mission.distance_m ?? "-"} m`],
              ["Flight Time", `${elapsed.toFixed(1)} s`],
              ["Progress", `${progress.toFixed(1)}%`],
            ].map(([label, value]) => (
              <div className="stat" key={label}>
                <span>{label}</span><strong>{value}</strong>
              </div>
            ))}
          </section>

          <section className="traffic-section">
            <div className="traffic-heading">
              <h2>Air Traffic (OpenSky)</h2>
              <span>{trafficLoading ? "Memuat..." : "Snapshot"}</span>
            </div>
            <div className="traffic-summary">
              {[
                ["Dalam radius", traffic?.in_radius_count ?? "-"],
                ["Lolos filter", traffic?.count ?? "-"],
                ["Pesawat ditampilkan", traffic?.visible_count ?? "-"],
                ["Total OpenSky", traffic?.total_received ?? "-"],
                ["Radius aktif", `${radiusKm} km`],
              ].map(([key, value]) => (
                <div className="stat" key={key}>
                  <span>{key}</span><strong>{value}</strong>
                </div>
              ))}
              <div className="snapshot-time">
                Snapshot: {formatTime(traffic?.snapshot_time_utc)}
              </div>
              <div className="snapshot-time">
                Pusat scan: {traffic?.center
                  ? `${Number(traffic.center.latitude).toFixed(4)}, ${Number(traffic.center.longitude).toFixed(4)}`
                  : "-"}
              </div>
              <div className="speed-row refresh-row">
                <label htmlFor="refresh">Refresh OpenSky</label>
                <select id="refresh" value={refreshSeconds}
                  onChange={(e) => setRefreshSeconds(Number(e.target.value))}>
                  <option value={15}>15 detik (demo)</option>
                  <option value={30}>30 detik</option>
                  <option value={60}>60 detik</option>
                </select>
              </div>
              <button className="scan-button" disabled={!plan || trafficLoading}
                onClick={() => setScanNonce((old) => old + 1)}>↻ Scan sekarang</button>
              {trafficError && <p className="error-text">OpenSky: {trafficError}</p>}
            </div>
            <div className="aircraft-list">
              {(traffic?.aircraft || []).map((p, index) => (
                <div className={`aircraft-item ${p.in_radius ? "" : "outside-range"}`}
                  key={`${p.icao24 || p.callsign || "plane"}-${index}`}>
                  <strong>✈ {p.callsign || "UNKNOWN"}
                    <span className="aircraft-status">
                      {p.in_radius
                        ? p.monitored ? "DALAM RADIUS" : "DALAM RADIUS · ALT TIDAK LOLOS"
                        : "DI LUAR RADIUS"}
                    </span>
                  </strong>
                  <small>
                    {p.altitude_m == null ? "Altitude tidak tersedia" :
                      `${Number(p.altitude_m).toFixed(0)} m baro`}
                    {" · "}{Number(p.distance_km).toFixed(1)} km dari pusat scan
                  </small>
                </div>
              ))}
              {traffic?.visible_count === 0 &&
                <p className="muted">Tidak ada pesawat berposisi valid pada snapshot ini.</p>}
            </div>
          </section>
        </aside>
      </main>
    </div>
  );
}

export default App;
