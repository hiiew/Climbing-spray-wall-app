<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\SoftDeletes;

class Comment extends Model
{
    use SoftDeletes;

    protected $fillable = ['route_id', 'user_id', 'body'];

    public function route(): BelongsTo
    {
        return $this->belongsTo(Route::class);
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }
}
