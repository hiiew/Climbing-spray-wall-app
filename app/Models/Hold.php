<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;

/**
 * @property string  $id
 * @property string  $wall_id
 * @property float   $x
 * @property float   $y
 * @property float   $width
 * @property float   $height
 * @property float   $center_x
 * @property float   $center_y
 * @property float   $area
 * @property string  $color
 * @property string  $color_hex
 * @property string  $type
 * @property float   $confidence_score
 * @property ?float  $type_confidence
 * @property bool    $is_verified
 * @property bool    $excluded
 */
class Hold extends Model
{
    use HasFactory, HasUlids;

    protected $fillable = [
        'wall_id', 'x', 'y', 'width', 'height', 'center_x', 'center_y', 'area',
        'color', 'color_hex', 'type', 'confidence_score', 'type_confidence',
        'is_verified', 'excluded',
    ];

    protected $casts = [
        'x'                => 'float',
        'y'                => 'float',
        'width'            => 'float',
        'height'           => 'float',
        'center_x'         => 'float',
        'center_y'         => 'float',
        'area'             => 'float',
        'confidence_score' => 'float',
        'type_confidence'  => 'float',
        'is_verified'      => 'boolean',
        'excluded'         => 'boolean',
    ];

    // ── Relationships ────────────────────────────────────────────────────────

    public function wall(): BelongsTo
    {
        return $this->belongsTo(Wall::class);
    }

    public function routes(): BelongsToMany
    {
        return $this->belongsToMany(Route::class, 'route_holds')
            ->withPivot(['position_order', 'role'])
            ->orderByPivot('position_order');
    }

    // ── Scopes ───────────────────────────────────────────────────────────────

    /**
     * Filter to only holds eligible for route generation.
     */
    public function scopeActive($query)
    {
        return $query->where('excluded', false);
    }
}
