<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;
use Illuminate\Support\Str;

/**
 * @property string  $id
 * @property string  $wall_id
 * @property int     $setter_id
 * @property ?string $name
 * @property ?string $description
 * @property string  $grade
 * @property string  $style
 * @property float   $quality_score
 * @property int     $hold_count
 * @property bool    $is_published
 * @property ?string $share_token
 * @property float   $average_rating
 * @property int     $total_ratings
 */
class Route extends Model
{
    use HasFactory, HasUlids, SoftDeletes;

    protected $fillable = [
        'wall_id', 'setter_id', 'name', 'description', 'grade', 'style',
        'quality_score', 'hold_count', 'is_published', 'share_token',
        'average_rating', 'total_ratings',
    ];

    protected $casts = [
        'quality_score'  => 'float',
        'hold_count'     => 'integer',
        'is_published'   => 'boolean',
        'average_rating' => 'float',
        'total_ratings'  => 'integer',
    ];

    // ── Relationships ────────────────────────────────────────────────────────

    public function wall(): BelongsTo
    {
        return $this->belongsTo(Wall::class);
    }

    public function setter(): BelongsTo
    {
        return $this->belongsTo(User::class, 'setter_id');
    }

    public function holds(): BelongsToMany
    {
        return $this->belongsToMany(Hold::class, 'route_holds')
            ->withPivot(['position_order', 'role'])
            ->orderByPivot('position_order');
    }

    public function ratings(): HasMany
    {
        return $this->hasMany(Rating::class);
    }

    public function comments(): HasMany
    {
        return $this->hasMany(Comment::class)->latest();
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    /**
     * Generate and persist a cryptographically random share token.
     */
    public function generateShareToken(): string
    {
        $token = Str::random(20);
        $this->update(['share_token' => $token, 'is_published' => true]);

        return $token;
    }

    /**
     * Recalculate and save the denormalised average_rating and total_ratings.
     * Called after each rating insert/update/delete.
     */
    public function recalculateRating(): void
    {
        $stats = $this->ratings()->selectRaw('COUNT(*) as total, AVG(stars) as average')->first();

        $this->update([
            'total_ratings'  => (int) $stats->total,
            'average_rating' => round((float) $stats->average, 2),
        ]);
    }

    // ── Scopes ───────────────────────────────────────────────────────────────

    public function scopePublished($query)
    {
        return $query->where('is_published', true);
    }
}
