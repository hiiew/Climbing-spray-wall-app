<?php

declare(strict_types=1);

namespace App\Jobs;

use App\Events\WallScanComplete;
use App\Events\WallScanFailed;
use App\Exceptions\HoldDetectionException;
use App\Models\Wall;
use App\Services\HoldDetectionService;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;
use Throwable;

/**
 * ProcessWallImageJob
 *
 * Dispatched immediately after a wall image is uploaded to S3.
 * Runs asynchronously on the 'cv-processing' queue monitored by Horizon.
 *
 * Retry policy:
 *   - 3 attempts total
 *   - Exponential backoff: 30s → 120s → 300s
 *   - Timeout per attempt: 130s (slightly above the CV service timeout of 120s)
 *
 * On final failure: wall marked scan_failed, WallScanFailed event broadcast.
 */
class ProcessWallImageJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    /** @var int Max attempts before marking the wall as scan_failed */
    public int $tries = 3;

    /** @var int Per-attempt timeout in seconds */
    public int $timeout = 130;

    /** @var bool Release back to queue on timeout (allows retries) */
    public bool $failOnTimeout = false;

    public function __construct(
        public readonly Wall $wall,
        public readonly string $mode = 'fast',
    ) {
        $this->onQueue('cv-processing');
    }

    /**
     * Exponential backoff: [30, 120, 300] seconds between attempts.
     *
     * @return array<int, int>
     */
    public function backoff(): array
    {
        return [30, 120, 300];
    }

    /**
     * Execute the job.
     *
     * @param  HoldDetectionService $service  Injected via the service container
     */
    public function handle(HoldDetectionService $service): void
    {
        Log::info("[ProcessWallImageJob] Starting for wall={$this->wall->id}, attempt={$this->attempts()}");

        $this->wall->markScanning();

        try {
            // Call the CV microservice
            $holdsData = $service->detectHolds($this->wall, $this->mode);

            // Persist holds and update wall status
            $holdCount = $service->persistHolds($this->wall, $holdsData);
            $this->wall->markComplete($holdCount);

            // Notify the frontend via WebSocket
            broadcast(new WallScanComplete($this->wall->id, $holdCount))->toOthers();

            Log::info("[ProcessWallImageJob] Completed for wall={$this->wall->id}. {$holdCount} holds stored.");

        } catch (HoldDetectionException $e) {
            Log::warning(
                "[ProcessWallImageJob] Detection error on attempt {$this->attempts()}: {$e->getMessage()}",
                ['wall_id' => $this->wall->id, 'error_code' => $e->errorCode],
            );

            // Re-throw so Laravel's queue re-queues or calls failed()
            throw $e;
        }
    }

    /**
     * Called after all retries are exhausted.
     */
    public function failed(Throwable $exception): void
    {
        $reason = $exception instanceof HoldDetectionException
            ? "[{$exception->errorCode}] {$exception->getMessage()}"
            : $exception->getMessage();

        Log::error(
            "[ProcessWallImageJob] Permanently failed for wall={$this->wall->id}: {$reason}",
            ['exception' => get_class($exception)],
        );

        $this->wall->markFailed($reason);

        broadcast(new WallScanFailed($this->wall->id, $reason));
    }
}
