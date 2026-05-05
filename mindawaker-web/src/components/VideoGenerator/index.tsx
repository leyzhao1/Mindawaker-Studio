'use client';

import { useState, useCallback, ChangeEvent, useEffect } from 'react';
import { Play, Pause, RotateCcw, CheckCircle2, AlertCircle, Loader2, Upload, X, Download, Mic2, Wand2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  useTask,
  applyRedrawSelection,
  createVideoTask,
  rebuildProject,
  rebuildClips,
  concatClips,
  saveProject,
  createEmptyVideoConfig,
  getVideoConfigFromSnapshot,
  getVideoStateFromLoadResponse,
  mergeVideoConfig,
  type AudioItemConfig,
  type ImageItemConfig,
  type VideoConfig,
  type VideoConfigDefaults,
  type VideoGeneratorState,
} from '@/hooks/useTask';
import { getStyleLabel, translate, type Locale } from '@/lib/i18n';

const isStoryStyle = (style?: string) => style === 'story';

type AssetTab = 'images' | 'audios' | 'clips';

import type { SettingsDefaults } from '@/hooks/useSettings';

function toVideoDefaults(defaults?: SettingsDefaults | null): VideoConfigDefaults | undefined {
  if (!defaults) return undefined;
  return defaults;
}

function applyDefaultVideoConfig(config: VideoConfig, defaults?: SettingsDefaults | null): VideoConfig {
  if (!defaults) return config;
  return {
    ...config,
    text_model_name: config.text_model_name || defaults.default_text_model_name || 'deepseek',
    text_api_key: config.text_api_key || defaults.default_text_api_key || '',
    image_model_name: config.image_model_name || defaults.default_image_model_name || 'flux',
    image_api_key: config.image_api_key || defaults.default_image_api_key || '',
    audio_model_name: config.audio_model_name || defaults.default_audio_model_name || 'azure',
    audio_api_key: config.audio_api_key || defaults.default_audio_api_key || '',
    voice: config.voice || defaults.voices?.[0]?.name || 'me2',
  };
}


interface VideoGeneratorProps {
  initialState?: VideoGeneratorState | null;
  onProjectChange?: (projectId: string | null) => void;
  defaults?: SettingsDefaults | null;
  locale?: Locale;
}

function formatDurationLabel(duration?: number) {
  if (typeof duration !== 'number' || Number.isNaN(duration)) return '--';
  return `${duration.toFixed(1)}s`;
}

function formatHistoryTime(locale: Locale, value?: number) {
  if (!value) return locale === 'zh' ? '刚刚' : 'Just now';
  return new Date(value * 1000).toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en', { hour: '2-digit', minute: '2-digit' });
}


























































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































import { generateAudio } from '@/hooks/useAudioGeneration';
import { generateImage } from '@/hooks/useImageGeneration';
import { getAssetUrl, triggerDownload } from '@/lib/generated-files';

const stepKeys = [
  { id: 'text', labelKey: 'videoStepText', descriptionKey: 'videoStepTextDesc' },
  { id: 'audio', labelKey: 'videoStepAudio', descriptionKey: 'videoStepAudioDesc' },
  { id: 'image', labelKey: 'videoStepImage', descriptionKey: 'videoStepImageDesc' },
  { id: 'video', labelKey: 'videoStepClip', descriptionKey: 'videoStepClipDesc' },
  { id: 'concat', labelKey: 'videoStepConcat', descriptionKey: 'videoStepConcatDesc' },
] as const;

const textModels = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'openai', label: 'OpenAI GPT' },
];

const imageModels = [
  { value: 'flux', label: 'Flux' },
  { value: 'jimeng', label: '即梦' },
  { value: 'mw_3d_guided', label: '3D guided' },
  { value: 'openai', label: 'OpenAI DALL-E' },
  { value: 'sdxl', label: 'Stable Diffusion XL' },
];

const audioModels = [
  { value: 'azure', label: 'Azure TTS' },
  { value: 'auralis', label: 'Auralis' },
  { value: 'microsoft', label: 'Microsoft TTS' },
];

export default function VideoGenerator({ initialState, onProjectChange, defaults, locale = 'zh' }: VideoGeneratorProps = {}) {
  const t = useCallback(
    (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate(locale, key, vars),
    [locale],
  );

  const steps = stepKeys.map((step) => ({
    id: step.id,
    label: t(step.labelKey),
    description: t(step.descriptionKey),
  }));

  const [config, setConfig] = useState<VideoConfig>(() =>
    mergeVideoConfig(createEmptyVideoConfig(toVideoDefaults(defaults)), initialState?.config)
  );

  const requiredFieldLabels = [
    !config.theme && !config.article ? t('themeOrUploadDoc') : null,
    !config.text_api_key ? t('textApiKey') : null,
    !config.image_api_key ? t('imageApiKey') : null,
    !config.audio_api_key ? t('audioApiKey') : null,
  ].filter(Boolean) as string[];
  const [didApplyDefaults, setDidApplyDefaults] = useState(false);

  const [taskId, setTaskId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(initialState?.projectId ?? null);
  const [showResult, setShowResult] = useState(Boolean(initialState?.status?.result?.video_path));
  const [fileName, setFileName] = useState<string>('');
  const [fileError, setFileError] = useState<string>('');
  const [isSaving, setIsSaving] = useState(false);
  const [isRebuilding, setIsRebuilding] = useState(false);
  const [isRebuildingClips, setIsRebuildingClips] = useState(false);
  const [isConcatingClips, setIsConcatingClips] = useState(false);
  const [isApplyingUpdate, setIsApplyingUpdate] = useState(false);
  const [manualStatus, setManualStatus] = useState<VideoGeneratorState['status']>(initialState?.status ?? null);
  const [redrawingImageIndex, setRedrawingImageIndex] = useState<number | null>(null);
  const [redrawingAudioIndex, setRedrawingAudioIndex] = useState<number | null>(null);
  const [expandedImageSettingsIndex, setExpandedImageSettingsIndex] = useState<number | null>(null);
  const [expandedAudioSettingsIndex, setExpandedAudioSettingsIndex] = useState<number | null>(null);
  const [imageDraftConfigs, setImageDraftConfigs] = useState<Record<number, ImageItemConfig>>({});
  const [audioDraftConfigs, setAudioDraftConfigs] = useState<Record<number, AudioItemConfig>>({});
  const [selectedImageHistory, setSelectedImageHistory] = useState<Record<number, number>>({});
  const [selectedAudioHistory, setSelectedAudioHistory] = useState<Record<number, number>>({});
  const [lastAppliedImageHistory, setLastAppliedImageHistory] = useState<Record<number, number>>({});
  const [lastAppliedAudioHistory, setLastAppliedAudioHistory] = useState<Record<number, number>>({});
  const [hasPendingSelectionChanges, setHasPendingSelectionChanges] = useState(false);
  const [assetTab, setAssetTab] = useState<AssetTab>(initialState?.status?.result?.clips?.length ? 'clips' : (initialState?.status?.result?.images?.length ? 'images' : 'audios'));

  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleProgress = useCallback((status: any) => {
    console.log('Progress:', status);
  }, []);

  const handleComplete = useCallback((completedStatus?: any) => {
    const pipelineStatus = completedStatus?.pipeline_status;
      if (pipelineStatus === 'in_video_concat' || completedStatus?.result?.video_path) {
      setAssetTab('clips');
      setShowResult(true);
      return;
    }
    if (pipelineStatus === 'in_video_rebuild' || completedStatus?.result?.clips) {
      setAssetTab('clips');
      setShowResult(false);
      return;
    }
    setShowResult(true);
  }, []);

  const handleError = useCallback((error: string) => {
    console.error('Task error:', error);
    setErrorMessage(error);
  }, []);

  const { status, connect, cancel } = useTask({
    onProgress: handleProgress,
    onComplete: handleComplete,
    onError: handleError,
  });

  const currentStatus = status ?? manualStatus;
  const videoUrl = getAssetUrl(currentStatus?.result?.video_path);
  const imageHistoryItems = currentStatus?.result?.image_redraw_history ?? [];
  const audioHistoryItems = currentStatus?.result?.audio_redraw_history ?? [];
  const statusForRender = currentStatus;
  const currentProjectId = currentStatus?.project_id || projectId || null;
  const result = statusForRender?.result;
  const imageItems = result?.images ?? [];
  const audioItems = result?.audios ?? [];
  const clipItems = result?.clips ?? [];
  const dirtyClipCount = clipItems.filter((item) => item?.dirty).length;
  const promptItems = result?.prompts ?? [];
  const lineItems = result?.lines ?? [];
  const durationItems = result?.durations ?? [];
  const imageConfigItems = result?.images_configs ?? [];
  const audioConfigItems = result?.audios_configs ?? [];
  const isRunning = statusForRender?.status === 'running' || statusForRender?.status === 'pending';
  const canRebuildClips = !!currentProjectId && dirtyClipCount > 0 && !isRunning;
  const canConcatClips = !!currentProjectId && clipItems.length > 0 && dirtyClipCount === 0 && !isRunning;

  useEffect(() => {
    if (!initialState) return;
    setProjectId(initialState.projectId);
    setConfig(mergeVideoConfig(createEmptyVideoConfig(toVideoDefaults(defaults)), initialState.config));
    setManualStatus(initialState.status);
    setShowResult(Boolean(initialState.status?.result?.video_path));
  }, [defaults, initialState]);

  useEffect(() => {
    if (!defaults || didApplyDefaults || initialState?.config) return;
    setConfig((current) => applyDefaultVideoConfig(current, defaults));
    setDidApplyDefaults(true);
  }, [defaults, didApplyDefaults, initialState?.config]);

  useEffect(() => {
    const imageHistory = currentStatus?.result?.image_redraw_history ?? [];
    const audioHistory = currentStatus?.result?.audio_redraw_history ?? [];
    const nextImageConfigs: Record<number, ImageItemConfig> = {};
    const nextAudioConfigs: Record<number, AudioItemConfig> = {};

    const nextImageSelection: Record<number, number> = {};
    imageHistory.forEach((items, index) => {
      const selectedIndex = items.findIndex((item) => item?.is_current);
      nextImageSelection[index] = selectedIndex >= 0 ? selectedIndex : 0;
    });

    const nextAudioSelection: Record<number, number> = {};
    audioHistory.forEach((items, index) => {
      const selectedIndex = items.findIndex((item) => item?.is_current);
      nextAudioSelection[index] = selectedIndex >= 0 ? selectedIndex : 0;
    });

    (currentStatus?.result?.images_configs ?? []).forEach((item, index) => {
      nextImageConfigs[index] = {
        image_model_name: item?.image_model_name || config.image_model_name,
        image_api_key: item?.image_api_key || config.image_api_key,
        prompt: item?.prompt || item?.text || currentStatus?.result?.prompts?.[index] || '',
        text: item?.text || item?.prompt || currentStatus?.result?.prompts?.[index] || '',
        n: item?.n || 1,
        size: item?.size || config.size,
      };
    });

    (currentStatus?.result?.audios_configs ?? []).forEach((item, index) => {
      nextAudioConfigs[index] = {
        audio_model_name: item?.audio_model_name || config.audio_model_name,
        audio_api_key: item?.audio_api_key || config.audio_api_key,
        text: item?.text || currentStatus?.result?.lines?.[index] || '',
        voice: item?.voice || config.voice,
      };
    });

    setImageDraftConfigs(nextImageConfigs);
    setAudioDraftConfigs(nextAudioConfigs);
    setSelectedImageHistory(nextImageSelection);
    setSelectedAudioHistory(nextAudioSelection);
    setLastAppliedImageHistory(nextImageSelection);
    setLastAppliedAudioHistory(nextAudioSelection);
    setHasPendingSelectionChanges(false);
  }, [config.audio_api_key, config.audio_model_name, config.image_api_key, config.image_model_name, config.size, config.voice, currentStatus]);

  useEffect(() => {
    const imageChanged = Object.keys(selectedImageHistory).some((key) => selectedImageHistory[Number(key)] !== lastAppliedImageHistory[Number(key)]);
    const audioChanged = Object.keys(selectedAudioHistory).some((key) => selectedAudioHistory[Number(key)] !== lastAppliedAudioHistory[Number(key)]);
    setHasPendingSelectionChanges(imageChanged || audioChanged);
  }, [lastAppliedAudioHistory, lastAppliedImageHistory, selectedAudioHistory, selectedImageHistory]);


  useEffect(() => {
    onProjectChange?.(projectId);
  }, [onProjectChange, projectId]);


  useEffect(() => {
    if (currentStatus?.project_id) {
      setProjectId(currentStatus.project_id);
    }
  }, [currentStatus?.project_id]);

  useEffect(() => {
    if (status) {
      setManualStatus(status);
    }
  }, [status]);

  const getErrorMessage = useCallback(
    (error: unknown, key: Parameters<typeof translate>[1]) => {
      const message = error && typeof error === 'object' && 'message' in error ? String((error as { message?: string }).message || '') : '';
      return message || t(key);
    },
    [t],
  );

  const getDirtyClipLabel = useCallback(
    (count: number) => t('dirtyClipsCount', { count }),
    [t],
  );

  const getCandidateLabel = useCallback(
    (index: number) => (index === 0 ? t('currentVersion') : t('candidateVersion', { index })),
    [t],
  );

  const getRequiredFieldMessage = useCallback(() => requiredFieldLabels.join(locale === 'zh' ? '、' : ', '), [locale, requiredFieldLabels]);

  const formatImageCountLabel = useCallback(
    (count: number) => (locale === 'zh' ? `${count} 张` : String(count)),
    [locale],
  );

  const formatCharacterCount = useCallback(
    (count: number) => (locale === 'zh' ? `${count} 字符` : `${count} characters`),
    [locale],
  );

  const formatImageMeta = useCallback(
    (modelName?: string, size?: string) => (locale === 'zh' ? `模型：${modelName || '-'} · 尺寸：${size || '-'}` : `Model: ${modelName || '-'} · Size: ${size || '-'}`),
    [locale],
  );

  const formatAudioMeta = useCallback(
    (modelName?: string, voiceName?: string) => (locale === 'zh' ? `模型：${modelName || '-'} · 音色：${voiceName || '-'}` : `Model: ${modelName || '-'} · Voice: ${voiceName || '-'}`),
    [locale],
  );

  useEffect(() => {
    if (initialState?.status?.id && (initialState.status.status === 'pending' || initialState.status.status === 'running')) {
      setTaskId(initialState.status.id);
      connect(initialState.status.id);
    }
  }, [connect, initialState]);

  const handleFileUpload = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setFileError('');
    setFileName(file.name);

    if (!file.name.endsWith('.txt')) {
      setFileError(t('uploadTxtOnlyError'));
      return;
    }

    if (file.size > 50 * 1024) {
      setFileError(t('fileTooLargeError'));
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;

      if (content.length > 2400) {
        setFileError(t('articleTooLongError'));
        return;
      }

      setConfig((prev: VideoConfig) => ({ ...prev, article: content }));
    };

    reader.onerror = () => {
      setFileError(t('fileReadFailedError'));
    };

    reader.readAsText(file);
  }, [t]);

  const handleClearFile = useCallback(() => {
    setConfig((prev: VideoConfig) => ({ ...prev, article: '' }));
    setFileName('');
    setFileError('');
  }, []);

  const resetGenerator = useCallback(() => {
    setTaskId(null);
    setShowResult(false);
    setManualStatus(null);
    setProjectId(null);
    setConfig(createEmptyVideoConfig(toVideoDefaults(defaults)));
    setFileName('');
    setFileError('');
    setErrorMessage(null);
  }, []);

  const handleSaveProject = useCallback(async () => {
    if (!currentProjectId) return;
    setIsSaving(true);
    setErrorMessage(null);
    try {
      await saveProject(currentProjectId);
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'saveProjectFailed'));
    } finally {
      setIsSaving(false);
    }
  }, [currentProjectId, getErrorMessage]);

  const handleRebuild = useCallback(async () => {
    if (!currentProjectId) return;
    setIsRebuilding(true);
    setErrorMessage(null);
    setShowResult(false);
    try {
      const result = await rebuildProject(currentProjectId);
      setTaskId(result.task_id);
      connect(result.task_id);
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'rebuildProjectFailed'));
    } finally {
      setIsRebuilding(false);
    }
  }, [connect, currentProjectId, getErrorMessage]);

  const handleApplyUpdate = useCallback(async () => {
    if (!currentProjectId || !hasPendingSelectionChanges) return;
    setIsApplyingUpdate(true);
    setErrorMessage(null);
    try {
      const imagePayload = Object.fromEntries(
        Object.entries(selectedImageHistory).filter(([key, value]) => lastAppliedImageHistory[Number(key)] !== value),
      );
      const audioPayload = Object.fromEntries(
        Object.entries(selectedAudioHistory).filter(([key, value]) => lastAppliedAudioHistory[Number(key)] !== value),
      );
      const response = await applyRedrawSelection(currentProjectId, {
        image_selected_history: imagePayload,
        audio_selected_history: audioPayload,
      });
      const nextState = mergeVideoConfig(createEmptyVideoConfig(), getVideoConfigFromSnapshot(response.project));
      setConfig(nextState);
      setManualStatus(getVideoStateFromLoadResponse({
        project_id: response.project_id,
        loaded: true,
        project: response.project,
      }).status);
      setProjectId(response.project_id);
      setLastAppliedImageHistory(selectedImageHistory);
      setLastAppliedAudioHistory(selectedAudioHistory);
      setHasPendingSelectionChanges(false);
      setShowResult(false);
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'updateAssetsFailed'));
    } finally {
      setIsApplyingUpdate(false);
    }
  }, [currentProjectId, getErrorMessage, hasPendingSelectionChanges, lastAppliedAudioHistory, lastAppliedImageHistory, selectedAudioHistory, selectedImageHistory]);

  const handleRebuildClips = useCallback(async () => {
    if (!currentProjectId) return;
    setIsRebuildingClips(true);
    setErrorMessage(null);
    setShowResult(false);
    try {
      const result = await rebuildClips(currentProjectId);
      setTaskId(result.task_id);
      setAssetTab('clips');
      connect(result.task_id);
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'rebuildClipsFailed'));
    } finally {
      setIsRebuildingClips(false);
    }
  }, [connect, currentProjectId, getErrorMessage]);

  const handleConcatClips = useCallback(async () => {
    if (!currentProjectId) return;
    setIsConcatingClips(true);
    setErrorMessage(null);
    try {
      const result = await concatClips(currentProjectId);
      setTaskId(result.task_id);
      setAssetTab('clips');
      connect(result.task_id);
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'concatClipsFailed'));
    } finally {
      setIsConcatingClips(false);
    }
  }, [connect, currentProjectId, getErrorMessage]);


  const handleStart = async () => {
    setErrorMessage(null);
    setShowResult(false);
    try {
      console.log('Starting task with config:', config);
      const result = await createVideoTask(config, projectId || undefined);
      console.log('Task created:', result);
      setProjectId(result.project_id);
      setTaskId(result.task_id);
      connect(result.task_id);
    } catch (error: any) {
      console.error('Failed to create task:', error);
      setErrorMessage(getErrorMessage(error, 'createTaskFailed'));
    }
  };

  const handleCancel = async () => {
    if (taskId) {
      await cancel(taskId);
      if (currentProjectId) {
        await handleSaveProject();
      }
    }
  };

  const getCurrentStepId = () => {
    if (!statusForRender) return null;

    const pipelineStatus = statusForRender.pipeline_status;
    if (pipelineStatus === 'in_text_progress') return 'text';
    if (pipelineStatus === 'in_audio_progress') return 'audio';
    if (pipelineStatus === 'in_image_progress') return 'image';
    if (pipelineStatus === 'in_video_progress') return 'video';
    if (pipelineStatus === 'in_video_rebuild') return 'video';
    if (pipelineStatus === 'in_video_concat') return 'concat';

    const stageText = `${statusForRender.stage || ''} ${statusForRender.message || ''}`.toLowerCase();

    if (stageText.includes('提示词') || stageText.includes('文案')) return 'text';
    if (stageText.includes('配音') || stageText.includes('音频')) return 'audio';
    if (stageText.includes('图像')) return 'image';
    if (stageText.includes('拼接') || stageText.includes('整片')) return 'concat';
    if (stageText.includes('字幕') || stageText.includes('视频')) return 'video';

    if (statusForRender.progress >= 100) return 'concat';
    if (statusForRender.progress >= 90) return 'concat';
    if (statusForRender.progress >= 75) return 'video';
    if (statusForRender.progress >= 50) return 'image';
    if (statusForRender.progress > 0) return 'text';

    return null;
  };

  const getStepStatus = (stepId: string) => {
    if (!statusForRender) return 'pending';

    if (statusForRender.status === 'completed') return 'completed';

    const currentStepId = getCurrentStepId();
    const stepIndex = steps.findIndex((s) => s.id === stepId);
    const currentIndex = steps.findIndex((s) => s.id === currentStepId);

    if (currentIndex === -1) return 'pending';
    if (stepIndex < currentIndex) return 'completed';
    if (stepIndex === currentIndex) return 'processing';
    return 'pending';
  };

  const handleImageDraftChange = useCallback((index: number, updates: Partial<ImageItemConfig>) => {
    setImageDraftConfigs((prev) => ({
      ...prev,
      [index]: {
        ...(prev[index] || {}),
        ...updates,
      },
    }));
  }, []);

  const handleAudioDraftChange = useCallback((index: number, updates: Partial<AudioItemConfig>) => {
    setAudioDraftConfigs((prev) => ({
      ...prev,
      [index]: {
        ...(prev[index] || {}),
        ...updates,
      },
    }));
  }, []);

  const handleResetImageDraft = useCallback((index: number) => {
    const imageConfig = imageConfigItems[index] as ImageItemConfig | undefined;
    const prompt = promptItems[index] || imageConfig?.prompt || imageConfig?.text || '';
    setImageDraftConfigs((prev) => ({
      ...prev,
      [index]: {
        image_model_name: config.image_model_name,
        image_api_key: config.image_api_key,
        prompt,
        text: prompt,
        n: config.n || 1,
        size: config.size,
      },
    }));
  }, [config.image_api_key, config.image_model_name, config.n, config.size, imageConfigItems, promptItems]);

  const handleResetAudioDraft = useCallback((index: number) => {
    const audioConfig = audioConfigItems[index] as AudioItemConfig | undefined;
    const text = lineItems[index] || audioConfig?.text || '';
    setAudioDraftConfigs((prev) => ({
      ...prev,
      [index]: {
        audio_model_name: config.audio_model_name,
        audio_api_key: config.audio_api_key,
        text,
        voice: config.voice,
      },
    }));
  }, [audioConfigItems, config.audio_api_key, config.audio_model_name, config.voice, lineItems]);

  const handleRedrawImage = useCallback(async (index: number) => {
    if (!currentProjectId) return;
    const imageConfig = imageConfigItems[index] as ImageItemConfig | undefined;
    const draft = imageDraftConfigs[index] || {};
    const prompt = draft.prompt || draft.text || promptItems[index] || imageConfig?.prompt || imageConfig?.text;
    const apiKey = draft.image_api_key || imageConfig?.image_api_key || config.image_api_key;
    const modelName = draft.image_model_name || imageConfig?.image_model_name || config.image_model_name;
    const size = draft.size || imageConfig?.size || config.size;
    const n = draft.n || imageConfig?.n || 1;
    if (!prompt || !apiKey || !modelName) {
      setErrorMessage(t('missingImageRedrawParams'));
      return;
    }

    setRedrawingImageIndex(index);
    setErrorMessage(null);
    try {
      const response = await generateImage(
        {
          prompt,
          image_api_key: apiKey,
          image_model_name: modelName,
          size,
          n,
          language: locale,
        },
        { projectId: currentProjectId, index },
      );

      const nextImagePath = response.image_paths?.[0];
      if (!nextImagePath) {
        throw new Error(t('imageRedrawNoResult'));
      }

      await handleSaveProject();
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'imageRedrawFailed'));
    } finally {
      setRedrawingImageIndex(null);
    }
  }, [config.image_api_key, config.image_model_name, config.size, currentProjectId, getErrorMessage, handleSaveProject, imageConfigItems, imageDraftConfigs, promptItems, t]);

  const handleRedrawAudio = useCallback(async (index: number) => {
    if (!currentProjectId) return;
    const audioConfig = audioConfigItems[index] as AudioItemConfig | undefined;
    const draft = audioDraftConfigs[index] || {};
    const text = lineItems[index] || audioConfig?.text;
    const apiKey = draft.audio_api_key || audioConfig?.audio_api_key || config.audio_api_key;
    const modelName = draft.audio_model_name || audioConfig?.audio_model_name || config.audio_model_name;
    const voice = draft.voice || audioConfig?.voice || config.voice;
    if (!text || !apiKey || !modelName) {
      setErrorMessage(t('missingAudioRedrawParams'));
      return;
    }

    setRedrawingAudioIndex(index);
    setErrorMessage(null);
    try {
      const response = await generateAudio(
        {
          text,
          audio_api_key: apiKey,
          audio_model_name: modelName,
          voice,
          language: locale,
        },
        { projectId: currentProjectId, index },
      );

      if (!response.audio_path) {
        throw new Error(t('audioRedrawNoResult'));
      }

      await handleSaveProject();
    } catch (error: any) {
      setErrorMessage(getErrorMessage(error, 'audioRedrawFailed'));
    } finally {
      setRedrawingAudioIndex(null);
    }
  }, [audioConfigItems, audioDraftConfigs, config.audio_api_key, config.audio_model_name, config.voice, currentProjectId, getErrorMessage, handleSaveProject, lineItems, t]);

  return (
    <div className="space-y-6">
      {/* Progress Steps */}
      {statusForRender && (
        <Card className="border-blue-100 bg-blue-50/50">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg flex items-center gap-2">
                  {isRunning ? (
                    <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                  ) : statusForRender.status === 'completed' ? (
                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                  ) : statusForRender.status === 'error' ? (
                    <AlertCircle className="w-5 h-5 text-red-500" />
                  ) : null}
                  {t('videoProgress')}
                </CardTitle>
                <CardDescription>{statusForRender.message || statusForRender.stage || t('preparing')}</CardDescription>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-2xl font-bold text-blue-600">{statusForRender.progress}%</span>
                {currentProjectId && (
                  <Badge variant="outline">{t('projectId')}: {currentProjectId}</Badge>
                )}
                {isRunning && (
                  <Button variant="destructive" size="sm" onClick={handleCancel}>
                    <Pause className="w-4 h-4 mr-1" />
                    {t('cancelTask')}
                  </Button>
                )}
                {statusForRender.status === 'completed' && (
                  <Button variant="outline" size="sm" onClick={resetGenerator}>
                    <RotateCcw className="w-4 h-4 mr-1" />
                    {t('createAnother')}
                  </Button>
                )}
                {currentProjectId && !isRunning && (
                  <Button variant="outline" size="sm" onClick={handleSaveProject} disabled={isSaving}>
                    {isSaving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null}
                    {t('saveProject')}
                  </Button>
                )}
                {currentProjectId && !isRunning && (
                  <Button variant="default" size="sm" onClick={handleApplyUpdate} disabled={isApplyingUpdate || !hasPendingSelectionChanges}>
                    {isApplyingUpdate ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null}
                    {t('updateAssets')}
                  </Button>
                )}
                {currentProjectId && statusForRender.status === 'error' && (
                  <Button variant="default" size="sm" onClick={handleRebuild} disabled={isRebuilding}>
                    {isRebuilding ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <RotateCcw className="w-4 h-4 mr-1" />}
                    {t('rebuildProject')}
                  </Button>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={statusForRender.progress} variant="gradient" className="h-3" />
            <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
              {steps.map((step) => {
                const stepStatus = getStepStatus(step.id);
                return (
                  <div
                    key={step.id}
                    className={`p-3 rounded-lg border transition-all ${
                      stepStatus === 'completed'
                        ? 'bg-green-50 border-green-200'
                        : stepStatus === 'processing'
                        ? 'bg-blue-50 border-blue-200 ring-2 ring-blue-100'
                        : 'bg-white border-gray-100'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      {stepStatus === 'completed' ? (
                        <CheckCircle2 className="w-4 h-4 text-green-500" />
                      ) : stepStatus === 'processing' ? (
                        <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                      ) : (
                        <div className="w-4 h-4 rounded-full border-2 border-gray-200" />
                      )}
                      <span
                        className={`font-medium text-sm ${
                          stepStatus === 'processing' ? 'text-blue-700' : 'text-gray-700'
                        }`}
                      >
                        {step.label}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">{step.description}</p>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Configuration Form */}
      {!statusForRender && (
        <Tabs defaultValue="content" className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="content">{t('contentSettings')}</TabsTrigger>
            <TabsTrigger value="text">{t('textModel')}</TabsTrigger>
            <TabsTrigger value="audio">{t('audioModel')}</TabsTrigger>
            <TabsTrigger value="image">{t('imageModel')}</TabsTrigger>
          </TabsList>

          <TabsContent value="content" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>{t('videoContentTitle')}</CardTitle>
                <CardDescription>{t('videoContentDesc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="theme" className="flex items-center gap-1">
                    {t('theme')}
                    {!config.article && <span className="text-red-500">*</span>}
                    {!config.theme && !config.article && (
                      <span className="text-xs text-red-500 font-normal">({t('required')})</span>
                    )}
                  </Label>
                  <Input
                    id="theme"
                    placeholder={t('videoThemePlaceholder')}
                    value={config.theme}
                    onChange={(e) => setConfig({ ...config, theme: e.target.value })}
                    disabled={!!config.article}
                    className={
                      !config.theme && !config.article ? "border-red-300 focus:border-red-500" :
                      config.article ? "bg-gray-50 text-gray-500 cursor-not-allowed" : ""
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="style">{t('writingStyle')}</Label>
                  <Select
                    value={config.style}
                    onValueChange={(value) => setConfig({ ...config, style: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {['温柔', '励志', '科普', '幽默', '严肃', 'story'].map((item) => (
                        <SelectItem key={item} value={item}>
                          {getStyleLabel(item, locale)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {isStoryStyle(config.style) && (
                  <div className="space-y-2">
                    <Label htmlFor="file-upload" className="flex items-center gap-1">
                      {t('uploadDocumentTxt')}
                    </Label>
                    <div className="border-2 border-dashed border-gray-200 rounded-lg p-4 hover:border-blue-300 transition-colors">
                      <input
                        id="file-upload"
                        type="file"
                        accept=".txt"
                        onChange={handleFileUpload}
                        className="hidden"
                      />
                      <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center gap-2">
                        <div className="w-12 h-12 rounded-full bg-blue-50 flex items-center justify-center">
                          <Upload className="w-6 h-6 text-blue-500" />
                        </div>
                        <div className="text-center">
                          <p className="text-sm font-medium">{t('uploadTxtCta')}</p>
                          <p className="text-xs text-muted-foreground mt-1">{t('uploadTxtHint')}</p>
                        </div>
                      </label>

                      {fileName && (
                        <div className="mt-3 p-3 bg-blue-50 rounded-md flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded bg-blue-100 flex items-center justify-center">
                              <span className="text-xs font-medium text-blue-700">TXT</span>
                            </div>
                            <div>
                              <p className="text-sm font-medium">{fileName}</p>
                              <p className="text-xs text-muted-foreground">
                                {config.article ? formatCharacterCount(config.article.length) : t('unreadContent')}
                              </p>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={handleClearFile}
                            className="p-1 hover:bg-red-100 rounded-full transition-colors"
                          >
                            <X className="w-4 h-4 text-red-500" />
                          </button>
                        </div>
                      )}

                      {fileError && (
                        <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded-md">
                          <p className="text-xs text-red-600">{fileError}</p>
                        </div>
                      )}

                      {config.article && !fileError && (
                        <div className="mt-3 p-2 bg-green-50 border border-green-200 rounded-md">
                          <p className="text-xs text-green-700">✅ {t('documentReadSuccess', { count: config.article.length })}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {config.article && isStoryStyle(config.style) && (
                  <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                    <p className="text-xs text-yellow-700">
                      {t('storyDocumentNotice')}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="text" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>{t('textConfigTitle')}</CardTitle>
                <CardDescription>{t('textConfigDesc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>{t('textModel')}</Label>
                  <Select
                    value={config.text_model_name}
                    onValueChange={(value) => setConfig({ ...config, text_model_name: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {textModels.map((model) => (
                        <SelectItem key={model.value} value={model.value}>
                          {model.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="text-api-key" className="flex items-center gap-1">
                    {t('apiKey')}
                    <span className="text-red-500">*</span>
                    {!config.text_api_key && (
                      <span className="text-xs text-red-500 font-normal">({t('required')})</span>
                    )}
                  </Label>
                  <Input
                    id="text-api-key"
                    type="password"
                    placeholder={t('enterApiKey')}
                    value={config.text_api_key}
                    onChange={(e) => setConfig({ ...config, text_api_key: e.target.value })}
                    className={!config.text_api_key ? "border-red-300 focus:border-red-500" : ""}
                  />
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <label className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                    <input
                      type="checkbox"
                      checked={Boolean(config.with_media_prompts)}
                      onChange={(e) => setConfig({ ...config, with_media_prompts: e.target.checked })}
                    />
                    {t('enableMediaPrompts')}
                  </label>
                  <div className="space-y-2">
                    <Label>{t('mediaPromptStyle')}</Label>
                    <Select
                      value={config.media_prompt_style || 'image_default'}
                      onValueChange={(value) => setConfig({ ...config, media_prompt_style: value })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="image_default">{t('mediaPromptStyleImageDefault')}</SelectItem>
                        <SelectItem value="retrieval_default">{t('mediaPromptStyleRetrievalDefault')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="audio" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>{t('audioConfigTitle')}</CardTitle>
                <CardDescription>{t('audioConfigDesc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>{t('audioModel')}</Label>
                  <Select
                    value={config.audio_model_name}
                    onValueChange={(value) => setConfig({ ...config, audio_model_name: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {audioModels.map((model) => (
                        <SelectItem key={model.value} value={model.value}>
                          {model.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="audio-api-key" className="flex items-center gap-1">
                    {t('apiKey')}
                    <span className="text-red-500">*</span>
                    {!config.audio_api_key && (
                      <span className="text-xs text-red-500 font-normal">({t('required')})</span>
                    )}
                  </Label>
                  <Input
                    id="audio-api-key"
                    type="password"
                    placeholder={t('enterApiKey')}
                    value={config.audio_api_key}
                    onChange={(e) => setConfig({ ...config, audio_api_key: e.target.value })}
                    className={!config.audio_api_key ? "border-red-300 focus:border-red-500" : ""}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="voice">{t('voice')}</Label>
                  <Input
                    id="voice"
                    placeholder={t('voicePlaceholder')}
                    value={config.voice}
                    onChange={(e) => setConfig({ ...config, voice: e.target.value })}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="image" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>{t('imageConfigTitle')}</CardTitle>
                <CardDescription>{t('imageConfigDesc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>{t('imageModel')}</Label>
                  <Select
                    value={config.image_model_name}
                    onValueChange={(value) => setConfig({ ...config, image_model_name: value })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {imageModels.map((model) => (
                        <SelectItem key={model.value} value={model.value}>
                          {model.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="image-api-key" className="flex items-center gap-1">
                    {t('apiKey')}
                    <span className="text-red-500">*</span>
                    {!config.image_api_key && (
                      <span className="text-xs text-red-500 font-normal">({t('required')})</span>
                    )}
                  </Label>
                  <Input
                    id="image-api-key"
                    type="password"
                    placeholder={t('enterApiKey')}
                    value={config.image_api_key}
                    onChange={(e) => setConfig({ ...config, image_api_key: e.target.value })}
                    className={!config.image_api_key ? "border-red-300 focus:border-red-500" : ""}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>{t('imageSize')}</Label>
                    <Select
                      value={config.size}
                      onValueChange={(value) => setConfig({ ...config, size: value })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1024*1024">1024 × 1024</SelectItem>
                        <SelectItem value="1024*720">1024 × 720</SelectItem>
                        <SelectItem value="720*1024">720 × 1024</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>{t('imageCount')}</Label>
                    <Select
                      value={String(config.n)}
                      onValueChange={(value) => setConfig({ ...config, n: Number(value) })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {[1, 2, 4, 8].map((count) => (
                          <SelectItem key={count} value={String(count)}>{formatImageCountLabel(count)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}

      {!!currentProjectId && (!!imageItems.length || !!audioItems.length || !!clipItems.length) && (
        <Card>
          <CardHeader>
            <CardTitle>{t('assetSequence')}</CardTitle>
            <CardDescription>{t('assetSequenceDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs value={assetTab} onValueChange={(value) => setAssetTab(value as AssetTab)} className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="images">{t('imageSequence')}</TabsTrigger>
                <TabsTrigger value="audios">{t('audioSequence')}</TabsTrigger>
                <TabsTrigger value="clips">{t('clips')}</TabsTrigger>
              </TabsList>

              <TabsContent value="images" className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => void handleRebuildClips()} disabled={!canRebuildClips || isRebuildingClips}>
                    {isRebuildingClips ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                    {t('rebuildClipsButton')}
                  </Button>
                  <span className="text-xs text-muted-foreground">{getDirtyClipLabel(dirtyClipCount)}</span>
                </div>
                {imageItems.length === 0 ? (
                  <div className="rounded-md border bg-slate-50 p-4 text-sm text-muted-foreground">{t('noImageAssets')}</div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {imageItems.map((path, index) => {
                      const imageUrl = getAssetUrl(path);
                      const imageConfig = imageConfigItems[index] as ImageItemConfig | undefined;
                      const imageDraft = imageDraftConfigs[index] || imageConfig || {
                        image_model_name: config.image_model_name,
                        image_api_key: config.image_api_key,
                        prompt: promptItems[index] || '',
                        text: promptItems[index] || '',
                        n: config.n || 1,
                        size: config.size,
                      };
                      const prompt = promptItems[index] || imageConfig?.prompt || imageConfig?.text || '-';
                      const isRedrawing = redrawingImageIndex === index;
                      const isSettingsOpen = expandedImageSettingsIndex === index;
                      const history = imageHistoryItems[index] ?? [];
                      const selectedHistoryIndex = selectedImageHistory[index] ?? history.findIndex((item) => item?.is_current) ?? 0;
                      return (
                        <div key={`image-${index}-${path}`} className="space-y-3 rounded-lg border bg-slate-50 p-3">
                          <img src={imageUrl} alt={t('imageLabel', { index: index + 1 })} className="aspect-square w-full rounded-md object-cover bg-white" />
                          <div className="space-y-1">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-sm font-medium">{t('imageLabel', { index: index + 1 })}</span>
                              <Badge variant="outline">{imageConfig?.size || config.size || '-'}</Badge>
                            </div>
                            <p className="line-clamp-3 text-xs text-muted-foreground">{prompt}</p>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <Button size="sm" onClick={() => void handleRedrawImage(index)} disabled={isRedrawing || !(imageDraft.image_api_key || config.image_api_key)}>
                              {isRedrawing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Wand2 className="mr-1 h-4 w-4" />}
                              {t('redrawItem')}
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => setExpandedImageSettingsIndex((current) => current === index ? null : index)}>
                              {t('settings')}
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => handleResetImageDraft(index)}>
                              {t('resetSettings')}
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => triggerDownload(imageUrl)}>
                              <Download className="mr-1 h-4 w-4" />
                              {t('download')}
                            </Button>
                          </div>
                          {isSettingsOpen && (
                            <div className="space-y-3 rounded-md border bg-white p-3">
                              <div className="text-xs font-medium text-muted-foreground">{t('imageItemSettings')}</div>
                              <div className="space-y-2">
                                <Label>{t('imageModel')}</Label>
                                <Select value={imageDraft.image_model_name || config.image_model_name} onValueChange={(value) => handleImageDraftChange(index, { image_model_name: value })}>
                                  <SelectTrigger>
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {imageModels.map((model) => (
                                      <SelectItem key={`image-item-model-${index}-${model.value}`} value={model.value}>
                                        {model.label}
                                      </SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              </div>
                              <div className="space-y-2">
                                <Label>{t('apiKey')}</Label>
                                <Input type="password" value={imageDraft.image_api_key || ''} onChange={(e) => handleImageDraftChange(index, { image_api_key: e.target.value })} placeholder={t('itemImageApiKeyPlaceholder')} />
                              </div>
                              <div className="grid grid-cols-2 gap-3">
                                <div className="space-y-2">
                                  <Label>{t('imageSize')}</Label>
                                  <Select value={imageDraft.size || config.size} onValueChange={(value) => handleImageDraftChange(index, { size: value })}>
                                    <SelectTrigger>
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                      <SelectItem value="1024*1024">1024 × 1024</SelectItem>
                                      <SelectItem value="1024*720">1024 × 720</SelectItem>
                                      <SelectItem value="720*1024">720 × 1024</SelectItem>
                                    </SelectContent>
                                  </Select>
                                </div>
                                <div className="space-y-2">
                                  <Label>{t('imageCount')}</Label>
                                  <Select value={String(imageDraft.n || 1)} onValueChange={(value) => handleImageDraftChange(index, { n: Number(value) })}>
                                    <SelectTrigger>
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                      {[1, 2, 4, 8].map((count) => (
                                        <SelectItem key={`image-item-count-${index}-${count}`} value={String(count)}>{formatImageCountLabel(count)}</SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                </div>
                              </div>
                              <div className="space-y-2">
                                <Label>{t('prompt')}</Label>
                                <Input value={imageDraft.prompt || imageDraft.text || ''} onChange={(e) => handleImageDraftChange(index, { prompt: e.target.value, text: e.target.value })} placeholder={t('itemImagePromptPlaceholder')} />
                              </div>
                            </div>
                          )}
                          {history.length > 0 && (
                            <div className="space-y-2 rounded-md border bg-white p-3">
                              <div className="text-xs font-medium text-muted-foreground">{t('redrawHistory')}</div>
                              <div className="grid gap-2">
                                {history.map((candidate, historyIndex) => {
                                  const candidateUrl = getAssetUrl(candidate.image_path);
                                  return (
                                    <button
                                      key={`image-history-${index}-${historyIndex}`}
                                      type="button"
                                      onClick={() => setSelectedImageHistory((prev) => ({ ...prev, [index]: historyIndex }))}
                                      className={`flex items-center gap-3 rounded-md border p-2 text-left ${selectedHistoryIndex === historyIndex ? 'border-blue-500 bg-blue-50' : 'border-slate-200 bg-slate-50'}`}
                                    >
                                      <img src={candidateUrl} alt={getCandidateLabel(historyIndex)} className="h-14 w-14 rounded object-cover bg-white" />
                                      <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2">
                                          <span className="text-xs font-medium">{getCandidateLabel(historyIndex)}</span>
                                          {candidate.is_current && <Badge variant="secondary">{t('applied')}</Badge>}
                                          {selectedHistoryIndex === historyIndex && <Badge>{t('pendingUpdate')}</Badge>}
                                        </div>
                                        <p className="line-clamp-2 text-xs text-muted-foreground">{candidate.prompt || candidate.config?.prompt || candidate.config?.text || '-'}</p>
                                        <p className="text-[11px] text-muted-foreground">{formatImageMeta(candidate.config?.image_model_name, candidate.config?.size)}</p>
                                        <p className="text-[11px] text-muted-foreground">{formatHistoryTime(locale, candidate.created_at)}</p>
                                      </div>
                                    </button>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="audios" className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => void handleRebuildClips()} disabled={!canRebuildClips || isRebuildingClips}>
                    {isRebuildingClips ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                    {t('rebuildClipsButton')}
                  </Button>
                  <span className="text-xs text-muted-foreground">{getDirtyClipLabel(dirtyClipCount)}</span>
                </div>
                {audioItems.length === 0 ? (
                  <div className="rounded-md border bg-slate-50 p-4 text-sm text-muted-foreground">{t('noAudioAssets')}</div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {audioItems.map((path, index) => {
                      const audioUrl = getAssetUrl(path);
                      const audioConfig = audioConfigItems[index] as AudioItemConfig | undefined;
                      const audioDraft = audioDraftConfigs[index] || audioConfig || {
                        audio_model_name: config.audio_model_name,
                        audio_api_key: config.audio_api_key,
                        text: lineItems[index] || '',
                        voice: config.voice,
                      };
                      const text = lineItems[index] || audioConfig?.text || '-';
                      const isRedrawing = redrawingAudioIndex === index;
                      const isSettingsOpen = expandedAudioSettingsIndex === index;
                      const history = audioHistoryItems[index] ?? [];
                      const selectedHistoryIndex = selectedAudioHistory[index] ?? history.findIndex((item) => item?.is_current) ?? 0;
                      return (
                        <div key={`audio-${index}-${path}`} className="space-y-3 rounded-lg border bg-slate-50 p-3">
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <Mic2 className="h-4 w-4 text-purple-500" />
                              <span className="text-sm font-medium">{t('audioItem', { index: index + 1 })}</span>
                            </div>
                            <Badge variant="outline">{formatDurationLabel(durationItems[index])}</Badge>
                          </div>
                          <p className="line-clamp-3 text-xs text-muted-foreground">{text}</p>
                          <audio controls src={audioUrl} className="w-full" />
                          <div className="flex flex-wrap items-center gap-2">
                            <Button size="sm" onClick={() => void handleRedrawAudio(index)} disabled={isRedrawing || !(audioDraft.audio_api_key || config.audio_api_key)}>
                              {isRedrawing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Wand2 className="mr-1 h-4 w-4" />}
                              {t('redrawItem')}
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => setExpandedAudioSettingsIndex((current) => current === index ? null : index)}>
                              {t('settings')}
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => handleResetAudioDraft(index)}>
                              {t('resetSettings')}
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => triggerDownload(audioUrl)}>
                              <Download className="mr-1 h-4 w-4" />
                              {t('download')}
                            </Button>
                          </div>
                          {isSettingsOpen && (
                            <div className="space-y-3 rounded-md border bg-white p-3">
                              <div className="text-xs font-medium text-muted-foreground">{t('audioItemSettings')}</div>
                              <div className="space-y-2">
                                <Label>{t('audioModel')}</Label>
                                <Select value={audioDraft.audio_model_name || config.audio_model_name} onValueChange={(value) => handleAudioDraftChange(index, { audio_model_name: value })}>
                                  <SelectTrigger>
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {audioModels.map((model) => (
                                      <SelectItem key={`audio-item-model-${index}-${model.value}`} value={model.value}>
                                        {model.label}
                                      </SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              </div>
                              <div className="space-y-2">
                                <Label>{t('apiKey')}</Label>
                                <Input type="password" value={audioDraft.audio_api_key || ''} onChange={(e) => handleAudioDraftChange(index, { audio_api_key: e.target.value })} placeholder={t('itemAudioApiKeyPlaceholder')} />
                              </div>
                              <div className="space-y-2">
                                <Label>{t('voice')}</Label>
                                <Input value={audioDraft.voice || ''} onChange={(e) => handleAudioDraftChange(index, { voice: e.target.value })} placeholder={t('itemVoicePlaceholder')} />
                              </div>
                              <div className="space-y-2">
                                <Label>{t('textContent')}</Label>
                                <Input value={lineItems[index] || audioConfig?.text || ''} readOnly disabled placeholder={t('originalTextFixed')} />
                              </div>
                            </div>
                          )}
                          {history.length > 0 && (
                            <div className="space-y-2 rounded-md border bg-white p-3">
                              <div className="text-xs font-medium text-muted-foreground">{t('redrawHistory')}</div>
                              <div className="grid gap-2">
                                {history.map((candidate, historyIndex) => (
                                  <button
                                    key={`audio-history-${index}-${historyIndex}`}
                                    type="button"
                                    onClick={() => setSelectedAudioHistory((prev) => ({ ...prev, [index]: historyIndex }))}
                                    className={`rounded-md border p-2 text-left ${selectedHistoryIndex === historyIndex ? 'border-blue-500 bg-blue-50' : 'border-slate-200 bg-slate-50'}`}
                                  >
                                    <div className="flex items-center gap-2">
                                      <span className="text-xs font-medium">{getCandidateLabel(historyIndex)}</span>
                                      {candidate.is_current && <Badge variant="secondary">{t('applied')}</Badge>}
                                      {selectedHistoryIndex === historyIndex && <Badge>{t('pendingUpdate')}</Badge>}
                                      <Badge variant="outline">{formatDurationLabel(candidate.duration)}</Badge>
                                    </div>
                                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{candidate.config?.text || '-'}</p>
                                    <p className="mt-1 text-[11px] text-muted-foreground">{formatAudioMeta(candidate.config?.audio_model_name, candidate.config?.voice)}</p>
                                    <p className="mt-1 text-[11px] text-muted-foreground">{formatHistoryTime(locale, candidate.created_at)}</p>
                                    {candidate.audio_path && <audio controls src={getAssetUrl(candidate.audio_path)} className="mt-2 w-full" />}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="clips" className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => void handleRebuildClips()} disabled={!canRebuildClips || isRebuildingClips}>
                    {isRebuildingClips ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                    {t('rebuildClipsButton')}
                  </Button>
                  <Button size="sm" onClick={() => void handleConcatClips()} disabled={!canConcatClips || isConcatingClips}>
                    {isConcatingClips ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                    {t('concatClips')}
                  </Button>
                  <span className="text-xs text-muted-foreground">{getDirtyClipLabel(dirtyClipCount)}</span>
                </div>
                {clipItems.length === 0 ? (
                  <div className="rounded-md border bg-slate-50 p-4 text-sm text-muted-foreground">{t('noVideoClips')}</div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {clipItems.map((clip) => {
                      const clipUrl = getAssetUrl(clip.clip_path);
                      const imageUrl = getAssetUrl(clip.image_path);
                      const audioUrl = getAssetUrl(clip.audio_path);
                      return (
                        <div key={`clip-${clip.index}-${clip.clip_path || 'empty'}`} className="space-y-3 rounded-lg border bg-slate-50 p-3">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium">{t('videoClip', { index: clip.index + 1 })}</span>
                            {clip.dirty ? <Badge variant="destructive">{t('dirty')}</Badge> : <Badge variant="secondary">{t('synced')}</Badge>}
                          </div>
                          {clip.clip_path ? <video src={clipUrl} controls className="w-full rounded-md bg-black" /> : <div className="rounded-md border bg-white p-4 text-xs text-muted-foreground">{t('videoClipNotGenerated')}</div>}
                          <div className="grid gap-3 text-xs text-muted-foreground grid-cols-2">
                            <div className="space-y-2">
                              <div className="font-medium text-foreground">{t('imageSequence')}</div>
                              {clip.image_path ? <img src={imageUrl} alt={t('imageLabel', { index: clip.index + 1 })} className="aspect-video w-full rounded-md object-cover bg-white" /> : <div>{t('none')}</div>}
                            </div>
                            <div className="space-y-2">
                              <div className="font-medium text-foreground">{t('audioSequence')}</div>
                              {clip.audio_path ? <audio controls src={audioUrl} className="w-full" /> : <div>{t('none')}</div>}
                              <div>{t('duration')}: {formatDurationLabel(clip.duration)}</div>
                            </div>
                          </div>
                          <p className="line-clamp-3 text-xs text-muted-foreground">{clip.text || clip.prompt || '-'}</p>
                        </div>
                      );
                    })}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}

      {/* Result Card */}
      {showResult && statusForRender?.result && (
        <Card className="border-green-200 bg-green-50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-green-700">
              <CheckCircle2 className="w-5 h-5" />
              {t('videoCompleted')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {videoUrl && (
              <video
                src={videoUrl}
                controls
                className="w-full rounded-lg"
                style={{ maxHeight: '400px' }}
              />
            )}
            {statusForRender.result.text && (
              <div className="bg-white p-4 rounded-lg">
                <h4 className="font-medium mb-2">{t('generatedCopy')}</h4>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                  {statusForRender.result.text}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Start Button */}
      {!statusForRender && (
        <div className="flex flex-col items-center pt-4 gap-3">
          <Button
            size="lg"
            variant="gradient"
            onClick={handleStart}
            disabled={(!config.theme && !config.article) || !config.text_api_key || !config.image_api_key || !config.audio_api_key}
            className="px-8 py-6 text-lg shadow-lg hover:shadow-xl transition-shadow"
          >
            <Play className="w-5 h-5 mr-2" />
            {t('startGenerateVideo')}
          </Button>
          {((!config.theme && !config.article) || !config.text_api_key || !config.image_api_key || !config.audio_api_key) && (
            <p className="text-sm text-muted-foreground">
              {t('fillRequiredFields')}
              <span className="text-red-500 ml-1">{getRequiredFieldMessage()}</span>
            </p>
          )}
          {errorMessage && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-md text-red-600 text-sm max-w-md">
              <strong>{t('error')}:</strong> {errorMessage}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
