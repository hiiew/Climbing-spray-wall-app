<?php

declare(strict_types=1);

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class WallResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id'         => $this->id,
            'name'       => $this->name,
            'angle'      => $this->angle,
            'width_cm'   => $this->width_cm,
            'height_cm'  => $this->height_cm,
            'status'     => $this->status,
            'hold_count' => $this->hold_count,
            'image_url'  => $this->image_url,
            'scan_error' => $this->when($this->status === 'scan_failed', $this->scan_error),
            'created_at' => $this->created_at->toIso8601String(),
            'updated_at' => $this->updated_at->toIso8601String(),
        ];
    }
}
