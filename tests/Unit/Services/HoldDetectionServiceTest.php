<?php

declare(strict_types=1);

namespace Tests\Unit\Services;

use App\Exceptions\HoldDetectionException;
use App\Models\Hold;
use App\Models\Wall;
use App\Services\HoldDetectionService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Client\Request as ClientRequest;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class HoldDetectionServiceTest extends TestCase
{
    use RefreshDatabase;

    private HoldDetectionService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new HoldDetectionService();
        config(['services.cv_service.url' => 'http://cv-service:8001']);
    }

    // ── detectHolds() ────────────────────────────────────────────────────────

    /** @test */
    public function it_returns_holds_array_on_successful_cv_response(): void
    {
        Http::fake([
            'cv-service:8001/detect-holds' => Http::response([
                'wall_id' => 'wall_001',
                'status'  => 'success',
                'holds'   => $this->sampleHoldsPayload(5),
            ], 200),
        ]);

        $wall  = Wall::factory()->create(['image_url' => 'https://s3.example.com/wall.jpg']);
        $holds = $this->service->detectHolds($wall);

        $this->assertCount(5, $holds);
        Http::assertSent(fn(ClientRequest $r) => str_contains($r->url(), '/detect-holds'));
    }

    /** @test */
    public function it_throws_hold_detection_exception_on_no_holds_error(): void
    {
        Http::fake([
            'cv-service:8001/detect-holds' => Http::response([
                'status' => 'error',
                'error'  => ['code' => 'NO_HOLDS_DETECTED', 'message' => 'No holds found.'],
            ], 400),
        ]);

        $this->expectException(HoldDetectionException::class);
        $this->expectExceptionMessage('No holds found.');

        $wall = Wall::factory()->create();
        $this->service->detectHolds($wall);
    }

    /** @test */
    public function it_throws_exception_when_cv_service_is_unreachable(): void
    {
        Http::fake([
            'cv-service:8001/*' => Http::response(null, 503),
        ]);

        $this->expectException(HoldDetectionException::class);

        $wall = Wall::factory()->create();
        $this->service->detectHolds($wall);
    }

    /** @test */
    public function it_sends_correct_payload_to_cv_service(): void
    {
        Http::fake([
            'cv-service:8001/detect-holds' => Http::response(['wall_id' => 'x', 'holds' => []], 200),
        ]);

        $wall = Wall::factory()->create([
            'id'        => 'test-wall-id',
            'image_url' => 'https://s3.test/wall.jpg',
        ]);

        try {
            $this->service->detectHolds($wall, 'accurate');
        } catch (HoldDetectionException) {
            // No holds is ok for this test — we just care about the request
        }

        Http::assertSent(function (ClientRequest $request): bool {
            return $request['wall_id'] === 'test-wall-id'
                && $request['image_url'] === 'https://s3.test/wall.jpg'
                && $request['mode'] === 'accurate';
        });
    }

    // ── persistHolds() ───────────────────────────────────────────────────────

    /** @test */
    public function it_bulk_inserts_holds_into_database(): void
    {
        $wall      = Wall::factory()->create();
        $holdsData = $this->sampleHoldsPayload(7);

        $count = $this->service->persistHolds($wall, $holdsData);

        $this->assertEquals(7, $count);
        $this->assertDatabaseCount('holds', 7);
        $this->assertDatabaseHas('holds', ['wall_id' => $wall->id]);
    }

    /** @test */
    public function it_deletes_stale_holds_before_persisting_new_ones(): void
    {
        $wall = Wall::factory()->create();
        Hold::factory()->count(3)->for($wall)->create(); // Stale holds

        $this->service->persistHolds($wall, $this->sampleHoldsPayload(2));

        $this->assertDatabaseCount('holds', 2); // Old 3 deleted, new 2 inserted
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    private function sampleHoldsPayload(int $count): array
    {
        return array_map(fn(int $i): array => [
            'id'              => "hold_{$i:04d}",
            'x'               => 0.1 * $i,
            'y'               => 0.1 * $i,
            'width'           => 0.05,
            'height'          => 0.05,
            'center_x'        => 0.1 * $i + 0.025,
            'center_y'        => 0.1 * $i + 0.025,
            'area'            => 0.0025,
            'color'           => 'blue',
            'color_hex'       => '#3B82F6',
            'type'            => 'jug',
            'confidence'      => 0.92,
            'type_confidence' => 0.88,
            'is_verified'     => true,
        ], range(1, $count));
    }
}
