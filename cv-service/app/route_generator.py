"""
route_generator.py — AI Route Generation Engine

Implements a graph-based Constraint Satisfaction Problem (CSP) approach to
generating climbing routes from a set of detected holds.

Architecture:
  1. HoldGraph      — directed weighted graph of reachable hold pairs
  2. GradeProfile   — per-grade parameter constraints
  3. RouteGenerator — randomised DFS with constraint pruning + scoring
  4. RouteRanker    — abstract interface for future ML ranking
  5. generate_routes() — main entry point

Coordinate system:
  All hold positions are normalised [0.0, 1.0] relative to the wall image.
  Real-world distances are computed using configurable wall dimensions (cm).
  y=0.0 is the TOP of the wall; y=1.0 is the BOTTOM.

Grade → Difficulty mapping (V-scale, Hueco):
  V0–V3  : Beginner     (large holds, short reaches, more holds)
  V4–V6  : Intermediate (mixed holds, moderate reaches)
  V7–V10 : Advanced     (small holds, longer reaches, fewer options)
  V11–V16: Elite        (crimp-heavy, full-span moves, minimal holds)
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WALL_WIDTH_CM  = 244
DEFAULT_WALL_HEIGHT_CM = 244

# V-scale grade list (index = numeric grade)
GRADES = ["V0","V1","V2","V3","V4","V5","V6","V7","V8","V9",
          "V10","V11","V12","V13","V14","V15","V16"]

# Hold type difficulty contribution (higher = harder hold to use)
HOLD_DIFFICULTY: dict[str, float] = {
    "jug":      0.10,
    "volume":   0.20,
    "sloper":   0.55,
    "pinch":    0.60,
    "pocket":   0.65,
    "crimp":    0.80,
    "foothold": 0.15,
    "unknown":  0.40,
}

# Hold type size proxy (larger area → easier)
HOLD_SIZE_EASE: dict[str, float] = {
    "jug":      0.90,
    "volume":   0.85,
    "sloper":   0.55,
    "pinch":    0.50,
    "pocket":   0.45,
    "crimp":    0.20,
    "foothold": 0.60,
    "unknown":  0.50,
}


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Hold:
    """
    Immutable hold representation inside the route generator.
    Coordinates are normalised [0, 1]; y=0 = top of wall.
    """
    id:        str
    center_x:  float
    center_y:  float   # 0 = top, 1 = bottom
    width:     float
    height:    float
    type:      str = "unknown"
    color:     str = "unknown"

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def size_ease(self) -> float:
        """Ease contribution from hold size + type (0 = hardest, 1 = easiest)."""
        type_ease  = HOLD_SIZE_EASE.get(self.type, 0.5)
        # Larger normalised area also contributes slightly
        area_bonus = min(self.area * 50, 0.2)
        return min(type_ease + area_bonus, 1.0)

    def real_distance_cm(
        self,
        other: "Hold",
        wall_width_cm:  float = DEFAULT_WALL_WIDTH_CM,
        wall_height_cm: float = DEFAULT_WALL_HEIGHT_CM,
    ) -> float:
        """Euclidean distance to another hold in real-world centimetres."""
        dx = (self.center_x - other.center_x) * wall_width_cm
        dy = (self.center_y - other.center_y) * wall_height_cm
        return math.sqrt(dx * dx + dy * dy)

    def is_above(self, other: "Hold") -> bool:
        """Return True if this hold is higher on the wall (smaller y value)."""
        return self.center_y < other.center_y


class RouteStyle(str, Enum):
    DYNAMIC      = "dynamic"
    BALANCE      = "balance"
    COMPRESSION  = "compression"
    ENDURANCE    = "endurance"
    COORDINATION = "coordination"


class BodyType(str, Enum):
    DEFAULT = "default"
    TALL    = "tall"
    SHORT   = "short"


@dataclass
class HoldAssignment:
    """A hold with its assigned role within a route."""
    hold:           Hold
    role:           str    # start | hand | foot | finish
    position_order: int


@dataclass
class GeneratedRoute:
    """A complete candidate route with its quality score."""
    holds:         list[HoldAssignment]
    quality_score: float
    grade_actual:  str
    style:         str
    metadata:      dict = field(default_factory=dict)

    def to_api_dict(self) -> dict:
        return {
            "route": {
                "holds": [
                    {
                        "hold_id":        a.hold.id,
                        "role":           a.role,
                        "position_order": a.position_order,
                    }
                    for a in self.holds
                ],
                "quality_score": round(self.quality_score, 4),
                "grade_actual":  self.grade_actual,
                "style":         self.style,
                "metadata":      self.metadata,
            }
        }


# ---------------------------------------------------------------------------
# Grade Profiles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GradeProfile:
    """
    Per-grade constraint parameters.

    reach_min_cm / reach_max_cm:
        Acceptable distance range between consecutive hand holds (cm).
        Lower range = more static/controlled movement.
        Upper range = more dynamic/powerful movement.

    hold_count_min / hold_count_max:
        Total hand holds in the route (excluding foot-only holds).

    small_hold_probability:
        Probability of selecting a smaller hold type (crimp, pocket)
        vs a larger hold (jug, sloper). Increases with grade.

    foot_hold_ratio:
        Approximate fraction of total holds that should be foot holds.
        Higher ratio → balance-oriented routes.

    max_consecutive_vertical:
        Maximum consecutive moves that are purely vertical (no lateral shift).
        Prevents boring straight-up routes.
    """
    grade:                    str
    reach_min_cm:             float
    reach_max_cm:             float
    hold_count_min:           int
    hold_count_max:           int
    small_hold_probability:   float
    foot_hold_ratio:          float
    max_consecutive_vertical: int
    difficulty_target:        float   # 0.0 = easy, 1.0 = hard


_GRADE_PROFILES: dict[str, GradeProfile] = {
    g: GradeProfile(
        grade                    = g,
        reach_min_cm             = v[0],
        reach_max_cm             = v[1],
        hold_count_min           = v[2],
        hold_count_max           = v[3],
        small_hold_probability   = v[4],
        foot_hold_ratio          = v[5],
        max_consecutive_vertical = v[6],
        difficulty_target        = v[7],
    )
    for g, v in {
    #  grade   rMin  rMax  hMin  hMax  smallP  footR  maxVert  diff
    "V0":  [18,   42,   5,    9,    0.05,  0.30,  2,      0.05],
    "V1":  [20,   48,   5,    9,    0.10,  0.30,  2,      0.12],
    "V2":  [22,   52,   6,   10,    0.18,  0.28,  3,      0.20],
    "V3":  [24,   58,   6,   11,    0.27,  0.26,  3,      0.28],
    "V4":  [26,   63,   7,   12,    0.36,  0.25,  3,      0.37],
    "V5":  [28,   68,   7,   13,    0.44,  0.24,  4,      0.46],
    "V6":  [30,   73,   8,   14,    0.52,  0.22,  4,      0.54],
    "V7":  [32,   78,   8,   15,    0.60,  0.20,  4,      0.62],
    "V8":  [34,   83,   8,   16,    0.67,  0.18,  5,      0.70],
    "V9":  [36,   88,   8,   17,    0.74,  0.16,  5,      0.77],
    "V10": [38,   93,   8,   18,    0.80,  0.15,  5,      0.84],
    "V11": [40,   97,   8,   19,    0.86,  0.12,  6,      0.89],
    "V12": [42,  100,   8,   20,    0.90,  0.10,  6,      0.93],
    "V13": [44,  104,   7,   18,    0.93,  0.08,  6,      0.95],
    "V14": [46,  108,   6,   16,    0.95,  0.06,  7,      0.97],
    "V15": [48,  112,   5,   14,    0.97,  0.05,  7,      0.98],
    "V16": [50,  118,   4,   12,    0.99,  0.04,  8,      1.00],
    }.items()
}


def get_grade_profile(grade: str) -> GradeProfile:
    if grade not in _GRADE_PROFILES:
        raise ValueError(f"Unknown grade: {grade}. Valid grades: {list(_GRADE_PROFILES.keys())}")
    return _GRADE_PROFILES[grade]


def apply_body_type_adjustment(
    profile: GradeProfile,
    body_type: BodyType,
) -> GradeProfile:
    """
    Adjust reach parameters for body type.
    Tall climbers can reach further; short climbers reach less.
    Returns a modified copy (GradeProfile is frozen, so we rebuild).
    """
    factor = {
        BodyType.TALL:    1.15,
        BodyType.SHORT:   0.87,
        BodyType.DEFAULT: 1.00,
    }[body_type]

    return GradeProfile(
        grade                    = profile.grade,
        reach_min_cm             = profile.reach_min_cm * factor,
        reach_max_cm             = profile.reach_max_cm * factor,
        hold_count_min           = profile.hold_count_min,
        hold_count_max           = profile.hold_count_max,
        small_hold_probability   = profile.small_hold_probability,
        foot_hold_ratio          = profile.foot_hold_ratio,
        max_consecutive_vertical = profile.max_consecutive_vertical,
        difficulty_target        = profile.difficulty_target,
    )


def apply_style_adjustment(
    profile:      GradeProfile,
    style:        RouteStyle,
    hold_count:   int | str = "auto",
) -> GradeProfile:
    """
    Adjust grade parameters for climbing style.

    dynamic:     Larger moves (increase max reach), fewer holds
    balance:     More foot holds, shorter moves
    compression: Body tension — shorter reaches, more crimps preferred
    endurance:   Many holds, moderate distances
    coordination: Timing-sensitive — high move variety enforced
    """
    adjustments: dict[RouteStyle, dict] = {
        RouteStyle.DYNAMIC:     {"reach_max_cm": 1.20, "foot_hold_ratio": 0.80, "hold_count_max": 0.75},
        RouteStyle.BALANCE:     {"reach_max_cm": 0.85, "foot_hold_ratio": 1.40, "hold_count_max": 1.10},
        RouteStyle.COMPRESSION: {"reach_max_cm": 0.80, "small_hold_probability": 1.15},
        RouteStyle.ENDURANCE:   {"hold_count_min": 1.30, "hold_count_max": 1.30, "reach_max_cm": 0.90},
        RouteStyle.COORDINATION:{"reach_max_cm": 1.10},
    }
    adj = adjustments.get(style, {})

    return GradeProfile(
        grade                    = profile.grade,
        reach_min_cm             = profile.reach_min_cm,
        reach_max_cm             = min(profile.reach_max_cm * adj.get("reach_max_cm", 1.0), 120),
        hold_count_min           = max(4, int(profile.hold_count_min * adj.get("hold_count_min", 1.0))),
        hold_count_max           = min(20, int(profile.hold_count_max * adj.get("hold_count_max", 1.0))),
        small_hold_probability   = min(0.99, profile.small_hold_probability * adj.get("small_hold_probability", 1.0)),
        foot_hold_ratio          = min(0.50, profile.foot_hold_ratio * adj.get("foot_hold_ratio", 1.0)),
        max_consecutive_vertical = profile.max_consecutive_vertical,
        difficulty_target        = profile.difficulty_target,
    )


# ---------------------------------------------------------------------------
# Hold Graph
# ---------------------------------------------------------------------------

@dataclass
class HoldEdge:
    """A directed edge between two holds with computed properties."""
    source:        Hold
    target:        Hold
    distance_cm:   float
    direction_deg: float   # angle from source → target (0° = right, 90° = up)
    is_upward:     bool    # target is higher on wall


class HoldGraph:
    """
    Directed weighted graph of holds.

    Nodes: holds (Hold objects)
    Edges: reachable pairs within the grade's reach constraints.

    Edge direction is always upward or lateral — we do not allow
    pure downward moves in a standard route (climbers move UP).

    An edge (A → B) exists if:
      1. B is above A (or within 5cm lateral tolerance)
      2. distance(A, B) ∈ [reach_min_cm, reach_max_cm]
    """

    def __init__(
        self,
        holds:          list[Hold],
        profile:        GradeProfile,
        wall_width_cm:  float = DEFAULT_WALL_WIDTH_CM,
        wall_height_cm: float = DEFAULT_WALL_HEIGHT_CM,
    ) -> None:
        self.holds          = holds
        self.profile        = profile
        self.wall_width_cm  = wall_width_cm
        self.wall_height_cm = wall_height_cm

        # Build adjacency list: hold_id → list[HoldEdge]
        self._adjacency: dict[str, list[HoldEdge]] = {h.id: [] for h in holds}
        self._build()

    def _build(self) -> None:
        """Construct all valid directed edges."""
        n = len(self.holds)
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                src = self.holds[i]
                tgt = self.holds[j]

                dist = src.real_distance_cm(tgt, self.wall_width_cm, self.wall_height_cm)

                # Must be within reach range
                if not (self.profile.reach_min_cm <= dist <= self.profile.reach_max_cm):
                    continue

                # Target must be higher or roughly lateral (within 8% wall height)
                vertical_tolerance = 0.08 * self.wall_height_cm
                height_diff_cm     = (src.center_y - tgt.center_y) * self.wall_height_cm

                if height_diff_cm < -vertical_tolerance:
                    # Target is more than tolerance below source — skip
                    continue

                # Compute direction angle (degrees, 0°=right, 90°=up)
                dx  = (tgt.center_x - src.center_x) * self.wall_width_cm
                dy  = (src.center_y - tgt.center_y) * self.wall_height_cm  # positive = upward
                deg = math.degrees(math.atan2(dy, dx))

                self._adjacency[src.id].append(HoldEdge(
                    source        = src,
                    target        = tgt,
                    distance_cm   = dist,
                    direction_deg = deg,
                    is_upward     = tgt.center_y < src.center_y,
                ))

    def neighbours(self, hold_id: str) -> list[HoldEdge]:
        return self._adjacency.get(hold_id, [])

    def edge_count(self) -> int:
        return sum(len(v) for v in self._adjacency.values())

    def start_candidates(self, bottom_fraction: float = 0.25) -> list[Hold]:
        """Holds in the bottom N% of the wall (largest y values)."""
        threshold = 1.0 - bottom_fraction
        return [h for h in self.holds if h.center_y >= threshold]

    def finish_candidates(self, top_fraction: float = 0.20) -> list[Hold]:
        """Holds in the top N% of the wall (smallest y values)."""
        return [h for h in self.holds if h.center_y <= top_fraction]


# ---------------------------------------------------------------------------
# Route Selection — Randomised DFS with Constraint Pruning
# ---------------------------------------------------------------------------

class RouteGenerator:
    """
    Generates candidate routes via randomised DFS on the HoldGraph.

    Algorithm (per attempt):
      1. Pick a random START hold from bottom candidates.
      2. At each step, collect valid next holds from the graph:
         - Must be in the adjacency list (within reach range)
         - Must not have been visited
         - Must not create a >max_consecutive_vertical straight path
         - Hold type must pass the small_hold_probability gate
      3. Randomly sample from valid candidates (weighted by hold ease).
      4. Continue until a FINISH hold is reached or max_holds exceeded.
      5. Prune paths with fewer than min_holds.

    Multiple attempts (default: 50) produce candidate routes that are
    then scored and returned ranked by quality.
    """

    def __init__(
        self,
        graph:   HoldGraph,
        profile: GradeProfile,
        style:   RouteStyle   = RouteStyle.DYNAMIC,
        seed:    Optional[int] = None,
    ) -> None:
        self.graph   = graph
        self.profile = profile
        self.style   = style
        self.rng     = random.Random(seed)

    def generate(
        self,
        n_attempts:         int = 60,
        n_routes_to_return: int = 3,
        hold_count_override: Optional[int] = None,
    ) -> list[GeneratedRoute]:
        """
        Run n_attempts DFS searches and return the top-n routes by quality.

        Args:
            n_attempts:          How many DFS attempts to run.
            n_routes_to_return:  Number of distinct routes to return.
            hold_count_override: If set, override the grade's hold count range.

        Returns:
            List of GeneratedRoute, sorted by quality_score descending.
        """
        target_count_min = hold_count_override or self.profile.hold_count_min
        target_count_max = hold_count_override or self.profile.hold_count_max

        candidates: list[GeneratedRoute] = []
        seen_paths: set[frozenset] = set()

        for attempt in range(n_attempts):
            route = self._single_attempt(target_count_min, target_count_max)
            if route is None:
                continue

            # Deduplicate by hold set (same holds in any order = duplicate)
            hold_set = frozenset(a.hold.id for a in route.holds)
            if hold_set in seen_paths:
                continue
            seen_paths.add(hold_set)

            candidates.append(route)

        if not candidates:
            return []

        # Score and rank
        for route in candidates:
            route.quality_score = self._score(route)

        candidates.sort(key=lambda r: r.quality_score, reverse=True)
        return candidates[:n_routes_to_return]

    def _single_attempt(
        self,
        target_min: int,
        target_max: int,
    ) -> Optional[GeneratedRoute]:
        """
        Single DFS attempt. Returns a GeneratedRoute or None if no valid path found.
        """
        start_candidates = self.graph.start_candidates()
        finish_candidates_set = {h.id for h in self.graph.finish_candidates()}

        if not start_candidates:
            return None

        # Weighted start selection: prefer holds lower on wall
        start = self._weighted_choice(start_candidates, key=lambda h: h.center_y)
        if start is None:
            return None

        path: list[Hold]        = [start]
        visited: set[str]       = {start.id}
        consecutive_vertical    = 0
        prev_direction: Optional[float] = None
        max_attempts_per_step   = 20

        while len(path) < target_max + 2:
            current = path[-1]

            # Check if we can finish here
            if (len(path) >= target_min
                    and current.id in finish_candidates_set
                    and len(path) >= 4):
                break  # Natural finish

            edges = self.graph.neighbours(current.id)
            if not edges:
                break

            # Filter: unvisited targets
            valid_edges = [e for e in edges if e.target.id not in visited]

            if not valid_edges:
                break  # Dead end

            # Style-based filtering
            valid_edges = self._apply_style_filter(valid_edges, prev_direction, consecutive_vertical)

            if not valid_edges:
                break

            # Hold-type difficulty gating
            valid_edges = self._apply_difficulty_filter(valid_edges)
            if not valid_edges:
                break

            # Weighted random choice: prefer hold types appropriate for grade
            chosen_edge = self._choose_edge(valid_edges)
            if chosen_edge is None:
                break

            # Track consecutive vertical moves
            if prev_direction is not None:
                if abs(chosen_edge.direction_deg - 90) < 20:  # Near-vertical
                    consecutive_vertical += 1
                else:
                    consecutive_vertical = 0
            prev_direction = chosen_edge.direction_deg

            path.append(chosen_edge.target)
            visited.add(chosen_edge.target.id)

        # Validate path length
        if len(path) < max(4, target_min):
            return None

        # Trim to target_max if needed
        if len(path) > target_max + 1:
            path = path[:target_max + 1]

        return self._assign_roles(path)

    def _apply_style_filter(
        self,
        edges:                list[HoldEdge],
        prev_direction:       Optional[float],
        consecutive_vertical: int,
    ) -> list[HoldEdge]:
        """Filter edges based on route style constraints."""

        # Prevent too many consecutive vertical moves
        if consecutive_vertical >= self.profile.max_consecutive_vertical:
            # Force a lateral component (|angle from 90°| > 25°)
            edges = [e for e in edges if abs(e.direction_deg - 90) > 25]

        if self.style == RouteStyle.DYNAMIC:
            # Prefer longer moves
            edges_long = [e for e in edges if e.distance_cm >= self.profile.reach_min_cm * 1.4]
            return edges_long or edges

        if self.style == RouteStyle.BALANCE:
            # Prefer moves with significant lateral component (footwork)
            edges_lateral = [e for e in edges if abs(e.direction_deg - 90) > 30]
            return edges_lateral or edges

        if self.style == RouteStyle.COMPRESSION:
            # Prefer shorter, more controlled moves
            mid = (self.profile.reach_min_cm + self.profile.reach_max_cm) / 2
            edges_short = [e for e in edges if e.distance_cm <= mid]
            return edges_short or edges

        if self.style == RouteStyle.ENDURANCE:
            # No filtering — want many moves, any direction
            return edges

        if self.style == RouteStyle.COORDINATION:
            # Vary direction significantly from previous move
            if prev_direction is not None:
                edges_varied = [
                    e for e in edges
                    if abs(e.direction_deg - prev_direction) > 40
                ]
                return edges_varied or edges

        return edges

    def _apply_difficulty_filter(self, edges: list[HoldEdge]) -> list[HoldEdge]:
        """
        Gate hold type selection based on grade's small_hold_probability.
        Easy grades strongly prefer large holds (jugs, volumes).
        Hard grades prefer small holds (crimps, pockets).
        """
        p = self.profile.small_hold_probability

        # Split into easy/hard holds
        easy  = [e for e in edges if HOLD_DIFFICULTY.get(e.target.type, 0.5) < 0.5]
        hard  = [e for e in edges if HOLD_DIFFICULTY.get(e.target.type, 0.5) >= 0.5]

        if easy and hard:
            # Blend based on probability
            if self.rng.random() < p:
                return hard or easy
            else:
                return easy or hard

        return edges  # Return all if only one category available

    def _choose_edge(self, edges: list[HoldEdge]) -> Optional[HoldEdge]:
        """
        Weighted random edge selection.
        Weight = ease of target hold (easier holds weighted down for hard grades).
        """
        p = self.profile.small_hold_probability

        weights = []
        for edge in edges:
            ease = edge.target.size_ease
            # Invert ease for high-grade routes (prefer hard holds)
            w = (1.0 - ease) * p + ease * (1.0 - p)
            weights.append(max(w, 0.01))  # Ensure positive weight

        total = sum(weights)
        cumulative = 0.0
        r = self.rng.random() * total
        for edge, w in zip(edges, weights):
            cumulative += w
            if r <= cumulative:
                return edge

        return edges[-1]  # Fallback

    def _weighted_choice(self, holds: list[Hold], key) -> Optional[Hold]:
        if not holds:
            return None
        weights = [key(h) for h in holds]
        total = sum(weights)
        r = self.rng.random() * total
        cumulative = 0.0
        for h, w in zip(holds, weights):
            cumulative += w
            if r <= cumulative:
                return h
        return holds[-1]

    def _assign_roles(self, path: list[Hold]) -> GeneratedRoute:
        """
        Assign roles to holds in the path.
        Rules:
          - First hold(s) → start
          - Last hold → finish
          - Foot hold ratio applied to interior holds
          - Remaining interior holds → hand
        """
        assignments: list[HoldAssignment] = []
        n = len(path)
        foot_target = max(0, round((n - 2) * self.profile.foot_hold_ratio))
        foot_count  = 0

        for idx, hold in enumerate(path):
            if idx == 0:
                role = "start"
            elif idx == n - 1:
                role = "finish"
            elif (hold.type == "foothold"
                  or (foot_count < foot_target and self.style == RouteStyle.BALANCE)):
                role = "foot"
                foot_count += 1
            else:
                role = "hand"

            assignments.append(HoldAssignment(
                hold           = hold,
                role           = role,
                position_order = idx + 1,
            ))

        actual_grade = self._estimate_actual_grade(path)

        return GeneratedRoute(
            holds        = assignments,
            quality_score= 0.0,   # Will be set by scorer
            grade_actual  = actual_grade,
            style        = self.style.value,
            metadata     = {
                "total_holds":        n,
                "foot_holds":         foot_count,
                "hand_holds":         n - foot_count - 2,
            },
        )

    def _estimate_actual_grade(self, path: list[Hold]) -> str:
        """
        Estimate the actual difficulty of a generated route based on:
        - Average hold difficulty
        - Average reach distance
        - Hold count (more holds = easier)
        """
        if len(path) < 2:
            return self.profile.grade

        dists       = []
        difficulties= []

        for i in range(len(path) - 1):
            d = path[i].real_distance_cm(path[i + 1])
            dists.append(d)
            difficulties.append(HOLD_DIFFICULTY.get(path[i].type, 0.4))

        avg_dist  = sum(dists) / len(dists)
        avg_diff  = sum(difficulties) / len(difficulties)
        count_pen = max(0, (self.profile.hold_count_min - len(path)) * 0.05)

        # Composite score [0, 1]
        reach_score  = (avg_dist - 18) / (120 - 18)  # Normalise 18–120cm
        diff_score   = avg_diff + count_pen
        composite    = 0.5 * reach_score + 0.4 * diff_score + 0.1 * count_pen

        # Map composite → grade index
        grade_idx    = round(composite * (len(GRADES) - 1))
        grade_idx    = max(0, min(grade_idx, len(GRADES) - 1))
        return GRADES[grade_idx]


# ---------------------------------------------------------------------------
# Quality Scoring
# ---------------------------------------------------------------------------

class RouteScorer:
    """
    Multi-factor quality scoring for a generated route.

    Score components (each 0.0–1.0, weighted sum):
      1. Hold type variety      (0–1): Are multiple hold types used?
      2. Reach variance         (0–1): Are moves of varied distance?
      3. Direction variety      (0–1): Is the route not a straight line?
      4. Height progression     (0–1): Does the route consistently move up?
      5. Hold difficulty fit    (0–1): Do hold difficulties match the target grade?
      6. Route length fit       (0–1): Is hold count within ideal range?
    """

    WEIGHTS = {
        "type_variety":     0.20,
        "reach_variance":   0.20,
        "direction_variety":0.20,
        "height_progress":  0.15,
        "difficulty_fit":   0.15,
        "length_fit":       0.10,
    }

    def __init__(
        self,
        profile:        GradeProfile,
        wall_width_cm:  float = DEFAULT_WALL_WIDTH_CM,
        wall_height_cm: float = DEFAULT_WALL_HEIGHT_CM,
    ) -> None:
        self.profile        = profile
        self.wall_width_cm  = wall_width_cm
        self.wall_height_cm = wall_height_cm

    def score(self, route: GeneratedRoute) -> float:
        """Return a quality score in [0.0, 1.0]."""
        holds = [a.hold for a in route.holds]
        if len(holds) < 3:
            return 0.0

        scores = {
            "type_variety":      self._type_variety(holds),
            "reach_variance":    self._reach_variance(holds),
            "direction_variety": self._direction_variety(holds),
            "height_progress":   self._height_progression(holds),
            "difficulty_fit":    self._difficulty_fit(holds),
            "length_fit":        self._length_fit(len(holds)),
        }

        total = sum(scores[k] * self.WEIGHTS[k] for k in scores)
        route.metadata["score_breakdown"] = {k: round(v, 3) for k, v in scores.items()}
        return min(round(total, 4), 1.0)

    def _type_variety(self, holds: list[Hold]) -> float:
        """Fraction of distinct hold types used (more variety = better)."""
        unique_types = len({h.type for h in holds if h.type != "unknown"})
        max_types    = len(HOLD_DIFFICULTY)
        return unique_types / max_types

    def _reach_variance(self, holds: list[Hold]) -> float:
        """
        Normalised standard deviation of reach distances.
        High variance = rhythmically interesting moves.
        """
        if len(holds) < 3:
            return 0.5
        dists = [
            holds[i].real_distance_cm(holds[i + 1], self.wall_width_cm, self.wall_height_cm)
            for i in range(len(holds) - 1)
        ]
        mean    = sum(dists) / len(dists)
        std_dev = math.sqrt(sum((d - mean) ** 2 for d in dists) / len(dists))
        # Normalise: std_dev of 0 → 0, std_dev ≥ 20cm → 1
        return min(std_dev / 20.0, 1.0)

    def _direction_variety(self, holds: list[Hold]) -> float:
        """
        Measures how much the route changes direction.
        A perfectly straight route scores 0; high variety scores 1.
        """
        if len(holds) < 3:
            return 0.5

        angles = []
        for i in range(len(holds) - 1):
            dx = (holds[i + 1].center_x - holds[i].center_x) * self.wall_width_cm
            dy = (holds[i].center_y - holds[i + 1].center_y) * self.wall_height_cm  # positive = up
            angles.append(math.degrees(math.atan2(dy, dx)))

        # Compute angular changes between consecutive moves
        changes = [abs(angles[i + 1] - angles[i]) for i in range(len(angles) - 1)]
        if not changes:
            return 0.5

        avg_change = sum(changes) / len(changes)
        # Normalise: avg_change of 0 → 0, ≥60° → 1
        return min(avg_change / 60.0, 1.0)

    def _height_progression(self, holds: list[Hold]) -> float:
        """
        Fraction of consecutive pairs where the next hold is higher.
        Score of 1.0 = always moving up; 0.0 = always going down.
        """
        if len(holds) < 2:
            return 1.0
        upward = sum(1 for i in range(len(holds) - 1) if holds[i + 1].center_y < holds[i].center_y)
        return upward / (len(holds) - 1)

    def _difficulty_fit(self, holds: list[Hold]) -> float:
        """
        How well the average hold difficulty matches the grade's target.
        Perfect match → 1.0; large mismatch → 0.0.
        """
        avg_diff   = sum(HOLD_DIFFICULTY.get(h.type, 0.4) for h in holds) / len(holds)
        target     = self.profile.difficulty_target
        mismatch   = abs(avg_diff - target)
        return max(0.0, 1.0 - mismatch * 2.5)

    def _length_fit(self, n_holds: int) -> float:
        """
        Penalise routes outside the ideal hold count range.
        """
        if self.profile.hold_count_min <= n_holds <= self.profile.hold_count_max:
            return 1.0
        elif n_holds < self.profile.hold_count_min:
            shortage = self.profile.hold_count_min - n_holds
            return max(0.0, 1.0 - shortage * 0.2)
        else:
            excess = n_holds - self.profile.hold_count_max
            return max(0.0, 1.0 - excess * 0.15)


# ---------------------------------------------------------------------------
# ML Extension Hook
# ---------------------------------------------------------------------------

class RouteRanker(ABC):
    """
    Abstract base for ML-based route ranking.

    Swap the heuristic RouteScorer for a learned model by subclassing
    this and passing it to generate_routes().

    Extension path:
      1. Collect user ratings (1–5 stars) for generated routes.
      2. Feature-engineer routes (holds, distances, types, grade).
      3. Train a regression model (XGBoost, small NN) to predict rating.
      4. Implement predict() below.
    """

    @abstractmethod
    def predict(self, route: GeneratedRoute) -> float:
        """Return a predicted quality score in [0.0, 1.0]."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the model is loaded and ready."""
        ...


class HeuristicRanker(RouteRanker):
    """Default ranker using the RouteScorer heuristic (no ML required)."""

    def __init__(
        self,
        profile:        GradeProfile,
        wall_width_cm:  float = DEFAULT_WALL_WIDTH_CM,
        wall_height_cm: float = DEFAULT_WALL_HEIGHT_CM,
    ) -> None:
        self._scorer = RouteScorer(profile, wall_width_cm, wall_height_cm)

    def predict(self, route: GeneratedRoute) -> float:
        return self._scorer.score(route)

    def is_available(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def generate_routes(
    holds_data:      list[dict],
    grade:           str               = "V5",
    style:           str               = "dynamic",
    body_type:       str               = "default",
    hold_count:      int | str         = "auto",
    wall_width_cm:   float             = DEFAULT_WALL_WIDTH_CM,
    wall_height_cm:  float             = DEFAULT_WALL_HEIGHT_CM,
    n_candidates:    int               = 60,
    n_return:        int               = 1,
    ranker:          Optional[RouteRanker] = None,
    seed:            Optional[int]     = None,
) -> list[GeneratedRoute]:
    """
    Main entry point — builds the hold graph, runs the generator,
    scores routes, and returns ranked results.

    Args:
        holds_data:      List of hold dicts from Laravel
                         [{id, center_x, center_y, width, height, type, color}, ...]
        grade:           V-scale grade string ("V0"–"V16" or "auto")
        style:           Route style string
        body_type:       Climber body type ("default", "tall", "short")
        hold_count:      Target hold count or "auto"
        wall_width_cm:   Physical wall width in cm
        wall_height_cm:  Physical wall height in cm
        n_candidates:    DFS attempts per call
        n_return:        How many top routes to return
        ranker:          Optional ML ranker (defaults to HeuristicRanker)
        seed:            RNG seed for reproducibility

    Returns:
        List of GeneratedRoute sorted by quality_score, best first.

    Raises:
        ValueError: If grade is invalid or insufficient holds.
    """
    if len(holds_data) < 4:
        raise ValueError(f"Route generation requires ≥ 4 holds; got {len(holds_data)}.")

    # Resolve "auto" grade: pick median grade based on hold set
    if grade == "auto":
        grade = _auto_grade(holds_data)

    # Build hold objects
    holds = [
        Hold(
            id       = h["id"],
            center_x = float(h["center_x"]),
            center_y = float(h["center_y"]),
            width    = float(h.get("width",  0.04)),
            height   = float(h.get("height", 0.04)),
            type     = h.get("type",  "unknown"),
            color    = h.get("color", "unknown"),
        )
        for h in holds_data
    ]

    # Build grade profile with body type and style adjustments
    profile = get_grade_profile(grade)
    profile = apply_body_type_adjustment(profile, BodyType(body_type))
    profile = apply_style_adjustment(profile, RouteStyle(style), hold_count)

    # Override hold count if specified
    count_override = None
    if isinstance(hold_count, int) and 4 <= hold_count <= 20:
        count_override = hold_count

    # Build graph
    graph = HoldGraph(holds, profile, wall_width_cm, wall_height_cm)

    if graph.edge_count() == 0:
        raise ValueError(
            f"No reachable hold pairs found for grade={grade}. "
            "Consider using a lower grade or checking hold positions."
        )

    # Generate candidates
    generator = RouteGenerator(graph, profile, RouteStyle(style), seed=seed)
    candidates = generator.generate(
        n_attempts          = n_candidates,
        n_routes_to_return  = n_return * 3,  # Generate extra, then score and trim
        hold_count_override = count_override,
    )

    if not candidates:
        raise ValueError(
            "No valid routes could be generated. "
            "Try a different grade, style, or check that holds span the full wall height."
        )

    # Score with ranker
    active_ranker = ranker or HeuristicRanker(profile, wall_width_cm, wall_height_cm)
    for route in candidates:
        route.quality_score = active_ranker.predict(route)

    candidates.sort(key=lambda r: r.quality_score, reverse=True)

    logger.info(
        "generate_routes: grade=%s style=%s → %d candidates, returning %d",
        grade, style, len(candidates), min(n_return, len(candidates))
    )

    return candidates[:n_return]


def _auto_grade(holds_data: list[dict]) -> str:
    """
    Estimate an appropriate grade based on the hold set composition.
    More small holds → higher auto-grade.
    """
    hold_types  = [h.get("type", "unknown") for h in holds_data]
    avg_diff    = sum(HOLD_DIFFICULTY.get(t, 0.4) for t in hold_types) / max(len(hold_types), 1)
    grade_idx   = round(avg_diff * (len(GRADES) - 1))
    return GRADES[max(0, min(grade_idx, len(GRADES) - 1))]
