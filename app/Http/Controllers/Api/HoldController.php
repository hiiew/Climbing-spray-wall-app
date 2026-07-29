<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Requests\Hold\UpdateHoldRequest;
use App\Http\Resources\HoldResource;
use App\Models\Hold;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Gate;

class HoldController extends Controller
{
    /**
     * PATCH /api/v1/holds/{hold}
     *
     * Allow users to correct hold type or exclude a hold from route generation.
     */
    public function update(UpdateHoldRequest $request, Hold $hold): HoldResource
    {
        Gate::authorize('update', $hold);
        $hold->update($request->only(['excluded', 'type']));

        return new HoldResource($hold);
    }

    /**
     * DELETE /api/v1/holds/{hold}
     *
     * Remove a falsely detected hold (user correction).
     */
    public function destroy(Hold $hold): JsonResponse
    {
        Gate::authorize('delete', $hold);
        $hold->delete();

        return response()->json(null, 204);
    }
}
