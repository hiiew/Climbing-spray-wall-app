<?php

declare(strict_types=1);

namespace App\Services;

use App\Exceptions\HoldDetectionException;
use App\Models\Hold;
use App\Models\Wall;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * HoldDetectionService
 *
 * Orchestrates the communication between the Laravel backend and the Python
 * CV microservice. Responsible for:
 *   1. Calling POST /detect-holds on the CV service
 *   2. Validating the response structure
 *   3. Bulk-inserting detected holds into the database
 *
 * This service is intentionally kept thin — business logic (scoring, etc.)
 * lives in the CV service; persistence logic lives here.
 */
class HoldDetectionService
{
    private string $cvServiceUrl;
    private int    $timeoutSeconds;

    public function __construct()
    {
        $this->cvServiceUrl   = rtrim((string) config('services.cv_service.url'), '/');
        $this->timeoutSeconds = (int) config('services.cv_service.timeout', 120);
    }

    /**
     * Call the CV microservice synchronously and return the raw holds array.
     *
     * @param  Wall   $wall      The wall model (must have image_url set)
     * @param  string $mode      'fast' or 'accurate'
     * @param  array  $options   Optional detection parameters
     * @return array<int, array> Raw holds from the CV service response
     *
     * @throws HoldDetectionException
     */
    public function detectHolds(
        Wall $wall,
        string $mode = 'fast',
        array $options = [],
    ): array {
        Log::info("[HoldDetectionService] Calling CV service for wall={$wall->id}");

        try {
            $response = Http::timeout($this->timeoutSeconds)
                ->retry(2, 5000) // 2 retries, 5s delay
                ->post("{$this->cvServiceUrl}/detect-holds", [
                    'wall_id'   => $wall->id,
                    'image_url' => $wall->image_url,
                    'mode'      => $mode,
                    'options'   => $options,
                ]);

            if ($response->failed()) {
                $errorBody = $response->json('error', []);
                $errorCode = $errorBody['code'] ?? 'INTERNAL_ERROR';
                $message   = $errorBody['message'] ?? "CV service returned HTTP {$response->status()}";

                Log::error("[HoldDetectionService] CV service error: {$errorCode} — {$message}", [
                    'wall_id' => $wall->id,
                    'status'  => $response->status(),
                ]);

                throw new HoldDetectionException($message, $errorCode, $wall->id);
            }

            $holds = $response->json('holds', []);

            Log::info("[HoldDetectionService] CV service returned " . count($holds) . " holds for wall={$wall->id}");

            return $holds;

        } catch (ConnectionException $e) {
            Log::critical("[HoldDetectionService] Cannot reach CV service: {$e->getMessage()}");
            throw new HoldDetectionException(
                'The hold detection service is currently unavailable.',
                'CV_SERVICE_UNREACHABLE',
                $wall->id,
                $e,
            );
        } catch (RequestException $e) {
            throw new HoldDetectionException(
                "Request to CV service failed: {$e->getMessage()}",
                'CV_REQUEST_FAILED',
                $wall->id,
                $e,
            );
        }
    }

    /**
     * Persist the detected holds returned by the CV service.
     *
     * Uses bulk insert via Eloquent for performance.
     * Deletes any previously detected holds for this wall first (idempotent).
     *
     * @param  Wall   $wall
     * @param  array  $holdsData  Raw holds array from detectHolds()
     * @return int    Number of holds persisted
     */
    public function persistHolds(Wall $wall, array $holdsData): int
    {
        // Delete any stale holds from a previous (failed) scan
        $wall->holds()->delete();

        $records = array_map(
            fn(array $hold): array => $this->mapHoldToDatabaseRecord($wall->id, $hold),
            $holdsData,
        );

        Hold::insert($records);

        $count = count($records);
        Log::info("[HoldDetectionService] Persisted {$count} holds for wall={$wall->id}");

        return $count;
    }

    /**
     * Map a single CV-service hold response to a database record array.
     *
     * @param  string $wallId
     * @param  array  $hold  Raw hold from CV service
     * @return array<string, mixed>
     */
    private function mapHoldToDatabaseRecord(string $wallId, array $hold): array
    {
        $now = now()->toDateTimeString();

        return [
            'id'               => $hold['id'],
            'wall_id'          => $wallId,
            'x'                => $hold['x'],
            'y'                => $hold['y'],
            'width'            => $hold['width'],
            'height'           => $hold['height'],
            'center_x'         => $hold['center_x'],
            'center_y'         => $hold['center_y'],
            'area'             => $hold['area'],
            'color'            => $hold['color'],
            'color_hex'        => $hold['color_hex'],
            'type'             => $hold['type'],
            'confidence_score' => $hold['confidence'],
            'type_confidence'  => $hold['type_confidence'] ?? null,
            'is_verified'      => $hold['is_verified'] ?? true,
            'excluded'         => false,
            'created_at'       => $now,
            'updated_at'       => $now,
        ];
    }
}
