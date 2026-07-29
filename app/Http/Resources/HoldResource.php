<?php

declare(strict_types=1);

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class HoldResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id'               => $this->id,
            'wall_id'          => $this->wall_id,
            'x'                => $this->x,
            'y'                => $this->y,
            'width'            => $this->width,
            'height'           => $this->height,
            'center_x'         => $this->center_x,
            'center_y'         => $this->center_y,
            'area'             => $this->area,
            'color'            => $this->color,
            'color_hex'        => $this->color_hex,
            'type'             => $this->type,
            'confidence_score' => $this->confidence_score,
            'type_confidence'  => $this->type_confidence,
            'is_verified'      => $this->is_verified,
            'excluded'         => $this->excluded,
            // Pivot data when loaded as part of a route
            'role'             => $this->whenPivotLoaded('route_holds', fn() => $this->pivot->role),
            'position_order'   => $this->whenPivotLoaded('route_holds', fn() => $this->pivot->position_order),
        ];
    }
}
