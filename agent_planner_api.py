"""FastAPI endpoint for bounded Hermes tool-proposal/CPA-feedback workflow."""
from __future__ import annotations

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

from agent_flight_planner import run_agent_flight_planner
from hermes_client import HermesGatewayError

router = APIRouter(tags=["Hermes Agentic Flight Planner"])


class AgentPlannerRequest(BaseModel):
    start_lat: float = Field(ge=-85, le=85)
    start_lon: float = Field(ge=-180, le=180)
    end_lat: float = Field(ge=-85, le=85)
    end_lon: float = Field(ge=-180, le=180)
    altitude_m: float = Field(ge=50, le=3300)
    speed_mps: float = Field(gt=0, le=100)
    time_step_s: float = Field(gt=0, le=300)
    radius_km: float = Field(ge=1, le=150)
    source: Literal['demo', 'opensky'] = 'demo'
    max_steps: int = Field(default=3, ge=1, le=3)


@router.post('/api/agent-plan')
def agent_plan(data: AgentPlannerRequest):
    """Demo and OpenSky plans are what-if predictions, not operational actions."""
    try:
        return run_agent_flight_planner(**data.model_dump())
    except HermesGatewayError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        detail = 'OpenSky membatasi akses (429).' if status == 429 else 'OpenSky tidak tersedia untuk simulasi.'
        raise HTTPException(status_code=503, detail=detail) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail='Tidak dapat memperoleh snapshot OpenSky.') from exc
    except (ValueError, OverflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
