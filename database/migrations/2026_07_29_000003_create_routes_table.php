<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('routes', function (Blueprint $table): void {
            $table->ulid('id')->primary();
            $table->foreignUlid('wall_id')->constrained('walls')->cascadeOnDelete();
            $table->foreignId('setter_id')->constrained('users')->cascadeOnDelete();

            $table->string('name', 100)->nullable()->comment('Null = unsaved draft');
            $table->text('description')->nullable();

            $table->string('grade', 5)->comment('V-scale: V0–V16');
            $table->enum('style', [
                'dynamic', 'balance', 'compression', 'endurance', 'coordination',
            ]);

            $table->decimal('quality_score', 4, 3)->comment('AI quality score 0.0–1.0');
            $table->unsignedTinyInteger('hold_count')->default(0);

            $table->boolean('is_published')->default(false);
            $table->string('share_token', 20)->unique()->nullable();

            $table->decimal('average_rating', 3, 2)->default(0.00);
            $table->unsignedSmallInteger('total_ratings')->default(0);

            $table->timestamps();
            $table->softDeletes();

            $table->index(['wall_id', 'is_published']);
            $table->index(['setter_id', 'is_published']);
            $table->index('share_token');
            $table->index('grade');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('routes');
    }
};
