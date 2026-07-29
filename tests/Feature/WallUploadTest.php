<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Jobs\ProcessWallImageJob;
use App\Models\User;
use App\Models\Wall;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Queue;
use Illuminate\Support\Facades\Storage;
use Tests\TestCase;

/**
 * Feature tests for the wall upload endpoint.
 *
 * Tests the full HTTP request cycle — routing, validation, S3 storage,
 * and job dispatch — without touching the CV service.
 */
class WallUploadTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    protected function setUp(): void
    {
        parent::setUp();
        Storage::fake('s3');
        Queue::fake();

        $this->user = User::factory()->create();
    }

    // ── Happy path ────────────────────────────────────────────────────────────

    /** @test */
    public function authenticated_user_can_upload_a_wall_image(): void
    {
        $response = $this->actingAs($this->user)
            ->postJson('/api/v1/walls', [
                'name'      => 'Garage Board 40°',
                'angle'     => 40,
                'width_cm'  => 244,
                'height_cm' => 244,
                'image'     => UploadedFile::fake()->image('wall.jpg', 1200, 1200)->size(5000),
            ]);

        $response->assertStatus(202)
            ->assertJsonPath('data.name', 'Garage Board 40°')
            ->assertJsonPath('data.status', 'pending_scan');

        $this->assertDatabaseHas('walls', [
            'user_id' => $this->user->id,
            'name'    => 'Garage Board 40°',
            'status'  => 'pending_scan',
        ]);

        Queue::assertPushed(ProcessWallImageJob::class);
    }

    /** @test */
    public function wall_image_is_stored_in_s3(): void
    {
        $this->actingAs($this->user)->postJson('/api/v1/walls', [
            'name'      => 'Test Wall',
            'angle'     => 0,
            'width_cm'  => 200,
            'height_cm' => 200,
            'image'     => UploadedFile::fake()->image('wall.jpg', 1200, 1200)->size(1000),
        ]);

        Storage::disk('s3')->assertExists(
            Wall::where('user_id', $this->user->id)->first()->image_path,
        );
    }

    /** @test */
    public function process_wall_image_job_is_dispatched_with_correct_wall(): void
    {
        $this->actingAs($this->user)->postJson('/api/v1/walls', [
            'name'      => 'Job Test Wall',
            'angle'     => 30,
            'width_cm'  => 200,
            'height_cm' => 200,
            'image'     => UploadedFile::fake()->image('wall.jpg', 1200, 1200)->size(2000),
        ]);

        $wall = Wall::where('user_id', $this->user->id)->first();

        Queue::assertPushed(ProcessWallImageJob::class, fn($job) => $job->wall->id === $wall->id);
    }

    // ── Validation error paths ────────────────────────────────────────────────

    /** @test */
    public function upload_fails_without_authentication(): void
    {
        $this->postJson('/api/v1/walls', [
            'name'  => 'Unauth Wall',
            'angle' => 40,
        ])->assertStatus(401);

        Queue::assertNothingPushed();
    }

    /** @test */
    public function upload_fails_when_image_is_missing(): void
    {
        $this->actingAs($this->user)->postJson('/api/v1/walls', [
            'name'      => 'No Image Wall',
            'angle'     => 20,
            'width_cm'  => 200,
            'height_cm' => 200,
        ])->assertStatus(422)->assertJsonValidationErrors(['image']);
    }

    /** @test */
    public function upload_fails_when_image_exceeds_20mb(): void
    {
        $this->actingAs($this->user)->postJson('/api/v1/walls', [
            'name'      => 'Big Image Wall',
            'angle'     => 20,
            'width_cm'  => 200,
            'height_cm' => 200,
            'image'     => UploadedFile::fake()->image('wall.jpg', 1200, 1200)->size(21000), // 21 MB
        ])->assertStatus(422)->assertJsonValidationErrors(['image']);
    }

    /** @test */
    public function upload_fails_when_image_is_below_minimum_resolution(): void
    {
        $this->actingAs($this->user)->postJson('/api/v1/walls', [
            'name'      => 'Tiny Image Wall',
            'angle'     => 20,
            'width_cm'  => 200,
            'height_cm' => 200,
            'image'     => UploadedFile::fake()->image('wall.jpg', 500, 400)->size(100), // 500x400 — too small
        ])->assertStatus(422)->assertJsonValidationErrors(['image']);
    }

    /** @test */
    public function upload_fails_when_wall_angle_exceeds_70_degrees(): void
    {
        $this->actingAs($this->user)->postJson('/api/v1/walls', [
            'name'      => 'Steep Wall',
            'angle'     => 75,
            'width_cm'  => 200,
            'height_cm' => 200,
            'image'     => UploadedFile::fake()->image('wall.jpg', 1200, 1200)->size(1000),
        ])->assertStatus(422)->assertJsonValidationErrors(['angle']);
    }

    // ── Wall listing ──────────────────────────────────────────────────────────

    /** @test */
    public function user_can_list_only_their_own_walls(): void
    {
        $otherUser = User::factory()->create();
        Wall::factory()->count(3)->for($this->user)->create();
        Wall::factory()->count(2)->for($otherUser)->create();

        $response = $this->actingAs($this->user)->getJson('/api/v1/walls');

        $response->assertOk()
            ->assertJsonCount(3, 'data');
    }

    /** @test */
    public function user_cannot_view_another_users_wall(): void
    {
        $otherWall = Wall::factory()->for(User::factory()->create())->create();

        $this->actingAs($this->user)
            ->getJson("/api/v1/walls/{$otherWall->id}")
            ->assertForbidden();
    }
}
