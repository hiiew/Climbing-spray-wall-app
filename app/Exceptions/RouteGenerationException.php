<?php

declare(strict_types=1);

namespace App\Exceptions;

use RuntimeException;

class RouteGenerationException extends RuntimeException
{
    public function __construct(
        string $message,
        public readonly string $errorCode,
        \Throwable $previous = null,
    ) {
        parent::__construct($message, 0, $previous);
    }
}
