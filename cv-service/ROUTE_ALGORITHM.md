# ROUTE_ALGORITHM.md — Route Generation Algorithm

> Module: `cv-service/app/route_generator.py`  
> Version: 1.0 | Grade Support: V0–V16 | Styles: 5

---

## Overview

The route generation system takes a set of detected holds (with normalised 2D positions, sizes, and types) and produces one or more **coherent, appropriately graded climbing routes**. The approach is a **graph-based Constraint Satisfaction Problem (CSP)** with a randomised DFS search, multi-factor quality scoring, and an ML extension hook.

```
Holds (positions + types)
        │
        ▼
┌─────────────────────────┐
│   1. Hold Graph Build   │  Directed weighted graph: nodes = holds, edges = reachable pairs
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│   2. Grade Profile      │  Per-grade parameters: reach range, hold count, difficulty target
│   + Body / Style Adj    │  Body type scaling + style-specific filtering
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│   3. Randomised DFS     │  N attempts from random start holds
│   with Constraint       │  Prune: reach, direction, hold type, visited
│   Pruning               │
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│   4. Role Assignment    │  start / hand / foot / finish
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│   5. Quality Scoring    │  6 components × weighted sum → [0, 1]
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│   6. Rank & Return      │  Top-N routes sorted by quality score
└─────────────────────────┘
```

---

## 1. Mathematical Model — The Hold Graph

### Coordinate System

All hold positions are **normalised** to the range `[0.0, 1.0]`:

- `x = 0.0` → left edge of wall
- `x = 1.0` → right edge of wall
- `y = 0.0` → **top** of wall (finish zone)
- `y = 1.0` → **bottom** of wall (start zone)

Real-world distances are computed using configurable wall dimensions (default 244 × 244 cm):

$$d_{real}(A, B) = \sqrt{((x_A - x_B) \cdot W)^2 + ((y_A - y_B) \cdot H)^2} \quad \text{(cm)}$$

### Graph Definition

**Nodes:** Every detected, non-excluded hold is a node $v_i \in V$.

**Edges:** A directed edge $e(A \to B)$ exists if and only if:

1. **Reach constraint:**
   $$r_{min} \leq d_{real}(A, B) \leq r_{max}$$

2. **Height constraint** (must be upward or lateral):
   $$(y_A - y_B) \cdot H > -\epsilon_{vertical}$$
   where $\epsilon_{vertical} = 0.08 \times H$ (8% of wall height tolerance for lateral traverses).

**Edge attributes:**
- `distance_cm` — Euclidean real-world distance
- `direction_deg` — Angle in degrees (0° = right, 90° = directly up)
- `is_upward` — Boolean

The graph is **directed** and **sparse** — in practice, each hold has 3–12 reachable neighbours depending on the grade and wall layout.

---

## 2. Grade Profiles

Each grade has a set of constraint parameters:

| Parameter | V0 | V5 | V10 | V16 |
|-----------|----|----|-----|-----|
| `reach_min_cm` | 18 | 28 | 38 | 50 |
| `reach_max_cm` | 42 | 68 | 93 | 118 |
| `hold_count_min` | 5 | 7 | 8 | 4 |
| `hold_count_max` | 9 | 13 | 18 | 12 |
| `small_hold_probability` | 0.05 | 0.44 | 0.80 | 0.99 |
| `foot_hold_ratio` | 0.30 | 0.24 | 0.15 | 0.04 |
| `difficulty_target` | 0.05 | 0.46 | 0.84 | 1.00 |

**Body type scaling** multiplies `reach_min` and `reach_max`:

| Body Type | Multiplier |
|-----------|-----------|
| Tall | 1.15× |
| Default | 1.00× |
| Short | 0.87× |

**Style adjustments** further modify the profile:

| Style | Effect |
|-------|--------|
| Dynamic | +20% max reach, fewer holds preferred |
| Balance | +40% foot holds, -15% max reach |
| Compression | -20% max reach, +15% small hold probability |
| Endurance | +30% hold count, -10% max reach |
| Coordination | +10% max reach, enforces direction changes |

---

## 3. Route Selection — Randomised DFS with Constraint Pruning

### Algorithm

```
ALGORITHM RouteGeneratorDFS(graph, profile, style, n_attempts):

  RESULT = []

  FOR attempt IN 1..n_attempts:
    start = WeightedRandomChoice(graph.start_candidates())   // Bottom 25%
    path  = [start]
    visited = {start.id}
    consecutive_vertical = 0

    WHILE |path| ≤ profile.hold_count_max + 1:
      current = path.last()

      IF current is finish candidate AND |path| ≥ profile.hold_count_min:
        BREAK  // Valid natural finish

      edges = graph.neighbours(current)
      edges = FILTER(edges, target not in visited)
      edges = ApplyStyleFilter(edges, consecutive_vertical, prev_direction)
      edges = ApplyDifficultyGate(edges, profile.small_hold_probability)

      IF edges is EMPTY: BREAK  // Dead end

      chosen = WeightedEdgeChoice(edges, profile)
      path.append(chosen.target)
      visited.add(chosen.target.id)
      UPDATE consecutive_vertical

    IF |path| ≥ max(4, profile.hold_count_min):
      route = AssignRoles(path)
      RESULT.append(route)

  RETURN TopN(Score(RESULT), n=n_routes_to_return)
```

### Weighted Edge Selection

At each step, each candidate edge is assigned a weight:

$$w(e) = (1 - \text{ease}(e.target)) \cdot p_{small} + \text{ease}(e.target) \cdot (1 - p_{small})$$

where:
- $\text{ease}(h)$ — hold type ease score (jug=0.9, crimp=0.2)
- $p_{small}$ — `small_hold_probability` from grade profile

This ensures that **hard grades strongly prefer small holds** while **easy grades prefer large holds**, without hard-coding exclusions.

### Direction Constraint

When `consecutive_vertical` exceeds `profile.max_consecutive_vertical`, the filter forces a lateral component:

$$|\theta_{direction} - 90°| > 25°$$

This prevents the degenerate case of routes that go straight up the wall.

---

## 4. Role Assignment

Roles are assigned deterministically after the DFS path is finalised:

```
path[0]            → "start"
path[-1]           → "finish"
foothold-typed holds (up to foot_hold_ratio × n) → "foot"
remaining interior holds                         → "hand"
```

---

## 5. Quality Scoring Function

The overall quality score is a weighted sum of six components, each in `[0, 1]`:

$$Q = 0.20 \cdot V_t + 0.20 \cdot V_r + 0.20 \cdot V_d + 0.15 \cdot P_h + 0.15 \cdot F_d + 0.10 \cdot F_l$$

| Component | Symbol | Measure |
|-----------|--------|---------|
| **Type Variety** | $V_t$ | Fraction of distinct hold types used |
| **Reach Variance** | $V_r$ | Normalised std-dev of move distances (÷ 20cm) |
| **Direction Variety** | $V_d$ | Avg angular change between consecutive moves (÷ 60°) |
| **Height Progression** | $P_h$ | Fraction of upward moves |
| **Difficulty Fit** | $F_d$ | `1 - 2.5 × |avg_difficulty - grade_target|` |
| **Length Fit** | $F_l$ | 1.0 if in `[hold_count_min, hold_count_max]`, penalised otherwise |

The metadata in each route response includes a `score_breakdown` dict for transparency.

---

## 6. Worked Example — V5 Dynamic Route

### Input

Wall: 244 × 244 cm  
Grade: V5 | Style: Dynamic | Body type: Default

**25 holds detected** (positions normalised, mixed types):

| # | ID | x | y | Type |
|---|-----|----|----|------|
| 1 | h_0 | 0.21 | 0.91 | jug |
| 2 | h_7 | 0.55 | 0.82 | jug |
| 3 | h_3 | 0.78 | 0.71 | sloper |
| 4 | h_12 | 0.42 | 0.59 | pinch |
| 5 | h_19 | 0.25 | 0.44 | crimp |
| 6 | h_14 | 0.60 | 0.31 | pocket |
| 7 | h_9 | 0.38 | 0.18 | crimp |
| 8 | h_22 | 0.52 | 0.08 | sloper |

### Grade Profile (V5 Dynamic)

- `reach_min_cm` = 28
- `reach_max_cm` = 82 (68 × 1.20 dynamic boost)
- `hold_count` target = 7–13

### Graph Construction

Edges computed for the 8-hold subset:

```
h_0(y=0.91) → h_7(y=0.82)   dist=50.2cm  ✓ (28 ≤ 50 ≤ 82)
h_7(y=0.82) → h_3(y=0.71)   dist=61.5cm  ✓
h_7(y=0.82) → h_12(y=0.59)  dist=73.3cm  ✓
h_3(y=0.71) → h_12(y=0.59)  dist=44.9cm  ✓
h_12(y=0.59)→ h_19(y=0.44)  dist=55.2cm  ✓
h_19(y=0.44)→ h_14(y=0.31)  dist=63.8cm  ✓
h_14(y=0.31)→ h_9(y=0.18)   dist=54.9cm  ✓
h_14(y=0.31)→ h_22(y=0.08)  dist=73.1cm  ✓
h_9(y=0.18) → h_22(y=0.08)  dist=38.2cm  ✓
```

### DFS Trace (Attempt #1, seed=42)

```
Start candidates (y ≥ 0.75): [h_0(jug), h_7(jug)]
WeightedChoice → h_0 (more bottom weight)

Step 1: current=h_0  → candidates=[h_7]  → choose h_7
Step 2: current=h_7  → candidates=[h_3, h_12]
        style=dynamic: prefer dist≥28×1.4=39cm → both qualify
        difficulty gate: p_small=0.44
          h_3(sloper, ease=0.55): w = 0.45×0.44 + 0.55×0.56 = 0.51
          h_12(pinch, ease=0.50): w = 0.50×0.44 + 0.50×0.56 = 0.50
        WeightedChoice → h_3

Step 3: current=h_3  → candidates=[h_12]  → choose h_12
Step 4: current=h_12 → candidates=[h_19]  → choose h_19
Step 5: current=h_19 → candidates=[h_14]  → choose h_14
Step 6: current=h_14 → candidates=[h_9, h_22]
        both valid; h_22 is finish candidate (y≤0.20)
        WeightedChoice → h_22 ✓ finish candidate, |path|=7 ≥ min=7 → BREAK
```

### Route Output

| Order | Hold | Type | Role |
|-------|------|------|------|
| 1 | h_0 | jug | **start** |
| 2 | h_7 | jug | hand |
| 3 | h_3 | sloper | hand |
| 4 | h_12 | pinch | hand |
| 5 | h_19 | crimp | hand |
| 6 | h_14 | pocket | hand |
| 7 | h_22 | sloper | **finish** |

### Quality Scoring

| Component | Value | Explanation |
|-----------|-------|-------------|
| Type Variety | 0.71 | 5/7 distinct types used |
| Reach Variance | 0.62 | Std-dev 12.4cm → 12.4/20 = 0.62 |
| Direction Variety | 0.58 | Average 35° angular change → 35/60 ≈ 0.58 |
| Height Progression | 1.00 | All moves upward |
| Difficulty Fit | 0.68 | avg_diff=0.46, target=0.46 → near-perfect |
| Length Fit | 1.00 | 7 holds ∈ [7, 13] |

$$Q = 0.20(0.71) + 0.20(0.62) + 0.20(0.58) + 0.15(1.00) + 0.15(0.68) + 0.10(1.00)$$
$$Q = 0.142 + 0.124 + 0.116 + 0.150 + 0.102 + 0.100 = \mathbf{0.734}$$

---

## 7. API Reference

### `POST /generate-route`

**Request body:**
```json
{
  "wall_id":       "wall_abc123",
  "holds": [
    { "id": "h_0",  "center_x": 0.21, "center_y": 0.91, "type": "jug",    "color": "red"  },
    { "id": "h_7",  "center_x": 0.55, "center_y": 0.82, "type": "jug",    "color": "blue" },
    { "id": "h_22", "center_x": 0.52, "center_y": 0.08, "type": "sloper", "color": "green"}
  ],
  "grade":          "V5",
  "style":          "dynamic",
  "body_type":      "default",
  "hold_count":     "auto",
  "wall_width_cm":  244,
  "wall_height_cm": 244,
  "n_candidates":   60,
  "seed":           null
}
```

**Success response `200`:**
```json
{
  "wall_id": "wall_abc123",
  "route": {
    "holds": [
      { "hold_id": "h_0",  "role": "start",  "position_order": 1 },
      { "hold_id": "h_7",  "role": "hand",   "position_order": 2 },
      { "hold_id": "h_22", "role": "finish", "position_order": 7 }
    ],
    "quality_score": 0.7340,
    "grade_actual":  "V5",
    "style":         "dynamic",
    "metadata": {
      "total_holds": 7,
      "foot_holds":  0,
      "hand_holds":  5,
      "score_breakdown": {
        "type_variety": 0.714,
        "reach_variance": 0.620,
        "direction_variety": 0.580,
        "height_progress": 1.000,
        "difficulty_fit": 0.680,
        "length_fit": 1.000
      }
    }
  }
}
```

**Error response `422`:**
```json
{
  "detail": {
    "error": {
      "code":    "NO_VALID_ROUTE",
      "message": "No valid routes could be generated. Try a different grade or style."
    }
  }
}
```

**Error codes:**

| Code | Cause |
|------|-------|
| `INSUFFICIENT_HOLDS` | Fewer than 4 holds provided |
| `NO_REACHABLE_PAIRS` | No hold pairs within reach range for this grade |
| `NO_VALID_ROUTE` | DFS couldn't find a valid path (wall layout or grade mismatch) |
| `INVALID_GRADE` | Grade string not in V0–V16 |

---

## 8. ML Extension Hook

The `RouteRanker` abstract base class allows swapping the heuristic scorer for a trained model:

```python
class MLRouteRanker(RouteRanker):
    """Example: XGBoost trained on user ratings."""

    def __init__(self, model_path: str):
        import joblib
        self._model = joblib.load(model_path)

    def is_available(self) -> bool:
        return self._model is not None

    def predict(self, route: GeneratedRoute) -> float:
        features = self._extract_features(route)
        return float(self._model.predict([features])[0])

    def _extract_features(self, route: GeneratedRoute) -> list[float]:
        holds = [a.hold for a in route.holds]
        return [
            len(holds),
            sum(HOLD_DIFFICULTY.get(h.type, 0.4) for h in holds) / len(holds),
            route.quality_score,                          # Heuristic as feature
            route.metadata.get("score_breakdown", {}).get("reach_variance", 0),
            route.metadata.get("score_breakdown", {}).get("direction_variety", 0),
            # ... add user-level features (rating history, preferred style)
        ]
```

**Training data collection path:**
1. Users rate generated routes (1–5 ★ via `POST /routes/{id}/ratings`)
2. Feature-engineer each rated route (hold types, distances, grade, style)
3. Train regression model: `features → predicted_rating`
4. Deploy `MLRouteRanker` in production; keep `HeuristicRanker` as fallback

---

## 9. Running the Tests

```bash
cd cv-service
pip install pytest

# Run all route generator tests
pytest tests/test_route_generator.py -v

# Run only a specific grade
pytest tests/test_route_generator.py::TestV5RouteGeneration -v

# Run with coverage
pip install pytest-cov
pytest tests/test_route_generator.py --cov=app.route_generator --cov-report=term-missing
```
