// Media Service 前端应用 - Alpine.js 组件

// 等待DOM加载完成后初始化Alpine.js
document.addEventListener('DOMContentLoaded', () => {
    console.log('Media Service Frontend initialized');
});

// Alpine.js 初始化
document.addEventListener('alpine:init', () => {
    // ==================== 全局状态存储 ====================
    Alpine.store('mediaService', {
        // API设置
        apiBaseUrl: 'http://localhost:6000',

        // 应用状态
        currentDirectory: null,
        selectedFiles: [],
        searchResults: [],
        activeVideo: null,
        activeWindows: [],
        loading: false,
        error: null,

        // 默认路径（从环境变量或配置中获取）
        defaultMediaRoot: 'E:/root/media_service_test_assets',
        defaultAnnotationRoot: 'E:/root/media_service_test_assets/scan_out',
        defaultWindowAnnotationRoot: 'E:/root/media_service_test_assets/window_scan_out',

        // API方法
        api: {
            // 健康检查
            async healthCheck() {
                try {
                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/health`);
                    return await response.json();
                } catch (error) {
                    console.error('Health check failed:', error);
                    return { success: false, error: error.message };
                }
            },

            // 获取服务端配置
            async getSettings() {
                try {
                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/settings`);
                    return await response.json();
                } catch (error) {
                    console.error('Get settings failed:', error);
                    return { success: false, error: error.message };
                }
            },

            // 构建媒体文件访问URL
            buildMediaUrl(filePath) {
                if (!filePath) {
                    return '';
                }
                return `${Alpine.store('mediaService').apiBaseUrl}/tag/media?path=${encodeURIComponent(filePath)}`;
            },

            // 标注相关
            async tagScan(inputDir, outputDir, overwrite = true, recursive = true) {
                try {
                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/tag/scan`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ input_dir: inputDir, output_dir: outputDir, overwrite, recursive })
                    });
                    return await response.json();
                } catch (error) {
                    console.error('Tag scan failed:', error);
                    return { success: false, error: error.message };
                }
            },

            async tagFile(filePath, inputRoot, outputDir, overwrite = true) {
                try {
                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/tag/file`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ file_path: filePath, input_root: inputRoot, output_dir: outputDir, overwrite })
                    });
                    return await response.json();
                } catch (error) {
                    console.error('Tag file failed:', error);
                    return { success: false, error: error.message };
                }
            },

            // 索引相关
            async indexBuild(annotationRoot) {
                try {
                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/index/build`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ annotation_root: annotationRoot })
                    });
                    return await response.json();
                } catch (error) {
                    console.error('Index build failed:', error);
                    return { success: false, error: error.message };
                }
            },

            async indexStats(annotationRoot) {
                try {
                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/index/stats?annotation_root=${encodeURIComponent(annotationRoot)}`);
                    return await response.json();
                } catch (error) {
                    console.error('Index stats failed:', error);
                    return { success: false, error: error.message };
                }
            },

            // 窗口索引
            async windowIndexScan(inputDir, outputDir, windowSizes = [2.0, 5.0, 10.0], strideRatio = 0.5, sampleFps = 1.0, maxFramesPerWindow = 8, minWindowCoverageRatio = 0.5, enableSemanticCaption = false, overwrite = true, recursive = true) {
                try {
                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/window-index/scan`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            input_dir: inputDir,
                            output_dir: outputDir,
                            window_sizes_sec: windowSizes,
                            stride_ratio: strideRatio,
                            sample_fps: sampleFps,
                            max_frames_per_window: maxFramesPerWindow,
                            min_window_coverage_ratio: minWindowCoverageRatio,
                            enable_semantic_caption: enableSemanticCaption,
                            overwrite,
                            recursive
                        })
                    });
                    return await response.json();
                } catch (error) {
                    console.error('Window index scan failed:', error);
                    return { success: false, error: error.message };
                }
            },

            async windowIndexFile(filePath, inputRoot, outputDir, windowSizes = [2.0, 5.0, 10.0], strideRatio = 0.5, sampleFps = 1.0, maxFramesPerWindow = 8, minWindowCoverageRatio = 0.5, enableSemanticCaption = false) {
                try {
                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/window-index/file`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            file_path: filePath,
                            input_root: inputRoot,
                            output_dir: outputDir,
                            window_sizes_sec: windowSizes,
                            stride_ratio: strideRatio,
                            sample_fps: sampleFps,
                            max_frames_per_window: maxFramesPerWindow,
                            min_window_coverage_ratio: minWindowCoverageRatio,
                            enable_semantic_caption: enableSemanticCaption
                        })
                    });
                    return await response.json();
                } catch (error) {
                    console.error('Window index file failed:', error);
                    return { success: false, error: error.message };
                }
            },

            // 检索相关
            async search(text, annotationRoot, searchMode = 'file_level', preferMediaType = 'auto', topK = 5, rankingStrategy = 'single_stage', windowAnnotationRoot = null, windowLevelPreferred = false, coarseTopN = 50, fineTopK = 10, duration = null, durationText = '') {
                try {
                    const requestBody = {
                        text,
                        annotation_root: annotationRoot,
                        top_k: topK,
                        prefer_media_type: preferMediaType,
                        search_mode: searchMode,
                        ranking_strategy: rankingStrategy,
                        window_level_preferred: windowLevelPreferred,
                        coarse_top_n: coarseTopN,
                        fine_top_k: fineTopK
                    };

                    if (windowAnnotationRoot) {
                        requestBody.window_annotation_root = windowAnnotationRoot;
                    }
                    if (duration !== null && duration !== '' && Number(duration) > 0) {
                        requestBody.duration = Number(duration);
                    }
                    if (durationText && durationText.trim()) {
                        requestBody.duration_text = durationText.trim();
                    }

                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/retrieve/search`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(requestBody)
                    });
                    return await response.json();
                } catch (error) {
                    console.error('Search failed:', error);
                    return { success: false, error: error.message };
                }
            },

            async batchSearch(texts, annotationRoot, topKPerLine = 3, preferMediaType = 'auto', strategy = 'sequential_coherence', searchMode = 'file_level', rankingStrategy = 'single_stage', windowAnnotationRoot = null, windowLevelPreferred = false, coarseTopN = 50, fineTopK = 10, duration = null, durationTexts = '') {
                try {
                    const requestBody = {
                        texts: Array.isArray(texts) ? texts : texts.split('\n').filter(t => t.trim()),
                        annotation_root: annotationRoot,
                        top_k_per_line: topKPerLine,
                        prefer_media_type: preferMediaType,
                        strategy,
                        search_mode: searchMode,
                        ranking_strategy: rankingStrategy,
                        window_level_preferred: windowLevelPreferred,
                        coarse_top_n: coarseTopN,
                        fine_top_k: fineTopK
                    };

                    if (windowAnnotationRoot) {
                        requestBody.window_annotation_root = windowAnnotationRoot;
                    }
                    if (duration !== null && duration !== '' && Number(duration) > 0) {
                        requestBody.duration = Number(duration);
                    }
                    if (durationTexts && durationTexts.trim()) {
                        requestBody.duration_texts = durationTexts.split('\n').filter(t => t.trim());
                    }

                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/retrieve/batch`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(requestBody)
                    });
                    return await response.json();
                } catch (error) {
                    console.error('Batch search failed:', error);
                    return { success: false, error: error.message };
                }
            },

            async explain(text, annotationPath, preferMediaType = 'auto') {
                try {
                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/retrieve/explain`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            text,
                            annotation_path: annotationPath,
                            prefer_media_type: preferMediaType
                        })
                    });
                    return await response.json();
                } catch (error) {
                    console.error('Explain failed:', error);
                    return { success: false, error: error.message };
                }
            },

            // 目录和文件操作
            async listDirectory(directory, recursive = false) {
                try {
                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/tag/list`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ directory, recursive })
                    });
                    return await response.json();
                } catch (error) {
                    console.error('List directory failed:', error);
                    return { success: false, error: error.message };
                }
            },

            async uploadFile(directory, file, overwrite = true) {
                try {
                    const formData = new FormData();
                    formData.append('file', file);
                    formData.append('directory', directory);
                    formData.append('overwrite', overwrite.toString());

                    const response = await fetch(`${Alpine.store('mediaService').apiBaseUrl}/tag/upload`, {
                        method: 'POST',
                        body: formData
                    });
                    return await response.json();
                } catch (error) {
                    console.error('Upload file failed:', error);
                    return { success: false, error: error.message };
                }
            }
        }
    });

    // ==================== 应用根组件 ====================
    Alpine.data('mediaServiceApp', () => ({
        // 标签页状态
        activeTab: 'media',

        // 模态框状态
        showVideoPlayer: false,
        showDetailModal: false,
        detailContent: '',
        videoTitle: '',

        async init() {
            console.log('App initialized');
            await this.syncDefaultPathsFromBackend();
            // 初始化时检查服务状态
            this.checkServiceStatus();

            // 设置默认目录
            if (!Alpine.store('mediaService').currentDirectory) {
                Alpine.store('mediaService').currentDirectory = Alpine.store('mediaService').defaultMediaRoot;
            }
        },

        // 同步服务端默认路径
        async syncDefaultPathsFromBackend() {
            try {
                const result = await Alpine.store('mediaService').api.getSettings();
                if (result.success) {
                    if (result.default_media_library_root) {
                        Alpine.store('mediaService').defaultMediaRoot = result.default_media_library_root;
                    }
                    if (result.default_annotation_root) {
                        Alpine.store('mediaService').defaultAnnotationRoot = result.default_annotation_root;
                    }
                    if (result.default_window_annotation_root) {
                        Alpine.store('mediaService').defaultWindowAnnotationRoot = result.default_window_annotation_root;
                    }
                }
            } catch (error) {
                console.warn('Sync default paths skipped:', error);
            }
        },

        // 检查服务状态
        async checkServiceStatus() {
            try {
                const result = await Alpine.store('mediaService').api.healthCheck();
                if (result.success) {
                    console.log('Service is healthy');
                } else {
                    Alpine.store('mediaService').error = '服务连接失败，请检查后端是否运行';
                }
            } catch (error) {
                Alpine.store('mediaService').error = '无法连接到服务，请检查网络连接';
            }
        },

        // 关闭视频播放器
        closePlayer() {
            this.showVideoPlayer = false;
            Alpine.store('mediaService').activeVideo = null;
            Alpine.store('mediaService').activeWindows = [];
        },

        // 播放窗口结果
        playWindow(result) {
            if (result.media_type === 'video') {
                Alpine.store('mediaService').activeVideo = result.source_path;

                // 如果是窗口级结果，设置活动窗口
                if (result.source_scope === 'window') {
                    Alpine.store('mediaService').activeWindows = [{
                        window_id: result.window_id,
                        window_level: result.window_level,
                        start_sec: result.start_sec,
                        end_sec: result.end_sec
                    }];
                }

                this.videoTitle = result.file_name || result.source_path.split('/').pop();
                this.showVideoPlayer = true;

                // 确保视频元素加载完成后跳转到正确位置
                setTimeout(() => {
                    const videoPlayer = Alpine.$data(document.querySelector('[x-data="videoPlayer"]'));
                    if (videoPlayer && result.source_scope === 'window' && result.start_sec) {
                        videoPlayer.playWindow({
                            start_sec: result.start_sec,
                            end_sec: result.end_sec
                        });
                    }
                }, 100);
            }
        },

        // 显示标注详情
        showDetail(annotation) {
            this.detailContent = this.formatAnnotationDetail(annotation);
            this.showDetailModal = true;
        },

        // 格式化标注详情为HTML
        formatAnnotationDetail(annotation) {
            if (!annotation) return '<p>无标注信息</p>';

            let html = '<div class="space-y-4">';

            // 基本信息
            html += `
                <div class="bg-gray-50 p-4 rounded">
                    <h4 class="font-medium text-gray-900 mb-2">基本信息</h4>
                    <div class="grid grid-cols-2 gap-2 text-sm">
                        <div><span class="text-gray-500">文件路径:</span> <span class="font-medium">${annotation.source_path || 'N/A'}</span></div>
                        <div><span class="text-gray-500">媒体类型:</span> <span class="font-medium">${annotation.media_type || 'N/A'}</span></div>
                        <div><span class="text-gray-500">文件大小:</span> <span class="font-medium">${this.formatFileSize(annotation.file_size) || 'N/A'}</span></div>
                        <div><span class="text-gray-500">状态:</span> <span class="font-medium ${annotation.status === 'ok' ? 'text-green-600' : 'text-red-600'}">${annotation.status || 'N/A'}</span></div>
                    </div>
                </div>
            `;

            // 内容标签
            if (annotation.content) {
                html += `
                    <div class="bg-blue-50 p-4 rounded">
                        <h4 class="font-medium text-gray-900 mb-2">内容分析</h4>
                        <div class="space-y-2 text-sm">
                            <div><span class="text-gray-500">描述:</span> <span class="font-medium">${annotation.content.caption || 'N/A'}</span></div>
                            <div><span class="text-gray-500">检测物体:</span> <span class="font-medium">${annotation.content.objects ? annotation.content.objects.join(', ') : 'N/A'}</span></div>
                            <div><span class="text-gray-500">场景标签:</span> <span class="font-medium">${annotation.content.scene_tags ? annotation.content.scene_tags.join(', ') : 'N/A'}</span></div>
                            <div><span class="text-gray-500">动作标签:</span> <span class="font-medium">${annotation.content.action_tags ? annotation.content.action_tags.join(', ') : 'N/A'}</span></div>
                        </div>
                    </div>
                `;
            }

            // 风格标签
            if (annotation.style) {
                html += `
                    <div class="bg-purple-50 p-4 rounded">
                        <h4 class="font-medium text-gray-900 mb-2">视觉风格</h4>
                        <div class="grid grid-cols-2 gap-2 text-sm">
                            <div><span class="text-gray-500">主色调:</span> <span class="font-medium">${annotation.style.dominant_colors ? annotation.style.dominant_colors.join(', ') : 'N/A'}</span></div>
                            <div><span class="text-gray-500">亮度:</span> <span class="font-medium">${annotation.style.brightness || 'N/A'}</span></div>
                            <div><span class="text-gray-500">对比度:</span> <span class="font-medium">${annotation.style.contrast || 'N/A'}</span></div>
                            <div><span class="text-gray-500">饱和度:</span> <span class="font-medium">${annotation.style.saturation || 'N/A'}</span></div>
                            <div><span class="text-gray-500">色温:</span> <span class="font-medium">${annotation.style.color_temperature || 'N/A'}</span></div>
                            <div><span class="text-gray-500">美学评分:</span> <span class="font-medium">${annotation.style.aesthetic_score || 'N/A'}</span></div>
                        </div>
                    </div>
                `;
            }

            // 情感标签
            if (annotation.emotion) {
                html += `
                    <div class="bg-pink-50 p-4 rounded">
                        <h4 class="font-medium text-gray-900 mb-2">情感分析</h4>
                        <div class="grid grid-cols-2 gap-2 text-sm">
                            <div><span class="text-gray-500">主要情感:</span> <span class="font-medium">${annotation.emotion.primary || 'N/A'}</span></div>
                            <div><span class="text-gray-500">次要情感:</span> <span class="font-medium">${annotation.emotion.secondary || 'N/A'}</span></div>
                            <div><span class="text-gray-500">置信度:</span> <span class="font-medium">${annotation.emotion.confidence || 'N/A'}</span></div>
                        </div>
                    </div>
                `;
            }

            // 节奏标签（视频）
            if (annotation.rhythm && annotation.media_type === 'video') {
                html += `
                    <div class="bg-green-50 p-4 rounded">
                        <h4 class="font-medium text-gray-900 mb-2">节奏分析</h4>
                        <div class="grid grid-cols-2 gap-2 text-sm">
                            <div><span class="text-gray-500">时长:</span> <span class="font-medium">${annotation.rhythm.duration ? annotation.rhythm.duration + '秒' : 'N/A'}</span></div>
                            <div><span class="text-gray-500">场景数量:</span> <span class="font-medium">${annotation.rhythm.scene_count || 'N/A'}</span></div>
                            <div><span class="text-gray-500">平均镜头长度:</span> <span class="font-medium">${annotation.rhythm.avg_shot_length ? annotation.rhythm.avg_shot_length + '秒' : 'N/A'}</span></div>
                            <div><span class="text-gray-500">运动强度:</span> <span class="font-medium">${annotation.rhythm.motion_intensity || 'N/A'}</span></div>
                            <div><span class="text-gray-500">节奏:</span> <span class="font-medium">${annotation.rhythm.pace || 'N/A'}</span></div>
                        </div>
                    </div>
                `;
            }

            html += '</div>';
            return html;
        },

        // 格式化文件大小
        formatFileSize(bytes) {
            if (!bytes) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
    }));

    // ==================== 媒体库组件 ====================
    Alpine.data('mediaLibrary', () => ({
        // 文件列表
        fileList: [],

        // 选中的文件
        selectedFiles: Alpine.store('mediaService').selectedFiles,

        // 当前目录
        currentDirectory: Alpine.store('mediaService').currentDirectory,

        // 默认路径
        defaultMediaRoot: Alpine.store('mediaService').defaultMediaRoot,

        init() {
            console.log('Media library initialized');
            // 如果当前目录为空，设置为默认目录
            if (!this.currentDirectory) {
                this.currentDirectory = this.defaultMediaRoot;
                Alpine.store('mediaService').currentDirectory = this.defaultMediaRoot;
            }

            // 尝试加载目录
            this.loadDirectory();
        },

        // 获取文件图标
        getFileIcon(fileType) {
            return fileType === 'image' ? 'fas fa-image text-green-500' : 'fas fa-video text-blue-500';
        },

        // 格式化文件大小
        formatFileSize(bytes) {
            if (!bytes) return '未知';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },

        // 检查文件是否被选中
        isSelected(file) {
            return this.selectedFiles.some(f => f.path === file.path);
        },

        // 切换文件选择
        toggleFileSelection(file) {
            if (this.isSelected(file)) {
                this.selectedFiles = this.selectedFiles.filter(f => f.path !== file.path);
            } else {
                this.selectedFiles.push(file);
            }
            Alpine.store('mediaService').selectedFiles = this.selectedFiles;
        },

        // 全选/取消全选
        toggleSelectAll(event) {
            const checked = event.target.checked;
            if (checked) {
                this.selectedFiles = [...this.fileList];
            } else {
                this.selectedFiles = [];
            }
            Alpine.store('mediaService').selectedFiles = this.selectedFiles;
        },

        // 清除选择
        clearSelection() {
            this.selectedFiles = [];
            Alpine.store('mediaService').selectedFiles = [];
        },

        // 按类型计数文件
        countFilesByType(type) {
            return this.fileList.filter(file => file.type === type).length;
        },

        // 浏览目录（模拟）
        browseDirectory() {
            // 在实际应用中，这里可以打开系统文件对话框
            // 这里我们只是模拟一下
            const newDir = prompt('请输入目录路径:', this.currentDirectory);
            if (newDir) {
                this.currentDirectory = newDir;
                Alpine.store('mediaService').currentDirectory = newDir;
                this.loadDirectory();
            }
        },

        // 加载目录
        async loadDirectory() {
            if (!this.currentDirectory) {
                Alpine.store('mediaService').error = '请先设置目录路径';
                return;
            }

            Alpine.store('mediaService').loading = true;
            Alpine.store('mediaService').error = null;

            try {
                let targetDirectory = this.currentDirectory;
                console.log('Loading directory:', targetDirectory);

                // 先按当前目录加载
                let result = await Alpine.store('mediaService').api.listDirectory(targetDirectory, false);

                // 如果当前路径是 Windows 盘符格式且结果为空，尝试回退到后端默认目录
                const isWindowsDrivePath = /^[A-Za-z]:[\\/]/.test(targetDirectory);
                if (result.success && (result.files || []).length === 0 && isWindowsDrivePath) {
                    const settings = await Alpine.store('mediaService').api.getSettings();
                    const backendDefaultRoot = settings.default_media_library_root;

                    if (settings.success && backendDefaultRoot) {
                        targetDirectory = backendDefaultRoot;
                        this.currentDirectory = backendDefaultRoot;
                        this.defaultMediaRoot = backendDefaultRoot;
                        Alpine.store('mediaService').currentDirectory = backendDefaultRoot;
                        Alpine.store('mediaService').defaultMediaRoot = backendDefaultRoot;

                        result = await Alpine.store('mediaService').api.listDirectory(targetDirectory, false);
                    }
                }

                if (result.success) {
                    this.fileList = result.files;
                    console.log('Loaded', this.fileList.length, 'files');
                } else {
                    Alpine.store('mediaService').error = result.error || '加载目录失败';
                    console.error('Failed to load directory:', result.error);
                }

            } catch (error) {
                Alpine.store('mediaService').error = '加载目录失败: ' + error.message;
                console.error('Failed to load directory:', error);
            } finally {
                Alpine.store('mediaService').loading = false;
            }
        },

        // 打开文件选择器
        openFilePicker() {
            this.$refs.fileInput.click();
        },

        // 处理文件上传
        async handleFileUpload(event) {
            const files = event.target.files;
            if (files.length === 0) return;

            console.log('Uploading', files.length, 'files');

            Alpine.store('mediaService').loading = true;
            Alpine.store('mediaService').error = null;

            try {
                let successCount = 0;
                let failCount = 0;

                // 逐个上传文件
                for (let i = 0; i < files.length; i++) {
                    const file = files[i];
                    const fileType = file.type.startsWith('image/') ? 'image' :
                                    file.type.startsWith('video/') ? 'video' : 'unknown';

                    if (fileType === 'unknown') {
                        console.warn('跳过不支持的文件类型:', file.name);
                        failCount++;
                        continue;
                    }

                    // 调用真实API上传文件
                    const result = await Alpine.store('mediaService').api.uploadFile(
                        this.currentDirectory,
                        file,
                        true  // overwrite: true
                    );

                    if (result.success) {
                        successCount++;
                        console.log('文件上传成功:', file.name);
                    } else {
                        failCount++;
                        console.error('文件上传失败:', file.name, result.error);
                    }
                }

                // 重置文件输入
                event.target.value = '';

                // 重新加载目录以获取最新文件列表
                if (successCount > 0) {
                    await this.loadDirectory();
                }

                // 显示上传结果
                const message = `上传完成: ${successCount} 个成功, ${failCount} 个失败`;
                if (failCount === 0) {
                    alert(message);
                } else {
                    alert(`⚠️ ${message}，请检查控制台获取详情`);
                }

            } catch (error) {
                Alpine.store('mediaService').error = '上传文件失败: ' + error.message;
                console.error('Upload failed:', error);
                alert('上传文件时发生错误，请查看控制台');
            } finally {
                Alpine.store('mediaService').loading = false;
            }
        },

        // 预览文件
        previewFile(file) {
            const mediaUrl = Alpine.store('mediaService').api.buildMediaUrl(file.path);
            if (file.type === 'image') {
                // 对于图片，在新窗口打开
                window.open(mediaUrl, '_blank');
            } else {
                // 对于视频，在视频播放器中打开
                Alpine.store('mediaService').activeVideo = file.path;
                const app = Alpine.$data(document.querySelector('[x-data="mediaServiceApp"]'));
                app.videoTitle = file.name;
                app.showVideoPlayer = true;
            }
        },

        // 标注单个文件
        async tagSingleFile(file) {
            const outputDir = Alpine.store('mediaService').defaultAnnotationRoot;

            Alpine.store('mediaService').loading = true;
            Alpine.store('mediaService').error = null;

            try {
                const result = await Alpine.store('mediaService').api.tagFile(
                    file.path,
                    this.currentDirectory,
                    outputDir,
                    true
                );

                if (result.success) {
                    alert(`文件 ${file.name} 标注成功！\n输出路径: ${result.output || '未知'}`);
                } else {
                    Alpine.store('mediaService').error = `标注失败: ${result.error || '未知错误'}`;
                }
            } catch (error) {
                Alpine.store('mediaService').error = '标注过程中出错: ' + error.message;
            } finally {
                Alpine.store('mediaService').loading = false;
            }
        },

        // 批量标注选中的文件
        async tagSelectedFiles() {
            if (this.selectedFiles.length === 0) {
                Alpine.store('mediaService').error = '请先选择要标注的文件';
                return;
            }

            const outputDir = Alpine.store('mediaService').defaultAnnotationRoot;

            Alpine.store('mediaService').loading = true;
            Alpine.store('mediaService').error = null;

            try {
                let successCount = 0;
                let failCount = 0;

                for (const file of this.selectedFiles) {
                    const result = await Alpine.store('mediaService').api.tagFile(
                        file.path,
                        this.currentDirectory,
                        outputDir,
                        true
                    );

                    if (result.success) {
                        successCount++;
                    } else {
                        failCount++;
                        console.error(`Failed to tag ${file.name}:`, result.error);
                    }
                }

                alert(`批量标注完成！\n成功: ${successCount} 个文件\n失败: ${failCount} 个文件`);

            } catch (error) {
                Alpine.store('mediaService').error = '批量标注过程中出错: ' + error.message;
            } finally {
                Alpine.store('mediaService').loading = false;
            }
        }
    }));

    // ==================== 标注面板组件 ====================
    Alpine.data('taggingPanel', () => ({
        // 文件级标注配置
        inputDir: Alpine.store('mediaService').defaultMediaRoot,
        outputDir: Alpine.store('mediaService').defaultAnnotationRoot,
        overwrite: true,
        recursive: true,
        singleTagFilePath: '',
        singleTagInputRoot: Alpine.store('mediaService').defaultMediaRoot,

        // 窗口级索引配置
        windowInputDir: Alpine.store('mediaService').defaultMediaRoot,
        windowOutputDir: Alpine.store('mediaService').defaultWindowAnnotationRoot,
        windowSizes: '2.0,5.0,10.0',
        strideRatio: 0.5,
        sampleFps: 1.0,
        windowOverwrite: true,
        windowRecursive: true,
        singleWindowFilePath: '',
        singleWindowInputRoot: Alpine.store('mediaService').defaultMediaRoot,

        // 状态
        isTagging: false,
        isTaggingSingleFile: false,
        isBuildingWindowIndex: false,
        isBuildingWindowSingleFile: false,
        taskHistory: [],

        init() {
            console.log('Tagging panel initialized');
            if (!this.windowOutputDir) {
                this.windowOutputDir = Alpine.store('mediaService').defaultWindowAnnotationRoot;
            }
        },

        // 标注目录
        async tagDirectory() {
            if (!this.inputDir || !this.outputDir) {
                Alpine.store('mediaService').error = '请填写输入目录和输出目录';
                return;
            }

            this.isTagging = true;
            Alpine.store('mediaService').loading = true;
            Alpine.store('mediaService').error = null;

            try {
                const result = await Alpine.store('mediaService').api.tagScan(
                    this.inputDir,
                    this.outputDir,
                    this.overwrite,
                    this.recursive
                );

                this.addTaskHistory({
                    type: '文件级标注',
                    timestamp: new Date().toLocaleString(),
                    status: result.success ? 'success' : 'error',
                    result: result.success ? `标注了 ${result.processed_count || '未知数量'} 个文件` : result.error
                });

                if (result.success) {
                    alert(`标注完成！\n处理了 ${result.processed_count || '未知数量'} 个文件`);
                } else {
                    Alpine.store('mediaService').error = `标注失败: ${result.error || '未知错误'}`;
                }
            } catch (error) {
                Alpine.store('mediaService').error = '标注过程中出错: ' + error.message;
                this.addTaskHistory({
                    type: '文件级标注',
                    timestamp: new Date().toLocaleString(),
                    status: 'error',
                    result: error.message
                });
            } finally {
                this.isTagging = false;
                Alpine.store('mediaService').loading = false;
            }
        },

        // 单文件标注
        async tagSingleFileByPath() {
            if (!this.singleTagFilePath || !this.singleTagInputRoot || !this.outputDir) {
                Alpine.store('mediaService').error = '请填写文件路径、输入根目录和输出目录';
                return;
            }

            this.isTaggingSingleFile = true;
            Alpine.store('mediaService').loading = true;
            Alpine.store('mediaService').error = null;

            try {
                const result = await Alpine.store('mediaService').api.tagFile(
                    this.singleTagFilePath,
                    this.singleTagInputRoot,
                    this.outputDir,
                    this.overwrite
                );

                this.addTaskHistory({
                    type: '单文件标注',
                    timestamp: new Date().toLocaleString(),
                    status: result.success ? 'success' : 'error',
                    result: result.success ? `输出: ${result.output || '未知'}` : result.error
                });

                if (result.success) {
                    alert(`单文件标注完成！\n输出路径: ${result.output || '未知'}`);
                } else {
                    Alpine.store('mediaService').error = `单文件标注失败: ${result.error || '未知错误'}`;
                }
            } catch (error) {
                Alpine.store('mediaService').error = '单文件标注过程中出错: ' + error.message;
                this.addTaskHistory({
                    type: '单文件标注',
                    timestamp: new Date().toLocaleString(),
                    status: 'error',
                    result: error.message
                });
            } finally {
                this.isTaggingSingleFile = false;
                Alpine.store('mediaService').loading = false;
            }
        },

        // 构建窗口索引
        async buildWindowIndex() {
            if (!this.windowInputDir) {
                Alpine.store('mediaService').error = '请填写视频目录路径';
                return;
            }

            // 解析窗口大小
            const windowSizesArray = this.windowSizes.split(',')
                .map(s => parseFloat(s.trim()))
                .filter(s => !isNaN(s) && s > 0);

            if (windowSizesArray.length === 0) {
                Alpine.store('mediaService').error = '请输入有效的窗口大小';
                return;
            }

            this.isBuildingWindowIndex = true;
            Alpine.store('mediaService').loading = true;
            Alpine.store('mediaService').error = null;

            try {
                const result = await Alpine.store('mediaService').api.windowIndexScan(
                    this.windowInputDir,
                    this.windowOutputDir,
                    windowSizesArray,
                    parseFloat(this.strideRatio),
                    parseFloat(this.sampleFps),
                    8, // maxFramesPerWindow
                    0.5, // minWindowCoverageRatio
                    false, // enableSemanticCaption
                    this.windowOverwrite,
                    this.windowRecursive
                );

                this.addTaskHistory({
                    type: '窗口级索引',
                    timestamp: new Date().toLocaleString(),
                    status: result.success ? 'success' : 'error',
                    result: result.success ? `构建了窗口索引` : result.error
                });

                if (result.success) {
                    alert('窗口索引构建完成！');
                } else {
                    Alpine.store('mediaService').error = `构建失败: ${result.error || '未知错误'}`;
                }
            } catch (error) {
                Alpine.store('mediaService').error = '构建过程中出错: ' + error.message;
                this.addTaskHistory({
                    type: '窗口级索引',
                    timestamp: new Date().toLocaleString(),
                    status: 'error',
                    result: error.message
                });
            } finally {
                this.isBuildingWindowIndex = false;
                Alpine.store('mediaService').loading = false;
            }
        },

        // 单文件窗口索引
        async buildWindowIndexForSingleFile() {
            if (!this.singleWindowFilePath || !this.singleWindowInputRoot || !this.windowOutputDir) {
                Alpine.store('mediaService').error = '请填写视频文件路径、输入根目录和窗口输出目录';
                return;
            }

            const windowSizesArray = this.windowSizes.split(',')
                .map(s => parseFloat(s.trim()))
                .filter(s => !isNaN(s) && s > 0);

            if (windowSizesArray.length === 0) {
                Alpine.store('mediaService').error = '请输入有效的窗口大小';
                return;
            }

            this.isBuildingWindowSingleFile = true;
            Alpine.store('mediaService').loading = true;
            Alpine.store('mediaService').error = null;

            try {
                const result = await Alpine.store('mediaService').api.windowIndexFile(
                    this.singleWindowFilePath,
                    this.singleWindowInputRoot,
                    this.windowOutputDir,
                    windowSizesArray,
                    parseFloat(this.strideRatio),
                    parseFloat(this.sampleFps),
                    8,
                    0.5,
                    false
                );

                this.addTaskHistory({
                    type: '单文件窗口索引',
                    timestamp: new Date().toLocaleString(),
                    status: result.success ? 'success' : 'error',
                    result: result.success ? '构建完成' : result.error
                });

                if (result.success) {
                    alert('单文件窗口索引构建完成！');
                } else {
                    Alpine.store('mediaService').error = `单文件窗口索引失败: ${result.error || '未知错误'}`;
                }
            } catch (error) {
                Alpine.store('mediaService').error = '单文件窗口索引过程中出错: ' + error.message;
                this.addTaskHistory({
                    type: '单文件窗口索引',
                    timestamp: new Date().toLocaleString(),
                    status: 'error',
                    result: error.message
                });
            } finally {
                this.isBuildingWindowSingleFile = false;
                Alpine.store('mediaService').loading = false;
            }
        },

        // 添加任务历史
        addTaskHistory(task) {
            task.id = Date.now() + Math.random();
            this.taskHistory.unshift(task);

            // 只保留最近10个任务
            if (this.taskHistory.length > 10) {
                this.taskHistory = this.taskHistory.slice(0, 10);
            }
        }
    }));

    // ==================== 检索面板组件 ====================
    Alpine.data('searchPanel', () => ({
        // 检索配置
        annotationRoot: Alpine.store('mediaService').defaultAnnotationRoot,
        windowAnnotationRoot: Alpine.store('mediaService').defaultWindowAnnotationRoot,
        searchMode: 'file_level',
        preferMediaType: 'auto',
        topK: 5,

        // 检索输入
        searchText: '',
        durationInput: '',
        durationTextInput: '',

        // 检索结果
        searchResults: Alpine.store('mediaService').searchResults,
        isSearching: false,

        init() {
            console.log('Search panel initialized');
            if (!this.windowAnnotationRoot) {
                this.windowAnnotationRoot = Alpine.store('mediaService').defaultWindowAnnotationRoot;
            }
        },
        async search() {
            if (!this.searchText.trim()) {
                Alpine.store('mediaService').error = '请输入检索文本';
                return;
            }

            if (!this.annotationRoot) {
                Alpine.store('mediaService').error = '请填写标注根目录';
                return;
            }

            this.isSearching = true;
            Alpine.store('mediaService').loading = true;
            Alpine.store('mediaService').error = null;

            try {
                const queryLines = this.searchText.split('\n').filter(t => t.trim());
                const durationLines = this.durationTextInput.split('\n').filter(t => t.trim());
                const useBatch = queryLines.length > 1 || durationLines.length > 1;

                let result;
                if (useBatch) {
                    result = await Alpine.store('mediaService').api.batchSearch(
                        this.searchText,
                        this.annotationRoot,
                        this.topK,
                        this.preferMediaType,
                        'sequential_coherence',
                        this.searchMode,
                        this.searchMode === 'window_level' ? 'cascade_sequence_v1' : 'single_stage',
                        this.windowAnnotationRoot,
                        this.searchMode === 'window_level',
                        50,
                        10,
                        this.durationInput,
                        this.durationTextInput
                    );
                } else {
                    result = await Alpine.store('mediaService').api.search(
                        this.searchText.trim(),
                        this.annotationRoot,
                        this.searchMode,
                        this.preferMediaType,
                        this.topK,
                        this.searchMode === 'window_level' ? 'cascade_sequence_v1' : 'single_stage',
                        this.windowAnnotationRoot,
                        this.searchMode === 'window_level',
                        50,
                        10,
                        this.durationInput,
                        this.durationTextInput
                    );
                }

                if (result.success) {
                    if (Array.isArray(result.results)) {
                        this.searchResults = result.results;
                    } else if (Array.isArray(result.items)) {
                        this.searchResults = result.items.flatMap(item => item.results || []);
                    } else {
                        this.searchResults = [];
                    }
                    Alpine.store('mediaService').searchResults = this.searchResults;

                    if (this.searchResults.length === 0) {
                        Alpine.store('mediaService').error = '未找到匹配结果';
                    }
                } else {
                    Alpine.store('mediaService').error = `检索失败: ${result.error || '未知错误'}`;
                    this.searchResults = [];
                    Alpine.store('mediaService').searchResults = [];
                }
            } catch (error) {
                Alpine.store('mediaService').error = '检索过程中出错: ' + error.message;
                this.searchResults = [];
                Alpine.store('mediaService').searchResults = [];
            } finally {
                this.isSearching = false;
                Alpine.store('mediaService').loading = false;
            }
        },

        // 构建检索结果视频地址
        getResultVideoSrc(result) {
            if (!result || !result.source_path) {
                return '';
            }
            return Alpine.store('mediaService').api.buildMediaUrl(result.source_path);
        },

        // 预览结果
        previewResult(result) {
            const app = Alpine.$data(document.querySelector('[x-data="mediaServiceApp"]'));

            if (result.media_type === 'image') {
                // 对于图片，在新窗口打开
                const mediaUrl = Alpine.store('mediaService').api.buildMediaUrl(result.source_path);
                window.open(mediaUrl, '_blank');
            } else {
                // 对于视频，在视频播放器中打开
                app.playWindow(result);
            }
        },

        // 解释结果
        async explainResult(result) {
            if (!result.annotation_path) {
                Alpine.store('mediaService').error = '该结果没有标注路径，无法解释';
                return;
            }

            Alpine.store('mediaService').loading = true;
            Alpine.store('mediaService').error = null;

            try {
                const explainResult = await Alpine.store('mediaService').api.explain(
                    this.searchText.trim(),
                    result.annotation_path,
                    this.preferMediaType
                );

                if (explainResult.success) {
                    const app = Alpine.$data(document.querySelector('[x-data="mediaServiceApp"]'));
                    app.detailContent = `
                        <div class="space-y-4">
                            <div class="bg-blue-50 p-4 rounded">
                                <h4 class="font-medium text-gray-900 mb-2">评分解释</h4>
                                <div class="space-y-2">
                                    <div><span class="text-gray-500">查询文本:</span> <span class="font-medium">${this.searchText.trim()}</span></div>
                                    <div><span class="text-gray-500">匹配原因:</span> <span class="font-medium">${explainResult.explanation || '无解释信息'}</span></div>
                                </div>
                            </div>

                            <div class="bg-gray-50 p-4 rounded">
                                <h4 class="font-medium text-gray-900 mb-2">原始结果</h4>
                                <pre class="text-xs overflow-auto">${JSON.stringify(result, null, 2)}</pre>
                            </div>
                        </div>
                    `;
                    app.showDetailModal = true;
                } else {
                    Alpine.store('mediaService').error = `解释失败: ${explainResult.error || '未知错误'}`;
                }
            } catch (error) {
                Alpine.store('mediaService').error = '解释过程中出错: ' + error.message;
            } finally {
                Alpine.store('mediaService').loading = false;
            }
        },

        // 播放窗口（调用应用级方法）
        playWindow(result) {
            const app = Alpine.$data(document.querySelector('[x-data="mediaServiceApp"]'));
            app.playWindow(result);
        }
    }));

    // ==================== 配置面板组件 ====================
    Alpine.data('configPanel', () => ({
        // 配置
        defaultMediaRoot: Alpine.store('mediaService').defaultMediaRoot,
        defaultAnnotationRoot: Alpine.store('mediaService').defaultAnnotationRoot,

        // 系统信息
        serviceStatus: '未知',
        apiVersion: '未知',

        init() {
            console.log('Config panel initialized');
            this.loadSystemInfo();
        },

        // 加载系统信息
        async loadSystemInfo() {
            try {
                const result = await Alpine.store('mediaService').api.healthCheck();
                if (result.success) {
                    this.serviceStatus = '运行中';
                    this.apiVersion = result.version || '未知';
                } else {
                    this.serviceStatus = '不可用';
                }
            } catch (error) {
                this.serviceStatus = '连接失败';
            }
        },

        // 保存配置
        saveConfig() {
            // 在实际应用中，这里应该将配置保存到本地存储或服务器
            Alpine.store('mediaService').apiBaseUrl = Alpine.store('mediaService').apiBaseUrl;

            alert('配置已保存（模拟）');
        }
    }));

    // ==================== 视频播放器组件 ====================
    Alpine.data('videoPlayer', () => ({
        // 视频状态
        videoUrl: null,
        isPlaying: false,
        currentTime: 0,
        duration: 0,

        // 活动窗口
        activeWindows: Alpine.store('mediaService').activeWindows,

        init() {
            console.log('Video player initialized');

            // 监听全局状态变化
            Alpine.effect(() => {
                const activeVideo = Alpine.store('mediaService').activeVideo;
                if (activeVideo) {
                    this.videoUrl = Alpine.store('mediaService').api.buildMediaUrl(activeVideo);

                    // 确保视频元素重新加载
                    setTimeout(() => {
                        if (this.$refs.video) {
                            this.$refs.video.load();
                        }
                    }, 100);
                }
            });

            Alpine.effect(() => {
                this.activeWindows = Alpine.store('mediaService').activeWindows;
            });
        },

        // 视频加载完成
        onVideoLoaded() {
            if (this.$refs.video) {
                this.duration = this.$refs.video.duration;
            }
        },

        // 更新进度
        updateProgress() {
            if (this.$refs.video) {
                this.currentTime = this.$refs.video.currentTime;
                this.isPlaying = !this.$refs.video.paused;
            }
        },

        // 播放窗口
        playWindow(window) {
            if (!this.$refs.video) return;

            this.$refs.video.currentTime = window.start_sec;
            this.$refs.video.play();

            // 在窗口结束时暂停
            const endTime = window.end_sec;
            const onTimeUpdate = () => {
                if (this.$refs.video.currentTime >= endTime) {
                    this.$refs.video.pause();
                    this.$refs.video.removeEventListener('timeupdate', onTimeUpdate);
                }
            };
            this.$refs.video.addEventListener('timeupdate', onTimeUpdate);
        },

        // 跳转到指定时间
        seekToTime(time) {
            if (this.$refs.video) {
                this.$refs.video.currentTime = parseFloat(time);
            }
        },

        // 切换播放/暂停
        togglePlay() {
            if (!this.$refs.video) return;

            if (this.$refs.video.paused) {
                this.$refs.video.play();
            } else {
                this.$refs.video.pause();
            }
        },

        // 格式化时间
        formatTime(seconds) {
            if (!seconds) return '0:00';
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        },

        // 关闭播放器（调用应用级方法）
        closePlayer() {
            const app = Alpine.$data(document.querySelector('[x-data="mediaServiceApp"]'));
            if (app) {
                app.closePlayer();
            }
        }
    }));
});