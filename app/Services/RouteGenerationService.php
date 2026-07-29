<?php

declare(strict_types=1);

namespace App\Services;

use App\Exceptions\RouteGenerationException;
use App\Models\Hold;
use App\Models\Route;
use App\Models\Wall;
use Illuminate\Database\Eloquent\Collection;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * RouteGenerationService
 *
 * Orchestrates route generation:
 *   1. Load active (non-excluded) holds for the wall
 *   2. Call POST /generate-route on the Python CV service
 *   3. Persist the generated route and its hold assignments in a transaction
 *
 * The generated route starts as a draft (name=null, is_published=false).
 * The user names/publishes it via PATCH /routes/{id}.
 */
class RouteGenerationService
{
    private string $cvServiceUrl;
    private int    $timeoutSeconds;

    public function __construct()
    {
        $this->cvServiceUrl   = rtrim((string) config('services.cv_service.url'), '/');
        $this->timeoutSeconds = (int) config('services.cv_service.timeout', 60);
    }

    /**
     * Generate a route for a wall and persist it.
     *
     * @param  Wall   $wall
     * @param  int    $setterId   The user ID of the route setter
     * @param  string $grade      e.g. 'V5'
     * @param  string $style      dynamic|balance|compression|endurance|coordination
     * @param  string $bodyType   default|tall|short
     * @param  int|string $holdCount  Integer or 'auto'
     * @return Route  The newly created Route model (with holds loaded)
     *
     * @throws RouteGenerationException
     */
    public function generate(
        Wall $wall,
        int $setterId,
        string $grade,
        string $style,
        string $bodyType = 'default',
        int|string $holdCount = 'auto',
    ): Route {
        // ── Step 1: Load active holds ────────────────────────────────────────
        $holds = $wall->holds()->active()->get();

        if ($holds->count() < 4) {
            throw new RouteGenerationException(
                "Route generation requires at least 4 active holds. This wall has {$holds->count()}.",
                'INSUFFICIENT_HOLDS',
            );
        }

        // ── Step 2: Call CV route engine ─────────────────────────────────────
        $cvResponse = $this->callRouteEngine($wall, $holds, $grade, $style, $bodyType, $holdCount);

        // ── Step 3: Persist in a transaction ─────────────────────────────────
        $route = DB::transaction(function () use ($wall, $setterId, $grade, $style, $cvResponse): Route {
            $routeData = $cvResponse['route'];

            $route = Route::create([
                'wall_id'       => $wall->id,
                'setter_id'     => $setterId,
                'grade'         => $routeData['grade_actual'] ?? $grade,
                'style'         => $style,
                'quality_score' => $routeData['quality_score'] ?? 0.0,
                'hold_count'    => count($routeData['holds']),
                'is_published'  => false,
            ]);

            $pivotRecords = array_map(
                fn(array $h): array => [
                    'route_id'       => $route->id,
                    'hold_id'        => $h['hold_id'],
                    'position_order' => $h['position_order'],
                    'role'           => $h['role'],
                ],
                $routeData['holds'],
            );

            DB::table('route_holds')->insert($pivotRecords);

            return $route;
        });

        // Eager-load holds for the response
        $route->load(['holds' => fn($q) => $q->orderByPivot('position_order')]);

        Log::info("[RouteGenerationService] Route {$route->id} created for wall={$wall->id}");

        return $route;
    }

    /**
     * Call the Python route generation engine.
     *
     * @param  Wall       $wall
     * @param  Collection $holds
     * @param  string     $grade
     * @param  string     $style
     * @param  string     $bodyType
     * @param  int|string $holdCount
     * @return array  Decoded JSON response body
     *
     * @throws RouteGenerationException
     */
    private function callRouteEngine(
        Wall $wall,
        Collection $holds,
        string $grade,
        string $style,
        string $bodyType,
        int|string $holdCount,
    ): array {
        Log::info("[RouteGenerationService] Calling route engine for wall={$wall->id}, grade={$grade}");

        // Prepare minimal hold payload (positions + type — the engine needs these)
        $holdsPayload = $holds->map(fn(Hold $h): array => [
            'id'       => $h->id,
            'center_x' => $h->center_x,
            'center_y' => $h->center_y,
            'width'    => $h->width,
            'height'   => $h->height,
            'type'     => $h->type,
            'color'    => $h->color,
        ])->values()->toArray();

        try {
            $response = Http::timeout($this->timeoutSeconds)
                ->post("{$this->cvServiceUrl}/generate-route", [
                    'wall_id'    => $wall->id,
                    'holds'      => $holdsPayload,
                    'grade'      => $grade,
                    'style'      => $style,
                    'body_type'  => $bodyType,
                    'hold_count' => $holdCount,
                ]);

            if ($response->failed()) {
                $errorCode = $response->json('error.code', 'GENERATION_FAILED');
                $message   = $response->json('error.message', "Route engine returned HTTP {$response->status()}");

                throw new RouteGenerationException($message, $errorCode);
            }

            return $response->json();

        } catch (ConnectionException $e) {
            throw new RouteGenerationException(
                'Route generation service is currently unavailable.',
                'ROUTE_ENGINE_UNREACHABLE',
                $e,
            );
        }
    }
}
