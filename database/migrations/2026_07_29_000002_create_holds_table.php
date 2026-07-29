<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Creates the `holds` table.
 *
 * All coordinate values are normalised to [0.0, 1.0] relative to the original
 * image dimensions, making them resolution-independent.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('holds', function (Blueprint $table): void {
            $table->ulid('id')->primary();
            $table->foreignUlid('wall_id')->constrained('walls')->cascadeOnDelete();

            // Normalised bounding box coordinates [0.0 – 1.0]
            $table->decimal('x', 8, 6)->comment('Left edge (normalised)');
            $table->decimal('y', 8, 6)->comment('Top edge (normalised)');
            $table->decimal('width', 8, 6)->comment('Bounding box width (normalised)');
            $table->decimal('height', 8, 6)->comment('Bounding box height (normalised)');
            $table->decimal('center_x', 8, 6);
            $table->decimal('center_y', 8, 6);
            $table->decimal('area', 10, 8)->comment('Bounding box area as fraction of image area');

            // Detection metadata
            $table->enum('color', [
                'red', 'orange', 'yellow', 'green', 'blue',
                'purple', 'pink', 'black', 'white', 'grey', 'unknown',
            ])->default('unknown');
            $table->string('color_hex', 7)->default('#9CA3AF');

            $table->enum('type', [
                'jug', 'crimp', 'sloper', 'pinch', 'pocket', 'foothold', 'volume', 'unknown',
            ])->default('unknown');

            $table->decimal('confidence_score', 5, 4)->comment('YOLO detection confidence 0.0–1.0');
            $table->decimal('type_confidence', 5, 4)->nullable()->comment('Hold-type classification confidence');

            $table->boolean('is_verified')->default(true)->comment('False if confidence < 0.50');
            $table->boolean('excluded')->default(false)->comment('User-excluded from route generation');

            $table->timestamps();

            $table->index(['wall_id', 'excluded']);
            $table->index(['wall_id', 'color']);
            $table->index(['wall_id', 'type']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('holds');
    }
};
