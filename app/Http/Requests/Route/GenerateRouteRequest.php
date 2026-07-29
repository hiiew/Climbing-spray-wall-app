<?php

declare(strict_types=1);

namespace App\Http\Requests\Route;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class GenerateRouteRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'grade' => [
                'required',
                Rule::in([
                    'V0','V1','V2','V3','V4','V5','V6','V7','V8',
                    'V9','V10','V11','V12','V13','V14','V15','V16','auto',
                ]),
            ],
            'style' => [
                'required',
                Rule::in(['dynamic', 'balance', 'compression', 'endurance', 'coordination']),
            ],
            'body_type'  => ['sometimes', Rule::in(['default', 'tall', 'short'])],
            'hold_count' => ['sometimes', 'nullable', 'integer', 'min:4', 'max:20'],
        ];
    }
}
