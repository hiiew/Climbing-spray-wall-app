<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * AuthTest — Feature tests for registration, login, and authorisation.
 *
 * Tests the full HTTP cycle: routing → validation → token issuance.
 * Uses RefreshDatabase so no state bleeds between tests.
 */
class AuthTest extends TestCase
{
    use RefreshDatabase;

    // ── Registration ──────────────────────────────────────────────────────────

    /** @test */
    public function user_can_register_with_valid_credentials(): void
    {
        $response = $this->postJson('/api/v1/auth/register', [
            'name'                  => 'Alice Climber',
            'email'                 => 'alice@example.com',
            'password'              => 'Secure@1234',
            'password_confirmation' => 'Secure@1234',
        ]);

        $response->assertStatus(201)
            ->assertJsonStructure([
                'data' => ['id', 'name', 'email'],
                'token',
            ]);

        $this->assertDatabaseHas('users', ['email' => 'alice@example.com']);
    }

    /** @test */
    public function registration_fails_with_duplicate_email(): void
    {
        User::factory()->create(['email' => 'dupe@example.com']);

        $this->postJson('/api/v1/auth/register', [
            'name'                  => 'Dupe User',
            'email'                 => 'dupe@example.com',
            'password'              => 'Secure@1234',
            'password_confirmation' => 'Secure@1234',
        ])->assertStatus(422)
          ->assertJsonValidationErrors(['email']);
    }

    /** @test */
    public function registration_fails_when_password_confirmation_missing(): void
    {
        $this->postJson('/api/v1/auth/register', [
            'name'     => 'Bob',
            'email'    => 'bob@example.com',
            'password' => 'Secure@1234',
        ])->assertStatus(422)
          ->assertJsonValidationErrors(['password']);
    }

    /** @test */
    public function registration_fails_when_password_too_short(): void
    {
        $this->postJson('/api/v1/auth/register', [
            'name'                  => 'Short',
            'email'                 => 'short@example.com',
            'password'              => '123',
            'password_confirmation' => '123',
        ])->assertStatus(422)
          ->assertJsonValidationErrors(['password']);
    }

    // ── Login ─────────────────────────────────────────────────────────────────

    /** @test */
    public function user_can_login_with_correct_credentials(): void
    {
        $user = User::factory()->create(['email' => 'login@example.com']);
        $user->updatePassword('Secure@1234');   // or use factory state

        $response = $this->postJson('/api/v1/auth/login', [
            'email'    => 'login@example.com',
            'password' => 'Secure@1234',
        ]);

        $response->assertOk()
            ->assertJsonStructure(['token', 'data' => ['id', 'name', 'email']])
            ->assertJsonPath('data.email', 'login@example.com');

        $this->assertNotNull($response->json('token'));
    }

    /** @test */
    public function login_fails_with_wrong_password(): void
    {
        User::factory()->create(['email' => 'wrong@example.com']);

        $this->postJson('/api/v1/auth/login', [
            'email'    => 'wrong@example.com',
            'password' => 'WrongPassword!',
        ])->assertStatus(401)
          ->assertJsonPath('error.code', 'INVALID_CREDENTIALS');
    }

    /** @test */
    public function login_fails_for_nonexistent_email(): void
    {
        $this->postJson('/api/v1/auth/login', [
            'email'    => 'ghost@example.com',
            'password' => 'Secure@1234',
        ])->assertStatus(401);
    }

    /** @test */
    public function login_requires_email_format(): void
    {
        $this->postJson('/api/v1/auth/login', [
            'email'    => 'not-an-email',
            'password' => 'Secure@1234',
        ])->assertStatus(422)
          ->assertJsonValidationErrors(['email']);
    }

    // ── Authenticated Endpoints ───────────────────────────────────────────────

    /** @test */
    public function authenticated_user_can_get_their_profile(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)
            ->getJson('/api/v1/user')
            ->assertOk()
            ->assertJsonPath('id', $user->id)
            ->assertJsonPath('name', $user->name);
    }

    /** @test */
    public function unauthenticated_request_to_protected_endpoint_returns_401(): void
    {
        $this->getJson('/api/v1/user')->assertStatus(401);
        $this->getJson('/api/v1/walls')->assertStatus(401);
        $this->postJson('/api/v1/auth/logout')->assertStatus(401);
    }

    /** @test */
    public function authenticated_user_can_logout(): void
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)
            ->postJson('/api/v1/auth/logout');

        $response->assertStatus(204);
    }

    /** @test */
    public function logout_invalidates_sanctum_token(): void
    {
        $user  = User::factory()->create();
        $token = $user->createToken('test')->plainTextToken;

        // First request with token succeeds
        $this->withToken($token)
            ->getJson('/api/v1/user')
            ->assertOk();

        // Logout
        $this->withToken($token)
            ->postJson('/api/v1/auth/logout')
            ->assertStatus(204);

        // Same token now rejected
        $this->withToken($token)
            ->getJson('/api/v1/user')
            ->assertStatus(401);
    }

    // ── Rate Limiting ─────────────────────────────────────────────────────────

    /** @test */
    public function login_endpoint_is_rate_limited_after_too_many_attempts(): void
    {
        User::factory()->create(['email' => 'victim@example.com']);

        // Attempt 10 rapid failed logins
        for ($i = 0; $i < 10; $i++) {
            $this->postJson('/api/v1/auth/login', [
                'email'    => 'victim@example.com',
                'password' => 'WrongPass!',
            ]);
        }

        // 11th attempt should be throttled
        $this->postJson('/api/v1/auth/login', [
            'email'    => 'victim@example.com',
            'password' => 'WrongPass!',
        ])->assertStatus(429);
    }
}
