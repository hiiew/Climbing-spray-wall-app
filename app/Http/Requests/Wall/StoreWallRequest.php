<?php

declare(strict_types=1);

namespace App\Http\Requests\Wall;

use Illuminate\Foundation\Http\FormRequest;

class StoreWallRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true; // Auth enforced via route middleware
    }

    public function rules(): array
    {
        return [
            'name'      => ['required', 'string', 'max:100'],
            'angle'     => ['required', 'integer', 'min:0', 'max:70'],
            'width_cm'  => ['required', 'integer', 'min:50', 'max:1000'],
            'height_cm' => ['required', 'integer', 'min:50', 'max:1000'],
            'image'     => [
                'required',
                'file',
                'mimes:jpeg,jpg,png,heic',
                'max:20480',      // 20 MB in kilobytes
                'dimensions:min_width=1000,min_height=1000',
            ],
        ];
    }

    public function messages(): array
    {
        return [
            'image.max'        => 'The wall image must be under 20 MB.',
            'image.dimensions' => 'The image must be at least 1000×1000 pixels.',
            'image.mimes'      => 'Only JPEG, PNG, and HEIC images are accepted.',
            'angle.max'        => 'Wall angle cannot exceed 70 degrees.',
        ];
    }
}
