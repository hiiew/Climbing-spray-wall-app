<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Requests\Wall\StoreWallRequest;
use App\Http\Resources\HoldResource;
use App\Http\Resources\WallResource;
use App\Jobs\ProcessWallImageJob;
use App\Models\Wall;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\AnonymousResourceCollection;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

/**
 * WallController
 *
 * Handles CRUD for spray walls and delegates hold-related sub-resources
 * to dedicated routes. Image upload and CV processing are fully decoupled
 * via the job queue.
 */
class WallController extends Controller
{
    /**
     * GET /api/v1/walls
     *
     * List the authenticated user's walls, newest first.
     */
    public function index(Request $request): AnonymousResourceCollection
    {
        $walls = $request->user()
            ->walls()
            ->latest()
            ->paginate(15);

        return WallResource::collection($walls);
    }

    /**
     * POST /api/v1/walls
     *
     * Upload a wall image, create the wall record, and dispatch the CV job.
     */
    public function store(StoreWallRequest $request): JsonResponse
    {
        $file    = $request->file('image');
        $path    = "walls/{$request->user()->id}/" . Str::ulid() . '.' . $file->extension();
        $disk    = Storage::disk('s3');

        $disk->put($path, $file->getContent(), 'private');
        $imageUrl = $disk->temporaryUrl($path, now()->addDays(365));

        $wall = $request->user()->walls()->create([
            'name'      => $request->name,
            'angle'     => $request->angle,
            'width_cm'  => $request->width_cm,
            'height_cm' => $request->height_cm,
            'image_url' => $imageUrl,
            'image_path'=> $path,
            'status'    => Wall::STATUS_PENDING,
        ]);

        ProcessWallImageJob::dispatch($wall);

        return (new WallResource($wall))
            ->response()
            ->setStatusCode(202);
    }

    /**
     * GET /api/v1/walls/{wall}
     */
    public function show(Wall $wall): WallResource
    {
        Gate::authorize('view', $wall);

        return new WallResource($wall);
    }

    /**
     * DELETE /api/v1/walls/{wall}
     */
    public function destroy(Wall $wall): JsonResponse
    {
        Gate::authorize('delete', $wall);

        Storage::disk('s3')->delete($wall->image_path);
        $wall->delete();

        return response()->json(null, 204);
    }

    /**
     * GET /api/v1/walls/{wall}/holds
     *
     * Return all holds for a wall with optional filtering.
     */
    public function holds(Request $request, Wall $wall): AnonymousResourceCollection
    {
        Gate::authorize('view', $wall);

        $holds = $wall->holds()
            ->when($request->boolean('active_only'), fn($q) => $q->active())
            ->orderBy('center_y')
            ->orderBy('center_x')
            ->get();

        return HoldResource::collection($holds);
    }
}
