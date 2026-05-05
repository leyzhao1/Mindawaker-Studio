'use client';

import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Download, Loader2, Box, Video } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getAssetUrl, triggerDownload } from '@/lib/generated-files';
import { getStyleLabel, translate, type Locale } from '@/lib/i18n';
import { useTask, type TaskStatus } from '@/hooks/useTask';
import { createThreeDGuidedTask } from '@/hooks/useThreeDGuidedTask';
import type { SettingsDefaults } from '@/hooks/useSettings';

interface ThreeDGuidedGeneratorProps {
  defaults?: SettingsDefaults | null;
  locale: Locale;
}

const textModels = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'openai', label: 'OpenAI GPT' },
];

const audioModels = [
  { value: 'azure', label: 'Azure TTS' },
  { value: 'auralis', label: 'Auralis' },
  { value: 'microsoft', label: 'Microsoft TTS' },
];

const textStyles = ['温柔', '励志', '科普', '幽默', '严肃', 'story'];

export default function ThreeDGuidedGenerator({ defaults, locale }: ThreeDGuidedGeneratorProps) {
  const [theme, setTheme] = useState('');
  const [style, setStyle] = useState('温柔');
  const [textModelName, setTextModelName] = useState(defaults?.default_text_model_name || 'deepseek');
  const [textApiKey, setTextApiKey] = useState(defaults?.default_text_api_key || '');
  const [audioModelName, setAudioModelName] = useState(defaults?.default_audio_model_name || 'azure');
  const [audioApiKey, setAudioApiKey] = useState(defaults?.default_audio_api_key || '');
  const [voice, setVoice] = useState(defaults?.voices?.[0]?.name || 'me2');
  const [threeDGuidedServiceUrl, setThreeDGuidedServiceUrl] = useState('http://127.0.0.1:7000');
  const [withMediaPrompts, setWithMediaPrompts] = useState(true);
  const [didApplyDefaults, setDidApplyDefaults] = useState(false);
  const [taskMeta, setTaskMeta] = useState<{ taskId: string; projectId: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { status, connect, disconnect } = useTask({
    basePath: '/api/video',
    onError: (message) => setError(message),
  });

  const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate(locale, key, vars);

  useEffect(() => {
    if (!defaults || didApplyDefaults) return;
    setTextModelName((current) => current || defaults.default_text_model_name || 'deepseek');
    setTextApiKey((current) => current || defaults.default_text_api_key || '');
    setAudioModelName((current) => current || defaults.default_audio_model_name || 'azure');
    setAudioApiKey((current) => current || defaults.default_audio_api_key || '');
    setVoice((current) => current || defaults.voices?.[0]?.name || 'me2');
    setDidApplyDefaults(true);
  }, [defaults, didApplyDefaults]);

  useEffect(() => () => disconnect(), [disconnect]);

  const handleGenerate = async () => {
    setError(null);
    try {
      const task = await createThreeDGuidedTask({
        theme,
        style,
        language: locale,
        text_model_name: textModelName,
        text_api_key: textApiKey,
        audio_model_name: audioModelName,
        audio_api_key: audioApiKey,
        voice,
        three_d_guided_service_url: threeDGuidedServiceUrl,
        with_media_prompts: withMediaPrompts,
      });
      setTaskMeta({ taskId: task.task_id, projectId: task.project_id });
      connect(task.task_id);
    } catch (err: any) {
      setError(err.message || (locale === 'zh' ? '3D GUIDED 生成失败' : 'Failed to generate 3D GUIDED video'));
    }
  };

  const result = status?.result as TaskStatus['result'] | null;
  const videoUrl = useMemo(() => getAssetUrl(result?.video_path), [result?.video_path]);

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <Box className="h-5 w-5 text-cyan-500" />
          {t('threeDGuidedTitle')}
        </CardTitle>
        <CardDescription>{t('threeDGuidedDesc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="guided-theme">{t('theme')}</Label>
          <Input
            id="guided-theme"
            placeholder={locale === 'zh' ? '例如：未来城市中的夜景故事' : 'e.g. a night story in a futuristic city'}
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>{t('textModel')}</Label>
            <Select value={textModelName} onValueChange={setTextModelName}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {textModels.map((model) => (
                  <SelectItem key={model.value} value={model.value}>{model.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>{t('contentStyle')}</Label>
            <Select value={style} onValueChange={setStyle}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {textStyles.map((item) => (
                  <SelectItem key={item} value={item}>{getStyleLabel(item, locale)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="guided-text-key">{t('textApiKey')}</Label>
          <Input
            id="guided-text-key"
            type="password"
            value={textApiKey}
            onChange={(e) => setTextApiKey(e.target.value)}
            placeholder={locale === 'zh' ? '输入文本模型 API Key' : 'Enter text model API key'}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>{t('audioModel')}</Label>
            <Select value={audioModelName} onValueChange={setAudioModelName}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {audioModels.map((model) => (
                  <SelectItem key={model.value} value={model.value}>{model.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="guided-voice">{t('voice')}</Label>
            <Input
              id="guided-voice"
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              placeholder={locale === 'zh' ? '例如：me2 / alloy' : 'e.g. me2 / alloy'}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="guided-audio-key">{t('audioApiKey')}</Label>
          <Input
            id="guided-audio-key"
            type="password"
            value={audioApiKey}
            onChange={(e) => setAudioApiKey(e.target.value)}
            placeholder={locale === 'zh' ? '输入音频模型 API Key' : 'Enter audio model API key'}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="guided-service-url">{t('threeDGuidedServiceUrl')}</Label>
          <Input
            id="guided-service-url"
            value={threeDGuidedServiceUrl}
            onChange={(e) => setThreeDGuidedServiceUrl(e.target.value)}
            placeholder={String(t('threeDGuidedServiceUrlPlaceholder'))}
          />
        </div>

        <label className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
          <input type="checkbox" checked={withMediaPrompts} onChange={(e) => setWithMediaPrompts(e.target.checked)} />
          {t('enableMediaPrompts')}
        </label>

        <Button
          onClick={handleGenerate}
          disabled={!theme || !textApiKey || !audioApiKey || !threeDGuidedServiceUrl}
          className="w-full"
        >
          {status && !status.done ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Video className="mr-2 h-4 w-4" />}
          {t('startGeneration')}
        </Button>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {(taskMeta || status) && (
          <div className="space-y-3 rounded-lg border bg-slate-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="font-medium">{locale === 'zh' ? '任务进度' : 'Task progress'}</h3>
                <p className="text-sm text-muted-foreground">
                  {locale === 'zh' ? '文本生成 → 音频生成 → 图像生成 → 视频拼装' : 'Text generation → Audio generation → Image generation → Video assembly'}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {taskMeta?.projectId && <Badge variant="outline">{locale === 'zh' ? `项目 ${taskMeta.projectId}` : `Project ${taskMeta.projectId}`}</Badge>}
                {status?.status === 'completed' && <Badge variant="success">{t('done')}</Badge>}
                {status?.status === 'error' && <Badge variant="destructive">{locale === 'zh' ? '失败' : 'Failed'}</Badge>}
                {status && !status.done && <Badge variant="processing">{locale === 'zh' ? '进行中' : 'Running'}</Badge>}
              </div>
            </div>
            <Progress value={status?.progress ?? 0} />
            <div className="text-sm text-slate-700">{status?.stage || t('taskCreated')}</div>
            {status?.message && <div className="text-xs text-muted-foreground">{status.message}</div>}
          </div>
        )}

        {videoUrl && (
          <div className="space-y-3 rounded-lg border bg-slate-50 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-medium">{t('generationResult')}</h3>
                <p className="text-sm text-muted-foreground">
                  {locale === 'zh' ? '已返回最终视频结果。' : 'The final video result is ready.'}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => triggerDownload(videoUrl)}>
                  <Download className="mr-1 h-4 w-4" />
                  {t('download')}
                </Button>
                <Badge variant="success" className="gap-1">
                  <CheckCircle2 className="h-3.5 w-3.5" /> {t('done')}
                </Badge>
              </div>
            </div>
            <video controls src={videoUrl} className="w-full rounded-md bg-black" />
            <div className="rounded-md bg-white p-3 text-xs text-muted-foreground break-all">{result?.video_path}</div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
