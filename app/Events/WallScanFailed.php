<?php

declare(strict_types=1);

namespace App\Events;

use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class WallScanFailed implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels;

    public function __construct(
        public readonly string $wallId,
        public readonly string $reason,
    ) {}

    public function broadcastOn(): array
    {
        return [new PrivateChannel("user.{$this->getWallUserId()}")];
    }

    public function broadcastAs(): string
    {
        return 'WallScanFailed';
    }

    public function broadcastWith(): array
    {
        return [
            'wall_id' => $this->wallId,
            'reason'  => $this->reason,
            'status'  => 'scan_failed',
        ];
    }

    private function getWallUserId(): int
    {
        return \App\Models\Wall::find($this->wallId)?->user_id ?? 0;
    }
}
