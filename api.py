"""FastAPI backend AI Airspace Conflict Advisor — tahap 6B.2."""

import requests
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from flight_plan import generate_flight_plan
from aircraft_service import get_nearby_aircraft, get_snapshot
from simulator import haversine_km
from cpa_api_service import analyze_flight_plan, make_demo_snapshot
from inflight_cpa_service import analyze_inflight
from cpa_visualization import attach_conflict_geometry
from route_evaluator import evaluate_route_candidates
from hermes_advisor_api import router as hermes_advisor_router
from agent_planner_api import router as agent_planner_router
from inflight_advisor_api import router as inflight_advisor_router
from simulation_plan import build_simulation_plan

app = FastAPI(title="AI Airspace Conflict Advisor", version="0.9.0")
app.include_router(hermes_advisor_router)
app.include_router(agent_planner_router)
app.include_router(inflight_advisor_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class FlightPlanRequest(BaseModel):
    start_lat: float = Field(default=-6.1754, ge=-85, le=85)
    start_lon: float = Field(default=106.8272, ge=-180, le=180)
    end_lat: float = Field(default=-6.1600, ge=-85, le=85)
    end_lon: float = Field(default=106.8500, ge=-180, le=180)
    altitude_m: float = Field(default=150, ge=0, le=3300)
    speed_mps: float = Field(default=10, gt=0, le=100)
    time_step_s: float = Field(default=30, gt=0, le=300)
    control_points: list[list[float]] | None = Field(default=None, min_length=2, max_length=4)
    delay_s: float = Field(default=0, ge=0, le=240)
    # Jika menerapkan mitigasi pada Demo, pesawat sintetis selalu dibuat
    # dari rute ASLI sehingga tidak bergeser mengikuti altitude/route usulan.
    demo_reference_altitude_m: float | None = Field(default=None, ge=0, le=3300)
    demo_reference_control_points: list[list[float]] | None = Field(default=None, min_length=2, max_length=4)


class ConflictAnalysisRequest(FlightPlanRequest):
    radius_km: float = Field(default=70, ge=1, le=150)
    source: Literal["demo", "opensky"] = "demo"


class RouteRecommendationRequest(ConflictAnalysisRequest):
    offsets_m: list[float] = Field(
        default_factory=lambda: [500, 1000, 1500],
        min_length=1,
        max_length=10,
    )
    bend_fraction: float = Field(default=0.5, ge=0.1, le=0.9)
    # Opsional: bila diisi, aktifkan pencarian multi-posisi.
    # Tanpa field ini endpoint lama tetap mengevaluasi 6 kandidat.
    bend_fractions: list[float] | None = Field(
        default=None, min_length=1, max_length=5,
    )


class InFlightAnalysisRequest(ConflictAnalysisRequest):
    elapsed_s: float = Field(default=0, ge=0)


def build_flight_plan(data: FlightPlanRequest):
    if data.control_points is not None or data.delay_s > 0:
        return build_simulation_plan(
            start_lat=data.start_lat, start_lon=data.start_lon,
            end_lat=data.end_lat, end_lon=data.end_lon,
            altitude_m=data.altitude_m, speed_mps=data.speed_mps,
            time_step_s=data.time_step_s,
            control_points=data.control_points, delay_s=data.delay_s,
            route_id="APPLIED_HERMES_SIMULATION",
        )
    return generate_flight_plan(
        start_lat=data.start_lat,
        start_lon=data.start_lon,
        end_lat=data.end_lat,
        end_lon=data.end_lon,
        altitude_m=data.altitude_m,
        speed_mps=data.speed_mps,
        time_step_s=data.time_step_s,
    )


def build_demo_reference_plan(data: FlightPlanRequest):
    if data.demo_reference_altitude_m is None:
        return None
    return build_simulation_plan(
        start_lat=data.start_lat, start_lon=data.start_lon,
        end_lat=data.end_lat, end_lon=data.end_lon,
        altitude_m=data.demo_reference_altitude_m,
        speed_mps=data.speed_mps, time_step_s=data.time_step_s,
        control_points=data.demo_reference_control_points,
        delay_s=0, route_id="REFERENCE_DEMO_ORIGINAL",
    )


def report_http_error(error):
    status = error.response.status_code if error.response is not None else None
    if status == 429:
        detail = "Kredit/rate limit OpenSky tercapai. Coba interval lebih panjang."
    elif status in (401, 403):
        detail = "Autentikasi atau izin OpenSky ditolak. Periksa .env."
    else:
        detail = f"OpenSky HTTP {status or 'error'}"
    return HTTPException(status_code=503, detail=detail)


@app.get("/")
def home():
    return {"message": "AI Airspace Conflict Advisor API", "status": "running", "mode": "simulation"}


@app.get("/health")
def health():
    return {"status": "healthy", "mode": "simulation"}


@app.get("/api/flight-plan")
def default_flight_plan():
    return generate_flight_plan()


@app.post("/api/flight-plan")
def create_flight_plan(data: FlightPlanRequest):
    try:
        return build_flight_plan(data)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/aircraft")
def nearby_aircraft(
    center_lat: float = Query(-6.1754, ge=-85, le=85),
    center_lon: float = Query(106.8272, ge=-180, le=180),
    drone_altitude_m: float = Query(150, ge=0, le=3300),
    radius_km: float = Query(70, ge=1, le=150),
    max_altitude_m: float = Query(3300, ge=0, le=3300),
):
    try:
        return get_nearby_aircraft(
            center_lat=center_lat,
            center_lon=center_lon,
            drone_altitude_m=drone_altitude_m,
            radius_km=radius_km,
            max_altitude_m=max_altitude_m,
        )
    except requests.HTTPError as error:
        raise report_http_error(error) from error
    except requests.RequestException as error:
        raise HTTPException(status_code=503, detail="Koneksi OpenSky gagal atau timeout") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/conflict-analysis")
def conflict_analysis(data: ConflictAnalysisRequest):
    try:
        plan = build_flight_plan(data)
        now_epoch = datetime.now(timezone.utc).timestamp()
        cached = False
        coverage_complete = True

        if data.source == "demo":
            demo_reference = build_demo_reference_plan(data)
            snapshot = make_demo_snapshot(demo_reference or plan, now_epoch)
        else:
            route = plan["waypoints"]
            center_lat = (route[0]["latitude"] + route[-1]["latitude"]) / 2
            center_lon = (route[0]["longitude"] + route[-1]["longitude"]) / 2
            route_offset_km = max(
                haversine_km(
                    center_lat, center_lon,
                    point["latitude"], point["longitude"],
                )
                for point in route
            )
            needed_km = data.radius_km + route_offset_km
            coverage_complete = needed_km <= 150
            snapshot, _, _, cached = get_snapshot(
                center_lat, center_lon, min(150, needed_km)
            )
            now_epoch = datetime.now(timezone.utc).timestamp()

        result = analyze_flight_plan(
            plan,
            snapshot,
            source=data.source,
            departure_epoch=now_epoch,
            coverage_complete=coverage_complete,
            cached=cached,
        )
        return attach_conflict_geometry(result, plan, snapshot, now_epoch)
    except requests.HTTPError as error:
        raise report_http_error(error) from error
    except requests.RequestException as error:
        raise HTTPException(status_code=503, detail="Koneksi OpenSky gagal atau timeout") from error
    except (ValueError, OverflowError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/inflight-analysis")
def inflight_analysis(data: InFlightAnalysisRequest):
    """Evaluasi sisa lintasan dari progres drone simulasi saat ini."""
    try:
        plan = build_flight_plan(data)
        return analyze_inflight(
            plan,
            elapsed_s=data.elapsed_s,
            radius_km=data.radius_km,
            source=data.source,
            demo_reference_plan=(build_demo_reference_plan(data) if data.source == "demo" else None),
        )
    except requests.HTTPError as error:
        raise report_http_error(error) from error
    except requests.RequestException as error:
        raise HTTPException(status_code=503, detail="Koneksi OpenSky gagal atau timeout") from error
    except (ValueError, OverflowError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/route-recommendation")
def route_recommendation(data: RouteRecommendationRequest):
    """Uji rute awal dan kandidat dengan snapshot dan waktu yang sama."""
    try:
        return evaluate_route_candidates(
            start_lat=data.start_lat,
            start_lon=data.start_lon,
            end_lat=data.end_lat,
            end_lon=data.end_lon,
            altitude_m=data.altitude_m,
            speed_mps=data.speed_mps,
            time_step_s=data.time_step_s,
            radius_km=data.radius_km,
            source=data.source,
            offsets_m=data.offsets_m,
            bend_fraction=data.bend_fraction,
            bend_fractions=data.bend_fractions,
        )
    except requests.HTTPError as error:
        raise report_http_error(error) from error
    except requests.RequestException as error:
        raise HTTPException(
            status_code=503,
            detail="Koneksi OpenSky gagal atau timeout",
        ) from error
    except (ValueError, OverflowError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
