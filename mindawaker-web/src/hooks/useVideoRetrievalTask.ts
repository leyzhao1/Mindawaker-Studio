'use client';

import type { Locale } from '@/lib/i18n';

export interface VideoRetrievalConfig {
  theme: string;
  style?: string;
  language?: Locale;
  text_model_name: string;
  text_api_key: string;
  audio_model_name: string;
  audio_api_key: string;
  voice?: string;
  with_media_prompts?: boolean;
  media_prompt_style?: string;
  annotation_root: string;
  media_service_base_url?: string;
  top_k_per_line?: number;
  prefer_media_type?: string;
  math_background_enabled?: boolean;
}

export interface VideoRetrievalTaskCreateResponse {
  task_id: string;
  project_id: string;
  status: string;
  message: string;
}

export async function createVideoRetrievalTask(
  config: VideoRetrievalConfig,
  projectId?: string,
): Promise<VideoRetrievalTaskCreateResponse> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);

  const response = await fetch(`/api/video-retrieval/compose${params.size ? `?${params.toString()}` : ''}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || '视频检索生成失败');
  }

  return response.json();
}
