<?php

declare(strict_types=1);

namespace App\Http\Requests\Hold;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class UpdateHoldRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'excluded' => ['sometimes', 'boolean'],
            'type'     => [
                'sometimes',
                Rule::in(['jug', 'crimp', 'sloper', 'pinch', 'pocket', 'foothold', 'volume', 'unknown']),
            ],
        ];
    }
}
