<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Exceptions\RouteGenerationException;
use App\Http\Controllers\Controller;
use App\Http\Requests\Route\GenerateRouteRequest;
use App\Http\Requests\Route\SaveRouteRequest;
use App\Http\Resources\RouteResource;
use App\Models\Comment;
use App\Models\Rating;
use App\Models\Route;
use App\Models\Wall;
use App\Services\RouteGenerationService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\AnonymousResourceCollection;
use Illuminate\Support\Facades\Gate;

class RouteController extends Controller
{
    public function __construct(
        private readonly RouteGenerationService $routeGenerationService,
    ) {}

    /**
     * POST /api/v1/walls/{wall}/routes/generate
     *
     * Generate a new AI route for the given wall. Returns a draft route.
     */
    public function generate(GenerateRouteRequest $request, Wall $wall): RouteResource|JsonResponse
    {
        Gate::authorize('view', $wall);

        if ($wall->status !== 'scan_complete') {
            return response()->json([
                'error' => [
                    'code'    => 'WALL_NOT_READY',
                    'message' => 'Wall must have a completed scan before generating routes.',
                ],
            ], 422);
        }

        try {
            $route = $this->routeGenerationService->generate(
                wall:       $wall,
                setterId:   $request->user()->id,
                grade:      $request->grade,
                style:      $request->style,
                bodyType:   $request->input('body_type', 'default'),
                holdCount:  $request->input('hold_count', 'auto'),
            );
        } catch (RouteGenerationException $e) {
            return response()->json([
                'error' => [
                    'code'    => $e->errorCode,
                    'message' => $e->getMessage(),
                ],
            ], 422);
        }

        return new RouteResource($route);
    }

    /**
     * GET /api/v1/walls/{wall}/routes
     *
     * List published routes for a wall.
     */
    public function index(Wall $wall): AnonymousResourceCollection
    {
        Gate::authorize('view', $wall);

        $routes = $wall->routes()
            ->published()
            ->with('setter')
            ->latest()
            ->paginate(20);

        return RouteResource::collection($routes);
    }

    /**
     * GET /api/v1/routes/{route}
     */
    public function show(Route $route): RouteResource
    {
        Gate::authorize('view', $route);
        $route->load(['holds', 'setter']);

        return new RouteResource($route);
    }

    /**
     * GET /routes/{token}  (public, no auth)
     *
     * View a route via its share token.
     */
    public function showByToken(string $token): RouteResource|JsonResponse
    {
        $route = Route::where('share_token', $token)->where('is_published', true)->first();

        if (! $route) {
            return response()->json(['error' => ['code' => 'ROUTE_NOT_FOUND', 'message' => 'Route not found.']], 404);
        }

        $route->load(['holds', 'setter']);

        return new RouteResource($route);
    }

    /**
     * PATCH /api/v1/routes/{route}
     *
     * Save (name) a draft route and optionally publish it.
     */
    public function save(SaveRouteRequest $request, Route $route): RouteResource
    {
        Gate::authorize('update', $route);

        $route->update($request->only(['name', 'description']));

        if ($request->boolean('is_published') && ! $route->share_token) {
            $route->generateShareToken();
        }

        $route->load(['holds', 'setter']);

        return new RouteResource($route);
    }

    /**
     * DELETE /api/v1/routes/{route}
     */
    public function destroy(Route $route): JsonResponse
    {
        Gate::authorize('delete', $route);
        $route->delete();

        return response()->json(null, 204);
    }

    /**
     * POST /api/v1/routes/{route}/ratings
     */
    public function rate(Request $request, Route $route): JsonResponse
    {
        $request->validate(['stars' => ['required', 'integer', 'min:1', 'max:5']]);

        Rating::updateOrCreate(
            ['route_id' => $route->id, 'user_id' => $request->user()->id],
            ['stars'    => $request->stars],
        );

        $route->recalculateRating();

        return response()->json([
            'average_rating' => $route->fresh()->average_rating,
            'total_ratings'  => $route->fresh()->total_ratings,
        ]);
    }

    /**
     * POST /api/v1/routes/{route}/comments
     */
    public function comment(Request $request, Route $route): JsonResponse
    {
        $request->validate(['body' => ['required', 'string', 'max:2000']]);

        $comment = Comment::create([
            'route_id' => $route->id,
            'user_id'  => $request->user()->id,
            'body'     => $request->body,
        ]);

        return response()->json(['data' => $comment], 201);
    }
}
