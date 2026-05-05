'use client';

import type { Locale } from '@/lib/i18n';

export interface ThreeDGuidedConfig {
  theme: string;
  style?: string;
  language?: Locale;
  text_model_name: string;
  text_api_key: string;
  audio_model_name: string;
  audio_api_key: string;
  voice?: string;
  three_d_guided_service_url: string;
  with_media_prompts?: boolean;
}

export interface ThreeDGuidedTaskCreateResponse {
  task_id: string;
  project_id: string;
  status: string;
  message: string;
}

export async function createThreeDGuidedTask(
  config: ThreeDGuidedConfig,
  projectId?: string,
): Promise<ThreeDGuidedTaskCreateResponse> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);

  const payload = {
    theme: config.theme,
    style: config.style,
    language: config.language,
    text_model_name: config.text_model_name,
    text_api_key: config.text_api_key,
    image_model_name: 'mw_3d_guided',
    image_api_key: config.three_d_guided_service_url,
    audio_model_name: config.audio_model_name,
    audio_api_key: config.audio_api_key,
    voice: config.voice,
    with_media_prompts: config.with_media_prompts,
  };

  const response = await fetch(`/api/video/compose${params.size ? `?${params.toString()}` : ''}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || '3D GUIDED 生成失败');
  }

  return response.json();
}
