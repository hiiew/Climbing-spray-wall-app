# TESTING_STRATEGY.md — QA Strategy: Climbing Spray Wall App

> Version: 1.0 | Framework: Laravel PHPUnit/Pest + pytest + React Testing Library + Playwright

---

## Testing Pyramid

```
                        ┌─────────────────────┐
                        │    E2E (Playwright)   │  ← 8 scenarios
                        │  Slow · High value    │
                      ┌─┴─────────────────────┴─┐
                      │    Integration Tests      │  ← 24 tests
                      │  Service boundaries       │
                    ┌─┴──────────────────────────┴─┐
                    │          Unit Tests            │  ← 90+ tests
                    │  Fast · Isolated · Many        │
                    └────────────────────────────────┘
```

---

## Testing Matrix

| Feature | Unit | Integration | E2E | Risk |
|---------|------|-------------|-----|------|
| Wall image upload (happy path) | ✅ StoreWallRequest validation | ✅ WallUploadTest | ✅ Playwright | 🔴 High |
| Wall upload — corrupt image | ✅ Request validation | ✅ WallUploadTest | — | 🔴 High |
| Wall upload — oversized image | ✅ Request validation | ✅ WallUploadTest | — | 🟡 Med |
| Wall upload — no holds detected | ✅ HoldDetectionService | ✅ job failed() | — | 🔴 High |
| CV service timeout | ✅ HoldDetectionService retry | ✅ mock HTTP | — | 🔴 High |
| Hold persistence (bulk insert) | ✅ HoldDetectionService | ✅ DB assertions | — | 🔴 High |
| Hold exclusion (user toggle) | ✅ Hold model scope | ✅ HoldController | ✅ Playwright | 🟡 Med |
| Route generation — V0/V5/V10 | ✅ RouteGenerationService | ✅ API endpoint | ✅ Playwright | 🔴 High |
| Route generation — insufficient holds | ✅ RouteGenerationService | ✅ 422 response | — | 🔴 High |
| Route generation — CV timeout | ✅ Service exception | ✅ 422 response | — | 🔴 High |
| Save route (name + publish) | ✅ SaveRouteRequest | ✅ RouteController | ✅ Playwright | 🟡 Med |
| Share route via public URL | — | ✅ RouteShareTest | ✅ Playwright | 🔴 High |
| Auth: register | ✅ AuthController | ✅ AuthTest | — | 🟡 Med |
| Auth: login + token | ✅ AuthController | ✅ AuthTest | — | 🟡 Med |
| Auth: unauthenticated access | — | ✅ AuthTest | — | 🔴 High |
| WebSocket scan notification | — | ✅ Event broadcast | — | 🟡 Med |
| Hold detector: image validation | ✅ preprocessor | ✅ API endpoint | — | 🔴 High |
| Hold detector: YOLO pipeline | ✅ hold_detector | ✅ mock model | — | 🔴 High |
| Hold detector: color classifier | ✅ color_classifier | ✅ HSV boundaries | — | 🟢 Low |
| Route algo: graph construction | ✅ HoldGraph | ✅ edge assertions | — | 🔴 High |
| Route algo: grade constraints | ✅ GradeProfile | ✅ reach bounds | — | 🔴 High |
| Route algo: quality scoring | ✅ RouteScorer | — | — | 🟡 Med |
| Hold map SVG rendering | ✅ RTL HoldMapOverlay | — | ✅ Playwright | 🔴 High |
| Upload progress UI | ✅ RTL WallUploader | — | — | 🟢 Low |
| Route panel grade slider | ✅ RTL RouteGeneratorPanel | — | — | 🟢 Low |
| Save route modal + copy URL | ✅ RTL SaveRouteModal | — | ✅ Playwright | 🟡 Med |

---

## Test File Inventory

```
tests/
├── Feature/
│   ├── WallUploadTest.php          ← Upload happy path + all error paths
│   ├── AuthTest.php                ← Register, login, logout, unauthorized
│   └── RouteShareTest.php          ← Public share URL + auth-gated routes
├── Unit/
│   └── Services/
│       ├── HoldDetectionServiceTest.php
│       └── RouteGenerationServiceTest.php

cv-service/tests/
├── test_hold_detector.py           ← CV pipeline with mocked inputs
├── test_route_generator.py         ← Algorithm constraint validation (Skill 5)
├── test_color_classifier.py        ← HSV colour logic
└── conftest.py                     ← Shared fixtures

e2e/
├── upload_and_generate_route.spec.ts   ← Full user journey
├── auth.spec.ts                        ← Login/register flows
└── share_route.spec.ts                 ← Public share URL

.github/workflows/
└── test.yml                        ← CI pipeline (all suites)
```

---

## Risk-Based Priority

### P0 — Block release if failing
- Wall upload + CV dispatch (data entry point)
- Hold persistence (corrupt data = unusable routes)
- Route generation API contract
- Public share URL (security: must not require auth)

### P1 — Fix before next sprint
- Auth token flows
- CV timeout/retry behaviour
- Grade constraint enforcement

### P2 — Fix when possible
- Quality score accuracy
- Frontend micro-interactions
- Color classifier edge cases
