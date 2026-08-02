"""
routes_api.py — FastAPI router for the /generate-route endpoint.

Mounted in main.py via: app.include_router(routes_router)

POST /generate-route
  Body: GenerateRouteRequest
  Response: GeneratedRouteResponse
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, validator

from app.route_generator import generate_routes, GRADES

logger    = logging.getLogger(__name__)
router    = APIRouter(tags=["Route Generation"])

# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

class HoldInput(BaseModel):
    id:        str
    center_x:  float = Field(..., ge=0.0, le=1.0)
    center_y:  float = Field(..., ge=0.0, le=1.0)
    width:     float = Field(default=0.04, ge=0.0, le=1.0)
    height:    float = Field(default=0.04, ge=0.0, le=1.0)
    type:      str   = "unknown"
    color:     str   = "unknown"


class GenerateRouteRequest(BaseModel):
    wall_id:     str
    holds:       list[HoldInput] = Field(..., min_items=4)
    grade:       str             = Field(default="V5")
    style:       str             = Field(default="dynamic")
    body_type:   str             = Field(default="default")
    hold_count:  int | str       = Field(default="auto")

    # Optional physical dimensions for real-world distance calculations
    wall_width_cm:  float = Field(default=244.0, gt=50)
    wall_height_cm: float = Field(default=244.0, gt=50)

    # Generation quality controls
    n_candidates:   int   = Field(default=60, ge=10, le=300)
    seed:           Optional[int] = None

    @validator("grade")
    def validate_grade(cls, v):
        if v not in GRADES and v != "auto":
            raise ValueError(f"grade must be one of {GRADES} or 'auto'")
        return v

    @validator("style")
    def validate_style(cls, v):
        allowed = {"dynamic", "balance", "compression", "endurance", "coordination"}
        if v not in allowed:
            raise ValueError(f"style must be one of {allowed}")
        return v

    @validator("body_type")
    def validate_body_type(cls, v):
        if v not in {"default", "tall", "short"}:
            raise ValueError("body_type must be 'default', 'tall', or 'short'")
        return v

    @validator("hold_count")
    def validate_hold_count(cls, v):
        if isinstance(v, int) and not (4 <= v <= 20):
            raise ValueError("hold_count must be 4–20 or 'auto'")
        if isinstance(v, str) and v != "auto":
            raise ValueError("hold_count must be an integer 4–20 or 'auto'")
        return v


class HoldAssignmentResponse(BaseModel):
    hold_id:        str
    role:           str
    position_order: int


class RouteResponse(BaseModel):
    holds:         list[HoldAssignmentResponse]
    quality_score: float
    grade_actual:  str
    style:         str
    metadata:      dict


class GeneratedRouteResponse(BaseModel):
    wall_id: str
    route:   RouteResponse


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/generate-route",
    response_model=GeneratedRouteResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a climbing route",
    description=(
        "Given a set of detected holds, generate an AI-designed climbing route "
        "matching the requested grade, style, and body type. Returns the best "
        "candidate route with quality score and hold role assignments."
    ),
)
async def generate_route_endpoint(request: GenerateRouteRequest) -> GeneratedRouteResponse:
    """
    POST /generate-route

    Algorithm:
    1. Build a directed hold graph constrained by grade-specific reach parameters.
    2. Run randomised DFS with constraint pruning to find candidate routes.
    3. Score each candidate with the multi-factor quality heuristic.
    4. Return the highest-scoring route.

    Error codes:
    - INSUFFICIENT_HOLDS   : Fewer than 4 holds provided.
    - INVALID_GRADE        : Grade string not in V0–V16 or 'auto'.
    - NO_VALID_ROUTE       : Algorithm couldn't find a valid path — try different grade.
    - NO_REACHABLE_PAIRS   : No holds within reach range — check hold positions/grade.
    """
    logger.info(
        "generate-route: wall=%s grade=%s style=%s holds=%d",
        request.wall_id, request.grade, request.style, len(request.holds)
    )

    holds_data = [h.dict() for h in request.holds]

    try:
        routes = generate_routes(
            holds_data      = holds_data,
            grade           = request.grade,
            style           = request.style,
            body_type       = request.body_type,
            hold_count      = request.hold_count,
            wall_width_cm   = request.wall_width_cm,
            wall_height_cm  = request.wall_height_cm,
            n_candidates    = request.n_candidates,
            n_return        = 1,
            seed            = request.seed,
        )
    except ValueError as exc:
        code = "NO_VALID_ROUTE"
        if "≥ 4 holds" in str(exc):
            code = "INSUFFICIENT_HOLDS"
        elif "No reachable" in str(exc):
            code = "NO_REACHABLE_PAIRS"

        logger.warning("generate-route failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": code, "message": str(exc)}},
        )

    best = routes[0]
    api_dict = best.to_api_dict()["route"]

    return GeneratedRouteResponse(
        wall_id=request.wall_id,
        route=RouteResponse(
            holds         = [HoldAssignmentResponse(**h) for h in api_dict["holds"]],
            quality_score = api_dict["quality_score"],
            grade_actual  = api_dict["grade_actual"],
            style         = api_dict["style"],
            metadata      = api_dict["metadata"],
        ),
    )
