<?php

declare(strict_types=1);

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class RouteResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id'             => $this->id,
            'wall_id'        => $this->wall_id,
            'name'           => $this->name,
            'description'    => $this->description,
            'grade'          => $this->grade,
            'style'          => $this->style,
            'quality_score'  => $this->quality_score,
            'hold_count'     => $this->hold_count,
            'is_published'   => $this->is_published,
            'average_rating' => $this->average_rating,
            'total_ratings'  => $this->total_ratings,
            'share_url'      => $this->when(
                $this->share_token !== null,
                fn() => url("/routes/{$this->share_token}"),
            ),
            'status'         => $this->name === null ? 'unsaved' : 'saved',
            'holds'          => HoldResource::collection($this->whenLoaded('holds')),
            'setter'         => new UserResource($this->whenLoaded('setter')),
            'created_at'     => $this->created_at->toIso8601String(),
        ];
    }
}
