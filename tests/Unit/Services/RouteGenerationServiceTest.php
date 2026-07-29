<?php

declare(strict_types=1);

namespace Tests\Unit\Services;

use App\Exceptions\RouteGenerationException;
use App\Models\Hold;
use App\Models\Route;
use App\Models\User;
use App\Models\Wall;
use App\Services\RouteGenerationService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class RouteGenerationServiceTest extends TestCase
{
    use RefreshDatabase;

    private RouteGenerationService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new RouteGenerationService();
        config(['services.cv_service.url' => 'http://cv-service:8001']);
    }

    // ── generate() ───────────────────────────────────────────────────────────

    /** @test */
    public function it_creates_a_route_and_pivot_records_on_success(): void
    {
        $user  = User::factory()->create();
        $wall  = Wall::factory()->for($user)->create(['status' => 'scan_complete']);
        $holds = Hold::factory()->count(10)->for($wall)->create();

        Http::fake([
            'cv-service:8001/generate-route' => Http::response(
                $this->sampleRouteResponse($holds->pluck('id')->toArray()),
                200,
            ),
        ]);

        $route = $this->service->generate($wall, $user->id, 'V5', 'dynamic');

        $this->assertInstanceOf(Route::class, $route);
        $this->assertEquals('V5', $route->grade);
        $this->assertEquals('dynamic', $route->style);
        $this->assertFalse($route->is_published);
        $this->assertNull($route->name);
        $this->assertNotEmpty($route->holds);
        $this->assertDatabaseHas('route_holds', ['route_id' => $route->id]);
    }

    /** @test */
    public function it_throws_if_wall_has_fewer_than_4_active_holds(): void
    {
        $user = User::factory()->create();
        $wall = Wall::factory()->for($user)->create(['status' => 'scan_complete']);
        Hold::factory()->count(3)->for($wall)->create(); // Only 3 — below minimum

        $this->expectException(RouteGenerationException::class);
        $this->expectExceptionMessage('at least 4 active holds');

        $this->service->generate($wall, $user->id, 'V3', 'balance');
    }

    /** @test */
    public function it_excludes_excluded_holds_from_the_engine_payload(): void
    {
        $user     = User::factory()->create();
        $wall     = Wall::factory()->for($user)->create(['status' => 'scan_complete']);
        $active   = Hold::factory()->count(8)->for($wall)->create(['excluded' => false]);
        $excluded = Hold::factory()->count(4)->for($wall)->create(['excluded' => true]);

        Http::fake([
            'cv-service:8001/generate-route' => Http::response(
                $this->sampleRouteResponse($active->pluck('id')->toArray()),
                200,
            ),
        ]);

        $this->service->generate($wall, $user->id, 'V4', 'compression');

        Http::assertSent(function ($request) use ($excluded): bool {
            $holdIds = collect($request['holds'])->pluck('id');
            foreach ($excluded->pluck('id') as $excludedId) {
                if ($holdIds->contains($excludedId)) {
                    return false; // Excluded hold found in payload — FAIL
                }
            }
            return true;
        });
    }

    /** @test */
    public function it_throws_route_generation_exception_on_cv_service_error(): void
    {
        $user  = User::factory()->create();
        $wall  = Wall::factory()->for($user)->create(['status' => 'scan_complete']);
        Hold::factory()->count(10)->for($wall)->create();

        Http::fake([
            'cv-service:8001/generate-route' => Http::response([
                'error' => ['code' => 'NO_VALID_ROUTE', 'message' => 'No valid route for this grade.'],
            ], 422),
        ]);

        $this->expectException(RouteGenerationException::class);
        $this->service->generate($wall, $user->id, 'V16', 'dynamic');
    }

    /** @test */
    public function it_rolls_back_on_database_error(): void
    {
        $user  = User::factory()->create();
        $wall  = Wall::factory()->for($user)->create(['status' => 'scan_complete']);
        $holds = Hold::factory()->count(10)->for($wall)->create();

        // Return a hold_id that doesn't exist → DB FK violation → rollback
        Http::fake([
            'cv-service:8001/generate-route' => Http::response(
                $this->sampleRouteResponse(['non_existent_hold_id']),
                200,
            ),
        ]);

        $this->assertDatabaseCount('routes', 0);

        try {
            $this->service->generate($wall, $user->id, 'V5', 'dynamic');
        } catch (\Throwable) {
            // Expected
        }

        $this->assertDatabaseCount('routes', 0); // Rolled back
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    private function sampleRouteResponse(array $holdIds): array
    {
        $holds = array_map(fn(int $i, string $id): array => [
            'hold_id'        => $id,
            'role'           => match ($i) {
                0       => 'start',
                count($holdIds) - 1 => 'finish',
                default => 'hand',
            },
            'position_order' => $i + 1,
        ], array_keys($holdIds), $holdIds);

        return [
            'route' => [
                'holds'         => $holds,
                'quality_score' => 0.87,
                'grade_actual'  => 'V5',
            ],
        ];
    }
}
