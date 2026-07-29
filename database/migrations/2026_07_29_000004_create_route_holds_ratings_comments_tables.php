<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('route_holds', function (Blueprint $table): void {
            $table->id();
            $table->foreignUlid('route_id')->constrained('routes')->cascadeOnDelete();
            $table->foreignUlid('hold_id')->constrained('holds')->cascadeOnDelete();
            $table->unsignedTinyInteger('position_order')->comment('Sequence index in the route');
            $table->enum('role', ['start', 'hand', 'foot', 'finish']);

            $table->unique(['route_id', 'hold_id']);
            $table->index(['route_id', 'position_order']);
        });

        Schema::create('ratings', function (Blueprint $table): void {
            $table->id();
            $table->foreignUlid('route_id')->constrained('routes')->cascadeOnDelete();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->unsignedTinyInteger('stars')->comment('1–5 stars');
            $table->timestamps();

            $table->unique(['route_id', 'user_id']);
            $table->index('route_id');
        });

        Schema::create('comments', function (Blueprint $table): void {
            $table->id();
            $table->foreignUlid('route_id')->constrained('routes')->cascadeOnDelete();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->text('body');
            $table->timestamps();
            $table->softDeletes();

            $table->index(['route_id', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('comments');
        Schema::dropIfExists('ratings');
        Schema::dropIfExists('route_holds');
    }
};
