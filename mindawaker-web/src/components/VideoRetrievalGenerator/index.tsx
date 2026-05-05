'use client';

import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Download, Loader2, Search, Video } from 'lucide-react';
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
import { useTask, type TaskStatus, type MissingHeadKeywordItem } from '@/hooks/useTask';
import { createVideoRetrievalTask } from '@/hooks/useVideoRetrievalTask';
import type { SettingsDefaults } from '@/hooks/useSettings';

type RetrievalAsset = {
  index: number;
  text?: string;
  source_path?: string;
  media_type?: string;
  score?: number;
  audio_duration?: number;
};

interface VideoRetrievalGeneratorProps {
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

const textStyles = ['温柔', '励志', '科普', '幽默', '严肃', 'math'];

function formatDuration(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  return `${value.toFixed(1)}s`;
}

export default function VideoRetrievalGenerator({ defaults, locale }: VideoRetrievalGeneratorProps) {
  const [theme, setTheme] = useState('');
  const [style, setStyle] = useState('温柔');
  const [textModelName, setTextModelName] = useState(defaults?.default_text_model_name || 'deepseek');
  const [textApiKey, setTextApiKey] = useState(defaults?.default_text_api_key || '');
  const [audioModelName, setAudioModelName] = useState(defaults?.default_audio_model_name || 'azure');
  const [audioApiKey, setAudioApiKey] = useState(defaults?.default_audio_api_key || '');
  const [voice, setVoice] = useState(defaults?.voices?.[0]?.name || 'me2');
  const [annotationRoot, setAnnotationRoot] = useState('');
  const [mediaServiceBaseUrl, setMediaServiceBaseUrl] = useState('http://127.0.0.1:6000');
  const [topKPerLine, setTopKPerLine] = useState('3');
  const [preferMediaType, setPreferMediaType] = useState('auto');
  const [withMediaPrompts, setWithMediaPrompts] = useState(true);
  const [mediaPromptStyle, setMediaPromptStyle] = useState('retrieval_default');
  const [mathBackgroundEnabled, setMathBackgroundEnabled] = useState(true);
  const [didApplyDefaults, setDidApplyDefaults] = useState(false);
  const [taskMeta, setTaskMeta] = useState<{ taskId: string; projectId: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { status, connect, disconnect } = useTask({
    basePath: '/api/video-retrieval',
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

  const mediaTypeOptions = [
    { value: 'auto', label: t('auto') },
    { value: 'video', label: t('videoOnly') },
    { value: 'image', label: t('imageOnly') },
  ];

  const mediaPromptStyleOptions = [
    { value: 'image_default', label: t('mediaPromptStyleImageDefault') },
    { value: 'retrieval_default', label: t('mediaPromptStyleRetrievalDefault') },
  ];

  const handleGenerate = async () => {
    setError(null);
    try {
      const task = await createVideoRetrievalTask({
        theme,
        style,
        language: locale,
        text_model_name: textModelName,
        text_api_key: textApiKey,
        audio_model_name: audioModelName,
        audio_api_key: audioApiKey,
        voice,
        annotation_root: annotationRoot,
        media_service_base_url: mediaServiceBaseUrl,
        top_k_per_line: Number(topKPerLine) || 3,
        prefer_media_type: preferMediaType,
        with_media_prompts: withMediaPrompts,
        media_prompt_style: mediaPromptStyle,
        math_background_enabled: mathBackgroundEnabled,
      });
      setTaskMeta({ taskId: task.task_id, projectId: task.project_id });
      connect(task.task_id);
    } catch (err: any) {
      setError(err.message || (locale === 'zh' ? '视频检索生成失败' : 'Failed to generate retrieval video'));
    }
  };

  const result = status?.result as (TaskStatus['result'] & {
    background_assets?: RetrievalAsset[];
    retrieval_items?: unknown[];
    missing_head_keywords?: MissingHeadKeywordItem[];
  }) | null;

  const videoUrl = useMemo(() => getAssetUrl(result?.video_path), [result?.video_path]);
  const lines = result?.lines || [];
  const prompts = result?.prompts || [];
  const assets = (result?.background_assets || []) as RetrievalAsset[];
  const missingHeadKeywords = result?.missing_head_keywords || [];

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <Search className="h-5 w-5 text-emerald-500" />
          {t('videoRetrievalTitle')}
        </CardTitle>
        <CardDescription>{t('videoRetrievalDesc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="retrieval-theme">{t('theme')}</Label>
          <Input
            id="retrieval-theme"
            placeholder={locale === 'zh' ? '例如：春天里的城市公园' : 'e.g. city park in spring'}
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
          <Label htmlFor="retrieval-text-key">{t('textApiKey')}</Label>
          <Input
            id="retrieval-text-key"
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
            <Label htmlFor="retrieval-voice">{t('voice')}</Label>
            <Input
              id="retrieval-voice"
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              placeholder={locale === 'zh' ? '例如：me2 / alloy' : 'e.g. me2 / alloy'}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="retrieval-audio-key">{t('audioApiKey')}</Label>
          <Input
            id="retrieval-audio-key"
            type="password"
            value={audioApiKey}
            onChange={(e) => setAudioApiKey(e.target.value)}
            placeholder={locale === 'zh' ? '输入音频模型 API Key' : 'Enter audio model API key'}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="annotation-root">{t('annotationRoot')}</Label>
            <Input
              id="annotation-root"
              value={annotationRoot}
              onChange={(e) => setAnnotationRoot(e.target.value)}
              placeholder={locale === 'zh' ? '例如：E:/dataset/annotations' : 'e.g. E:/dataset/annotations'}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="media-service-url">{t('mediaServiceUrl')}</Label>
            <Input id="media-service-url" value={mediaServiceBaseUrl} onChange={(e) => setMediaServiceBaseUrl(e.target.value)} placeholder="http://127.0.0.1:6000" />
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
            <input type="checkbox" checked={withMediaPrompts} onChange={(e) => setWithMediaPrompts(e.target.checked)} />
            {t('enableMediaPrompts')}
          </label>
          <div className="space-y-2">
            <Label>{t('mediaPromptStyle')}</Label>
            <Select value={mediaPromptStyle} onValueChange={setMediaPromptStyle}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {mediaPromptStyleOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="space-y-2">
            <Label htmlFor="top-k-per-line">{t('topKPerLine')}</Label>
            <Input id="top-k-per-line" type="number" min="1" max="10" value={topKPerLine} onChange={(e) => setTopKPerLine(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>{t('mediaPreference')}</Label>
            <Select value={preferMediaType} onValueChange={setPreferMediaType}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {mediaTypeOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <label className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
            <input type="checkbox" checked={mathBackgroundEnabled} onChange={(e) => setMathBackgroundEnabled(e.target.checked)} />
            {t('allowMathBackground')}
          </label>
        </div>

        <Button
          onClick={handleGenerate}
          disabled={!theme || !textApiKey || !audioApiKey || !annotationRoot}
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
                  {locale === 'zh' ? '文本生成 → 音频生成 → 素材检索 → 视频拼装' : 'Text generation → Audio generation → Asset retrieval → Video assembly'}
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

        {status?.status === 'error' && missingHeadKeywords.length > 0 && (
          <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-amber-900">{locale === 'zh' ? '缺失素材关键词' : 'Missing asset keywords'}</h3>
              <Badge variant="secondary">{locale === 'zh' ? `${missingHeadKeywords.length} 句` : `${missingHeadKeywords.length} lines`}</Badge>
            </div>
            <p className="text-sm text-amber-800">
              {locale === 'zh'
                ? '以下文案未检索到素材，请补充或改写关键词后重试。'
                : 'No assets were found for the lines below. Add or rewrite keywords and retry.'}
            </p>
            <div className="space-y-2">
              {missingHeadKeywords.map((item) => (
                <div key={`${item.index}-${item.text || ''}`} className="rounded-md bg-white p-3 text-sm text-slate-700">
                  <div className="mb-2 flex items-center gap-2">
                    <Badge variant="outline">#{item.index + 1}</Badge>
                    <span className="font-medium">{item.text || (locale === 'zh' ? '（无文案）' : '(empty text)')}</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(item.head_keywords || []).length > 0 ? (
                      item.head_keywords?.map((keyword) => (
                        <Badge key={`${item.index}-${keyword}`} variant="secondary">{keyword}</Badge>
                      ))
                    ) : (
                      <span className="text-xs text-muted-foreground">{locale === 'zh' ? '未提取到 head 关键词' : 'No head keywords extracted'}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {videoUrl && (
          <div className="space-y-3 rounded-lg border bg-slate-50 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-medium">{t('generationResult')}</h3>
                <p className="text-sm text-muted-foreground">
                  {locale === 'zh' ? '已返回最终视频与检索背景资产。' : 'Returned the final video and retrieved background assets.'}
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

        {lines.length > 0 && (
          <div className="space-y-3 rounded-lg border bg-slate-50 p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">{locale === 'zh' ? '分句结果' : 'Split lines'}</h3>
              <Badge variant="secondary">{locale === 'zh' ? `${lines.length} 句` : `${lines.length} lines`}</Badge>
            </div>
            <div className="space-y-2">
              {lines.map((line, index) => (
                <div key={`${index}-${line.slice(0, 12)}`} className="rounded-md bg-white p-3 text-sm text-slate-700">
                  {index + 1}. {line}
                </div>
              ))}
            </div>
          </div>
        )}

        {prompts.length > 0 && (
          <div className="space-y-3 rounded-lg border bg-slate-50 p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">{t('attachedMediaPrompts')}</h3>
              <Badge variant="secondary">{locale === 'zh' ? `${prompts.length} 条` : `${prompts.length} prompts`}</Badge>
            </div>
            <div className="space-y-2">
              {prompts.map((prompt, index) => (
                <div key={`${index}-${String(prompt).slice(0, 12)}`} className="rounded-md bg-white p-3 text-sm text-slate-700">
                  {index + 1}. {prompt}
                </div>
              ))}
            </div>
          </div>
        )}

        {assets.length > 0 && (
          <div className="space-y-3 rounded-lg border bg-slate-50 p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">{locale === 'zh' ? '背景素材命中' : 'Matched background assets'}</h3>
              <Badge variant="secondary">{locale === 'zh' ? `${assets.length} 段` : `${assets.length} items`}</Badge>
            </div>
            <div className="space-y-3">
              {assets.map((asset) => (
                <div key={`${asset.index}-${asset.source_path || asset.text || 'asset'}`} className="rounded-md bg-white p-3 text-sm text-slate-700">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">#{asset.index + 1}</Badge>
                    <Badge variant="secondary">{asset.media_type || 'unknown'}</Badge>
                    <Badge variant="outline">{formatDuration(asset.audio_duration)}</Badge>
                    <Badge variant="outline">score {(asset.score ?? 0).toFixed(3)}</Badge>
                  </div>
                  <div className="mt-2 whitespace-pre-wrap">{asset.text || '—'}</div>
                  <div className="mt-2 break-all text-xs text-muted-foreground">{asset.source_path || (locale === 'zh' ? '未返回 source_path' : 'source_path not returned')}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
