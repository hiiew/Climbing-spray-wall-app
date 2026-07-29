<?php

// Append this to your existing config/services.php array:

return [

    // ... existing services (mailgun, ses, etc.) ...

    /*
    |--------------------------------------------------------------------------
    | Python CV Microservice
    |--------------------------------------------------------------------------
    */
    'cv_service' => [
        'url'     => env('CV_SERVICE_URL', 'http://cv-service:8001'),
        'timeout' => env('CV_SERVICE_TIMEOUT', 120),
    ],

];
