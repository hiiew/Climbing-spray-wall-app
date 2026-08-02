<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\Hold;
use App\Models\Route;
use App\Models\User;
use App\Models\Wall;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * RouteShareTest — Feature tests for the public route sharing system.
 *
 * Critical security invariants:
 * - The /share/{token} endpoint must NOT require authentication
 * - Unpublished routes must NOT be accessible via share token
 * - Routes belonging to other users must NOT be visible to unauthorised viewers
 * - The share token must be cryptographically random and unpredictable
 */
class RouteShareTest extends TestCase
{
    use RefreshDatabase;

    private User  $owner;
    private Wall  $wall;
    private Route $route;

    protected function setUp(): void
    {
        parent::setUp();

        $this->owner = User::factory()->create();
        $this->wall  = Wall::factory()->for($this->owner)->create(['status' => 'scan_complete']);
        $this->route = Route::factory()->for($this->wall)->create([
            'setter_id'    => $this->owner->id,
            'name'         => 'The Crimson Slab',
            'is_published' => true,
            'share_token'  => 'abc123XYZ789secure',
        ]);
    }

    // ── Public Share Endpoint ─────────────────────────────────────────────────

    /** @test */
    public function public_share_url_returns_route_without_authentication(): void
    {
        // No actingAs() — deliberately unauthenticated
        $this->getJson('/api/v1/share/abc123XYZ789secure')
            ->assertOk()
            ->assertJsonPath('data.name', 'The Crimson Slab');
    }

    /** @test */
    public function share_url_returns_grade_and_style(): void
    {
        $this->getJson('/api/v1/share/abc123XYZ789secure')
            ->assertOk()
            ->assertJsonStructure([
                'data' => ['id', 'name', 'grade', 'style', 'hold_count', 'quality_score'],
            ]);
    }

    /** @test */
    public function share_url_returns_404_for_nonexistent_token(): void
    {
        $this->getJson('/api/v1/share/INVALID_TOKEN_XXXXXX')
            ->assertStatus(404)
            ->assertJsonPath('error.code', 'ROUTE_NOT_FOUND');
    }

    /** @test */
    public function share_url_returns_404_for_unpublished_route(): void
    {
        $unpublished = Route::factory()->for($this->wall)->create([
            'setter_id'    => $this->owner->id,
            'is_published' => false,
            'share_token'  => 'unpublished-token-999',
        ]);

        $this->getJson('/api/v1/share/unpublished-token-999')
            ->assertStatus(404);
    }

    /** @test */
    public function share_url_response_includes_holds_data(): void
    {
        Hold::factory()->count(6)->for($this->wall)->create();

        $this->route->holds()->attach(
            Hold::where('wall_id', $this->wall->id)->pluck('id')->mapWithKeys(
                fn($id, $i) => [$id => ['position_order' => $i + 1, 'role' => 'hand']]
            )->toArray()
        );

        $this->getJson('/api/v1/share/abc123XYZ789secure')
            ->assertOk()
            ->assertJsonStructure(['data' => ['holds']]);
    }

    // ── Share Token Generation ────────────────────────────────────────────────

    /** @test */
    public function saving_route_as_published_generates_share_token(): void
    {
        $draft = Route::factory()->for($this->wall)->create([
            'setter_id'    => $this->owner->id,
            'name'         => null,
            'is_published' => false,
            'share_token'  => null,
        ]);

        $this->actingAs($this->owner)
            ->patchJson("/api/v1/routes/{$draft->id}", [
                'name'         => 'New Route',
                'is_published' => true,
            ])->assertOk();

        $this->assertDatabaseMissing('routes', [
            'id'          => $draft->id,
            'share_token' => null,
        ]);
    }

    /** @test */
    public function share_tokens_are_unique(): void
    {
        $tokens = [];
        for ($i = 0; $i < 10; $i++) {
            $route = Route::factory()->for($this->wall)->create([
                'setter_id'    => $this->owner->id,
                'name'         => null,
                'is_published' => false,
            ]);
            $token = $route->generateShareToken();
            $tokens[] = $token;
        }

        $this->assertCount(10, array_unique($tokens), 'Share tokens must all be unique');
    }

    /** @test */
    public function share_tokens_are_at_least_20_characters(): void
    {
        $token = $this->route->generateShareToken();
        $this->assertGreaterThanOrEqual(20, strlen($token));
    }

    // ── Authorisation: Private Endpoints ────────────────────────────────────

    /** @test */
    public function unauthenticated_user_cannot_save_a_route(): void
    {
        $this->patchJson("/api/v1/routes/{$this->route->id}", [
            'name' => 'Hijacked Route',
        ])->assertStatus(401);
    }

    /** @test */
    public function user_cannot_save_another_users_route(): void
    {
        $attacker = User::factory()->create();

        $this->actingAs($attacker)
            ->patchJson("/api/v1/routes/{$this->route->id}", [
                'name' => 'Stolen Name',
            ])->assertForbidden();
    }

    /** @test */
    public function user_cannot_delete_another_users_route(): void
    {
        $attacker = User::factory()->create();

        $this->actingAs($attacker)
            ->deleteJson("/api/v1/routes/{$this->route->id}")
            ->assertForbidden();
    }

    /** @test */
    public function owner_can_delete_their_own_route(): void
    {
        $this->actingAs($this->owner)
            ->deleteJson("/api/v1/routes/{$this->route->id}")
            ->assertStatus(204);

        $this->assertSoftDeleted('routes', ['id' => $this->route->id]);
    }

    // ── Rating & Comments (social features) ──────────────────────────────────

    /** @test */
    public function authenticated_user_can_rate_a_published_route(): void
    {
        $rater = User::factory()->create();

        $this->actingAs($rater)
            ->postJson("/api/v1/routes/{$this->route->id}/ratings", ['stars' => 4])
            ->assertOk()
            ->assertJsonStructure(['average_rating', 'total_ratings']);
    }

    /** @test */
    public function rating_must_be_between_1_and_5(): void
    {
        $rater = User::factory()->create();

        $this->actingAs($rater)
            ->postJson("/api/v1/routes/{$this->route->id}/ratings", ['stars' => 6])
            ->assertStatus(422)
            ->assertJsonValidationErrors(['stars']);

        $this->actingAs($rater)
            ->postJson("/api/v1/routes/{$this->route->id}/ratings", ['stars' => 0])
            ->assertStatus(422);
    }

    /** @test */
    public function rating_is_idempotent_per_user(): void
    {
        $rater = User::factory()->create();

        $this->actingAs($rater)
            ->postJson("/api/v1/routes/{$this->route->id}/ratings", ['stars' => 3]);

        $this->actingAs($rater)
            ->postJson("/api/v1/routes/{$this->route->id}/ratings", ['stars' => 5]);

        // Should have only 1 rating row (updateOrCreate)
        $this->assertDatabaseCount('ratings', 1);

        $this->route->refresh();
        $this->assertEquals(5.0, $this->route->average_rating);
    }

    /** @test */
    public function unauthenticated_user_cannot_rate_route(): void
    {
        $this->postJson("/api/v1/routes/{$this->route->id}/ratings", ['stars' => 4])
            ->assertStatus(401);
    }
}
