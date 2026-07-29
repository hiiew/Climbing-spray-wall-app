<?php

declare(strict_types=1);

use App\Http\Controllers\Api\HoldController;
use App\Http\Controllers\Api\RouteController;
use App\Http\Controllers\Api\WallController;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;

/*
|--------------------------------------------------------------------------
| API Routes — Climbing Spray Wall App
|--------------------------------------------------------------------------
|
| Version: v1
| Auth:    Laravel Sanctum (stateless token auth for SPA)
|
| Route naming convention: resource.action  e.g. walls.store, routes.generate
|
*/

// ── Health ───────────────────────────────────────────────────────────────────
Route::get('/health', fn() => response()->json(['status' => 'ok']))->name('health');

// ── Auth ─────────────────────────────────────────────────────────────────────
Route::prefix('v1')->group(function (): void {

    Route::post('/auth/register', [\App\Http\Controllers\Api\AuthController::class, 'register'])->name('auth.register');
    Route::post('/auth/login',    [\App\Http\Controllers\Api\AuthController::class, 'login'])->name('auth.login');

    // ── Authenticated routes ──────────────────────────────────────────────────
    Route::middleware('auth:sanctum')->group(function (): void {

        Route::get('/user', fn(Request $r) => $r->user())->name('user.me');
        Route::post('/auth/logout', [\App\Http\Controllers\Api\AuthController::class, 'logout'])->name('auth.logout');

        // ── Walls ─────────────────────────────────────────────────────────────
        Route::apiResource('walls', WallController::class)->except(['update']);
        Route::get('walls/{wall}/holds', [WallController::class, 'holds'])->name('walls.holds');

        // ── Holds ─────────────────────────────────────────────────────────────
        Route::patch('holds/{hold}',  [HoldController::class, 'update'])->name('holds.update');
        Route::delete('holds/{hold}', [HoldController::class, 'destroy'])->name('holds.destroy');

        // ── Route Generation ──────────────────────────────────────────────────
        Route::post('walls/{wall}/routes/generate', [RouteController::class, 'generate'])->name('routes.generate');
        Route::get('walls/{wall}/routes',            [RouteController::class, 'index'])->name('walls.routes.index');

        // ── Routes (saved) ────────────────────────────────────────────────────
        Route::get('routes/{route}',     [RouteController::class, 'show'])->name('routes.show');
        Route::patch('routes/{route}',   [RouteController::class, 'save'])->name('routes.save');
        Route::delete('routes/{route}',  [RouteController::class, 'destroy'])->name('routes.destroy');

        // ── Ratings & Comments ────────────────────────────────────────────────
        Route::post('routes/{route}/ratings',  [RouteController::class, 'rate'])->name('routes.rate');
        Route::post('routes/{route}/comments', [RouteController::class, 'comment'])->name('routes.comment');
    });

    // ── Public route (no auth) ────────────────────────────────────────────────
    Route::get('/share/{token}', [RouteController::class, 'showByToken'])->name('routes.share');
});
