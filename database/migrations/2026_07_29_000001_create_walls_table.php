<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Creates the `walls` table.
 *
 * Each wall belongs to a user and represents one physical spray wall
 * with a corresponding image stored in S3.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('walls', function (Blueprint $table): void {
            $table->ulid('id')->primary();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();

            $table->string('name', 100);
            $table->unsignedTinyInteger('angle')->default(0)->comment('Wall overhang angle in degrees (0–70)');
            $table->unsignedSmallInteger('width_cm')->comment('Panel width in centimetres');
            $table->unsignedSmallInteger('height_cm')->comment('Panel height in centimetres');
            $table->string('image_url')->comment('S3 object URL of the raw wall photograph');
            $table->string('image_path')->comment('S3 object key/path for deletion');

            $table->enum('status', [
                'pending_scan',
                'scanning',
                'scan_complete',
                'scan_failed',
            ])->default('pending_scan');

            $table->unsignedSmallInteger('hold_count')->default(0);
            $table->text('scan_error')->nullable()->comment('Error message if status=scan_failed');

            $table->timestamps();
            $table->softDeletes();

            $table->index(['user_id', 'status']);
            $table->index('created_at');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('walls');
    }
};
