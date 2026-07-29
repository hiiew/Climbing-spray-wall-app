<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;

/**
 * @property string  $id
 * @property int     $user_id
 * @property string  $name
 * @property int     $angle
 * @property int     $width_cm
 * @property int     $height_cm
 * @property string  $image_url
 * @property string  $image_path
 * @property string  $status  pending_scan|scanning|scan_complete|scan_failed
 * @property int     $hold_count
 * @property ?string $scan_error
 */
class Wall extends Model
{
    use HasFactory, HasUlids, SoftDeletes;

    protected $fillable = [
        'user_id', 'name', 'angle', 'width_cm', 'height_cm',
        'image_url', 'image_path', 'status', 'hold_count', 'scan_error',
    ];

    protected $casts = [
        'angle'      => 'integer',
        'width_cm'   => 'integer',
        'height_cm'  => 'integer',
        'hold_count' => 'integer',
    ];

    // ── Status constants ────────────────────────────────────────────────────

    public const STATUS_PENDING  = 'pending_scan';
    public const STATUS_SCANNING = 'scanning';
    public const STATUS_COMPLETE = 'scan_complete';
    public const STATUS_FAILED   = 'scan_failed';

    // ── Relationships ────────────────────────────────────────────────────────

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function holds(): HasMany
    {
        return $this->hasMany(Hold::class);
    }

    public function routes(): HasMany
    {
        return $this->hasMany(Route::class);
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    public function markScanning(): bool
    {
        return $this->update(['status' => self::STATUS_SCANNING]);
    }

    public function markComplete(int $holdCount): bool
    {
        return $this->update([
            'status'     => self::STATUS_COMPLETE,
            'hold_count' => $holdCount,
            'scan_error' => null,
        ]);
    }

    public function markFailed(string $reason): bool
    {
        return $this->update([
            'status'     => self::STATUS_FAILED,
            'scan_error' => $reason,
        ]);
    }
}
