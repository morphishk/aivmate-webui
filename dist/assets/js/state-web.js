        document.addEventListener('DOMContentLoaded', function() {
            // ===== 错误边界与工具函数 =====
            function showToast(message) {
                let toast = document.getElementById('api-toast');
                if (!toast) {
                    toast = document.createElement('div');
                    toast.id = 'api-toast';
                    toast.style.cssText = 'position:fixed;top:50px;left:50%;transform:translateX(-50%);background:rgba(200,0,0,0.9);color:#fff;padding:8px 16px;border-radius:4px;z-index:9999;font-size:14px;pointer-events:none;opacity:0;transition:opacity 0.3s;';
                    document.body.appendChild(toast);
                }
                toast.textContent = message;
                toast.style.opacity = '1';
                clearTimeout(toast._timer);
                toast._timer = setTimeout(function() { toast.style.opacity = '0'; }, 3000);
            }

            // ===== 自定义模态框 =====
            const Modal = {
                overlay: document.getElementById('custom-modal'),
                titleEl: document.getElementById('modal-title'),
                bodyEl: document.getElementById('modal-body'),
                inputEl: document.getElementById('modal-input'),
                confirmBtn: document.getElementById('modal-confirm'),
                cancelBtn: document.getElementById('modal-cancel'),
                _resolve: null,
                _reject: null,

                init: function() {
                    const self = this;
                    this.confirmBtn.onclick = function() {
                        const value = self.inputEl.style.display === 'none' ? true : (self.inputEl.value || '');
                        if (self._resolve) self._resolve(value);
                        self.hide();
                    };
                    this.cancelBtn.onclick = function() {
                        if (self._resolve) self._resolve(false);
                        self.hide();
                    };
                    this.overlay.addEventListener('click', function(e) {
                        if (e.target === self.overlay) {
                            if (self._resolve) self._resolve(false);
                            self.hide();
                        }
                    });
                    this.inputEl.addEventListener('keydown', function(e) {
                        if (e.key === 'Enter') {
                            e.preventDefault();
                            self.confirmBtn.click();
                        } else if (e.key === 'Escape') {
                            self.cancelBtn.click();
                        }
                    });
                },

                show: function(config) {
                    const self = this;
                    return new Promise(function(resolve) {
                        self._resolve = resolve;
                        self.titleEl.textContent = config.title || '提示';
                        self.bodyEl.textContent = config.message || '';
                        self.confirmBtn.textContent = config.confirmText || '确认';
                        self.cancelBtn.textContent = config.cancelText || '取消';
                        if (config.showInput) {
                            self.inputEl.style.display = 'block';
                            self.inputEl.value = config.inputValue || '';
                            setTimeout(function() { self.inputEl.focus(); self.inputEl.select(); }, 50);
                        } else {
                            self.inputEl.style.display = 'none';
                            self.inputEl.value = '';
                            setTimeout(function() { self.confirmBtn.focus(); }, 50);
                        }
                        self.overlay.style.display = 'flex';
                    });
                },

                hide: function() {
                    this.overlay.style.display = 'none';
                    this._resolve = null;
                }
            };
            Modal.init();

            async function apiFetch(url, options) {
                try {
                    const res = await fetch(url, options);
                    const data = await res.json();
                    if (data.status === 'error' && !(options && options.skipStatusCheck)) {
                        showToast('错误：' + (data.message || '未知错误'));
                        throw new Error(data.message || 'API错误');
                    }
                    return data;
                } catch (e) {
                    if (e.name === 'TypeError' || (e.message && e.message.includes('fetch'))) {
                        showToast('网络连接失败，请检查服务状态');
                    }
                    throw e;
                }
            }

            const dropdownBtn = document.getElementById('dropdown-btn');
            const dropdownContent = document.getElementById('dropdown-content');
            const chatMessages = document.getElementById('chat_messages');
            let sessionLoading = document.getElementById('session-loading');
            // session-loading spinner init
            if (!sessionLoading) {
                sessionLoading = document.createElement('div');
                sessionLoading.id = 'session-loading';
                sessionLoading.className = 'session-loading-msg';
                sessionLoading.style.display = 'none';
                sessionLoading.title = '小月正在思考与回答...';
                sessionLoading.innerHTML = '<div class="spinner"></div>';
                const chatMessagesEl = document.getElementById('chat_messages');
                // session-loading dynamically created
                if (chatMessagesEl && chatMessagesEl.parentNode) {
                    chatMessagesEl.parentNode.insertBefore(sessionLoading, chatMessagesEl.nextSibling);
                }
            }
            const clearButton = document.getElementById('clear_button');
            dropdownBtn.addEventListener('click', function() {
                dropdownContent.classList.toggle('show');
            });
            window.addEventListener('click', function(event) {
                if (!event.target.matches('#dropdown-btn')) {
                    if (dropdownContent.classList.contains('show')) {
                        dropdownContent.classList.remove('show');
                    }
                }
            });
            document.getElementById('live2d-btn').addEventListener('click', function() {
                window.open(document.getElementById('live2d_url').href, '_blank');
                dropdownContent.classList.remove('show');
            });
            document.getElementById('mmd-btn').addEventListener('click', function() {
                window.open(document.getElementById('mmd_url').href, '_blank');
                dropdownContent.classList.remove('show');
            });
            document.getElementById('vmd-btn').addEventListener('click', function() {
                window.open(document.getElementById('vmd_url').href, '_blank');
                dropdownContent.classList.remove('show');
            });
            document.getElementById('vrm-btn').addEventListener('click', function() {
                window.open(document.getElementById('vrm_url').href, '_blank');
                dropdownContent.classList.remove('show');
            });
            document.getElementById('settings-btn').addEventListener('click', function() {
                window.open(document.getElementById('settings_url').href, '_blank');
                dropdownContent.classList.remove('show');
            });
            const live2dUrl = document.createElement('a');
            live2dUrl.id = 'live2d_url';
            live2dUrl.style.display = 'none';
            document.body.appendChild(live2dUrl);           
            const mmdUrl = document.createElement('a');
            mmdUrl.id = 'mmd_url';
            mmdUrl.style.display = 'none';
            document.body.appendChild(mmdUrl);
            const vmdUrl = document.createElement('a');
            vmdUrl.id = 'vmd_url';
            vmdUrl.style.display = 'none';
            document.body.appendChild(vmdUrl);
            const vrmUrl = document.createElement('a');
            vrmUrl.id = 'vrm_url';
            vrmUrl.style.display = 'none';
            document.body.appendChild(vrmUrl);
            const settingsUrl = document.createElement('a');
            settingsUrl.id = 'settings_url';
            settingsUrl.style.display = 'none';
            document.body.appendChild(settingsUrl);

            // ===== 时间格式化工具 =====
            function formatTime(ts) {
                if (!ts) {
                    const now = new Date();
                    return now.getHours().toString().padStart(2, '0') + ':' +
                           now.getMinutes().toString().padStart(2, '0') + ':' +
                           now.getSeconds().toString().padStart(2, '0');
                }
                const d = new Date(ts * 1000);
                return d.getHours().toString().padStart(2, '0') + ':' +
                       d.getMinutes().toString().padStart(2, '0');
            }
            function formatDateTime(ts) {
                if (!ts) return '';
                const d = new Date(ts * 1000);
                return (d.getMonth() + 1) + '/' + d.getDate() + ' ' +
                       d.getHours().toString().padStart(2, '0') + ':' +
                       d.getMinutes().toString().padStart(2, '0');
            }

            window.userInteracted = false;
            const autoVoiceCheckbox = document.getElementById('autoVoice');
            const ttsStatusEl = document.getElementById('tts-status');
            const voiceHintEl = document.getElementById('voice-hint');

            // 恢复自动朗读开关状态
            const savedAutoVoice = localStorage.getItem('autoVoice');
            autoVoiceCheckbox.checked = savedAutoVoice === null ? true : savedAutoVoice === 'true';

            // ===== ASR 模式切换 =====
            const ASRState = {
                IDLE: 'idle',
                RECORDING: 'recording',
                PROCESSING: 'processing'
            };
            let asrState = ASRState.IDLE;
            let mediaRecorder = null;
            let audioChunks = [];
            let recordingStartTime = 0;
            let holdAudioCtx = null;
            let holdAnalyser = null;
            let holdDataArray = null;
            let holdWaveformRaf = null;
            let holdMicStream = null;
            let asrMode = localStorage.getItem('asrMode') || 'vad';

            function initAsrModeSelector() {
                const voiceBar = document.querySelector('.voice-bar');
                if (!voiceBar || document.getElementById('asr-mode-selector')) return;
                const selector = document.createElement('div');
                selector.id = 'asr-mode-selector';
                selector.className = 'asr-mode-selector';
                selector.innerHTML = '<span>🎤</span>' +
                    '<label><input type="radio" name="asrMode" value="vad" ' + (asrMode === 'vad' ? 'checked' : '') + '> VAD自动</label>' +
                    '<label><input type="radio" name="asrMode" value="hold" ' + (asrMode === 'hold' ? 'checked' : '') + '> 按住说话</label>';
                voiceBar.appendChild(selector);
                selector.querySelectorAll('input[name="asrMode"]').forEach(function(radio) {
                    radio.addEventListener('change', function() {
                        setAsrMode(this.value);
                    });
                });
            }

            function setAsrMode(mode) {
                if (mode === asrMode) return;
                asrMode = mode;
                localStorage.setItem('asrMode', mode);
                resetAllRecordingState();
                const radios = document.querySelectorAll('input[name="asrMode"]');
                radios.forEach(function(r) { r.checked = (r.value === mode); });
                const micBtn = document.getElementById('mic-btn');
                if (micBtn) {
                    micBtn.title = mode === 'hold' ? '按住说话（或按空格键）' : '语音输入（VAD自动监听）';
                }
                showStatusToast('已切换到' + (mode === 'vad' ? 'VAD自动监听' : '按住说话') + '模式');
            }

            function resetAllRecordingState() {
                if (asrState === ASRState.RECORDING && mediaRecorder && mediaRecorder.state === 'recording') {
                    try { mediaRecorder.stop(); } catch(e) {}
                }
                if (holdMicStream) {
                    holdMicStream.getTracks().forEach(function(t) { t.stop(); });
                    holdMicStream = null;
                }
                if (holdAudioCtx) {
                    holdAudioCtx.close();
                    holdAudioCtx = null;
                }
                if (holdWaveformRaf) {
                    cancelAnimationFrame(holdWaveformRaf);
                    holdWaveformRaf = null;
                }
                mediaRecorder = null;
                audioChunks = [];
                asrState = ASRState.IDLE;
                _submitState.isSubmitting = false;
                const waveCanvas = document.getElementById('waveform-canvas');
                if (waveCanvas) waveCanvas.style.display = 'none';
                if (isListening) {
                    _stopListening();
                }
            }

            function showStatusToast(msg) {
                const toast = document.createElement('div');
                toast.textContent = msg;
                toast.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:rgba(0,30,60,0.9);color:#4fc3f7;padding:8px 16px;border-radius:6px;font-size:13px;z-index:9999;border:1px solid rgba(0,150,255,0.3);';
                document.body.appendChild(toast);
                setTimeout(function() { toast.remove(); }, 2000);
            }

            autoVoiceCheckbox.addEventListener('change', function() {
                localStorage.setItem('autoVoice', autoVoiceCheckbox.checked);
            });

            if (window.location.protocol === 'http:') {
                voiceHintEl.style.display = 'block';
            }
            document.addEventListener('click', function onFirstClick() {
                window.userInteracted = true;
                voiceHintEl.style.display = 'none';
                document.removeEventListener('click', onFirstClick);
            }, { once: true });

            // TTS 音频播放队列
            let ttsQueue = [];
            let ttsIndex = 0;
            let currentAudio = null;
            let currentTtsBtn = null;
            let activeTtsPollTimer = null;

            function updateTtsStatus() {
                if (ttsQueue.length > 0 && ttsIndex < ttsQueue.length) {
                    ttsStatusEl.textContent = '🔊 正在播放 ' + (ttsIndex + 1) + '/' + ttsQueue.length;
                    ttsStatusEl.classList.add('show');
                } else {
                    ttsStatusEl.classList.remove('show');
                }
            }

            function playTtsQueue(urls, btnEl) {
                if (!urls || urls.length === 0) {
                    _submitState.isSubmitting = false;
                    return;
                }
                ttsQueue = urls;
                ttsIndex = 0;
                currentTtsBtn = btnEl;
                if (btnEl) btnEl.textContent = '⏹️';
                playNextTts();
            }

            function appendToTtsQueue(newUrls) {
                if (!newUrls || newUrls.length === 0) return;
                console.log('[TTS] appendToTtsQueue called, newUrls:', newUrls.length, 'current ttsQueue:', ttsQueue.length, 'ttsIndex:', ttsIndex, 'currentAudio:', !!currentAudio);
                const existing = new Set(ttsQueue);
                let appended = false;
                for (let i = 0; i < newUrls.length; i++) {
                    if (!existing.has(newUrls[i])) {
                        ttsQueue.push(newUrls[i]);
                        existing.add(newUrls[i]);
                        appended = true;
                    }
                }
                console.log('[TTS] after append, ttsQueue:', ttsQueue.length, 'appended:', appended);
                if (appended) {
                    updateTtsStatus();
                    // 如果当前没在播放（比如第一段播完了但队列空了），继续播
                    if (!currentAudio && ttsIndex < ttsQueue.length) {
                        console.log('[TTS] auto continue playNextTts, ttsIndex:', ttsIndex);
                        playNextTts();
                    } else {
                        console.log('[TTS] skip auto continue, currentAudio:', !!currentAudio, 'ttsIndex:', ttsIndex, 'ttsQueue:', ttsQueue.length);
                    }
                }
            }

            function startTtsPoll(batchId, total) {
                console.log('[TTS] startTtsPoll, batchId:', batchId, 'total:', total);
                if (!batchId || total <= 1) {
                    console.log('[TTS] startTtsPoll early return, batchId:', batchId, 'total:', total);
                    return;
                }
                // 取消之前的轮询，避免多个轮询同时运行
                if (activeTtsPollTimer) {
                    clearInterval(activeTtsPollTimer);
                    activeTtsPollTimer = null;
                }
                const pollTimer = setInterval(function() {
                    fetch('./api/tts_progress', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({batch_id: batchId})
                    })
                    .then(function(r) { return r.json(); })
                    .then(function(progress) {
                        console.log('[TTS] poll result:', progress.status, 'urls:', progress.urls ? progress.urls.length : 0, 'done:', progress.done);
                        if (progress.status === 'success' && progress.urls && progress.urls.length > 0) {
                            appendToTtsQueue(progress.urls);
                            if (progress.done) {
                                clearInterval(pollTimer);
                                activeTtsPollTimer = null;
                            }
                        }
                    })
                    .catch(function(err) {
                        console.warn('[TTS Poll] 轮询失败:', err);
                    });
                }, 800);
                activeTtsPollTimer = pollTimer;
                // 安全：最多轮询 2 分钟，防止无限轮询
                setTimeout(function() {
                    if (activeTtsPollTimer === pollTimer) {
                        activeTtsPollTimer = null;
                    }
                    clearInterval(pollTimer);
                }, 120000);
            }

            function reportAudioStatus(playing) {
                const payload = { playing: playing };
                // 新增：上报当前播放文件路径
                if (playing && currentAudio && currentAudio.src) {
                    try {
                        const url = new URL(currentAudio.src);
                        // 拼接为相对路径，如 dist/assets/cache_voice/tts_xxx.mp3
                        payload.current_file = 'dist' + url.pathname;
                    } catch (e) {
                        console.error('[AudioStatus] 解析音频 URL 失败:', e);
                    }
                }
                fetch('./api/audio_status', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                }).catch(function(err) {
                    console.error('[AudioStatus] 上报失败:', err);
                });
            }

            function playNextTts() {
                console.log('[TTS] playNextTts, ttsIndex:', ttsIndex, 'ttsQueue.length:', ttsQueue.length);
                if (ttsIndex >= ttsQueue.length) {
                    console.log('[TTS] playNextTts queue empty, activeTtsPollTimer:', !!activeTtsPollTimer);
                    reportAudioStatus(false);
                    // 如果后台仍在生成后续段（轮询活跃），不要停止 TTS，等待 appendToTtsQueue 追加
                    if (activeTtsPollTimer) {
                        currentAudio = null; // 释放旧 Audio，允许 appendToTtsQueue 触发续播
                        console.log('[TTS] playNextTts: waiting for polling to deliver more segments');
                        updateTtsStatus();
                        return;
                    }
                    stopTts();
                    _submitState.isSubmitting = false;
                    return;
                }
                updateTtsStatus();
                const url = ttsQueue[ttsIndex];
                console.log('[TTS] playing url:', url.substring(url.lastIndexOf('/') + 1));
                currentAudio = new Audio(url);
                // 播放新文件前上报
                reportAudioStatus(true);
                currentAudio.onplay = function() {
                    reportAudioStatus(true);
                };
                currentAudio.onended = function() {
                    ttsIndex++;
                    playNextTts();
                };
                currentAudio.onerror = function() {
                    console.error('TTS 音频播放失败:', url);
                    reportAudioStatus(false);
                    ttsIndex++;
                    playNextTts();
                };
                currentAudio.onpause = function() {
                    reportAudioStatus(false);
                };
                currentAudio.play().catch(function(e) {
                    console.warn('浏览器阻止自动播放:', e);
                    reportAudioStatus(false);
                    ttsIndex++;
                    playNextTts();
                });
            }

            function stopTts() {
                if (currentAudio) {
                    currentAudio.pause();
                    currentAudio = null;
                }
                reportAudioStatus(false);
                if (currentTtsBtn) {
                    currentTtsBtn.textContent = '🔊';
                    currentTtsBtn = null;
                }
                // 取消活跃的 TTS 轮询
                if (activeTtsPollTimer) {
                    clearInterval(activeTtsPollTimer);
                    activeTtsPollTimer = null;
                }
                ttsQueue = [];
                ttsIndex = 0;
                updateTtsStatus();
                _submitState.isSubmitting = false;
            }

            function playSingleTTS(text, btnEl) {
                console.log('[TTS] playSingleTTS called, text length:', text ? text.length : 0, 'content:', text ? text.substring(0, 80) : '');
                if (currentTtsBtn && currentTtsBtn !== btnEl) {
                    stopTts();
                }
                if (btnEl && btnEl.textContent === '⏹️') {
                    stopTts();
                    return;
                }
                fetch('./api/tts_segment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({text: text, session_id: AppState.currentSessionId})
                })
                .then(r => r.json())
                .then(data => {
                    console.log('[TTS] tts_segment response:', data.status, 'audio_urls:', data.audio_urls ? data.audio_urls.length : 0, 'batch_id:', data.batch_id, 'total:', data.total);
                    if (data.status === 'success' && data.audio_urls && data.audio_urls.length > 0) {
                        playTtsQueue(data.audio_urls, btnEl);
                        // 流式 TTS：启动轮询追加后续段
                        if (data.batch_id && data.total > 1) {
                            startTtsPoll(data.batch_id, data.total);
                        } else {
                            console.log('[TTS] no polling needed, batch_id:', data.batch_id, 'total:', data.total);
                        }
                    }
                })
                .catch(err => console.error('TTS 请求失败:', err));
            }

            // 浮动朗读按钮（选中文本）
            let floatTtsBtn = null;
            function showFloatTTSButton(text) {
                if (!floatTtsBtn) {
                    floatTtsBtn = document.createElement('button');
                    floatTtsBtn.id = 'float-tts-btn';
                    floatTtsBtn.innerHTML = '🔊';
                    floatTtsBtn.title = '朗读选中文本';
                    document.body.appendChild(floatTtsBtn);
                }
                const selection = window.getSelection();
                if (selection.rangeCount === 0) return;
                const range = selection.getRangeAt(0).getBoundingClientRect();
                floatTtsBtn.style.left = (range.left + window.scrollX) + 'px';
                floatTtsBtn.style.top = (range.top + window.scrollY - 36) + 'px';
                floatTtsBtn.style.display = 'block';
                floatTtsBtn.onclick = function() {
                    playSingleTTS(text);
                    hideFloatTTSButton();
                };
            }
            function hideFloatTTSButton() {
                if (floatTtsBtn) floatTtsBtn.style.display = 'none';
            }
            document.addEventListener('mouseup', function() {
                const selection = window.getSelection().toString().trim();
                if (selection.length > 0) {
                    showFloatTTSButton(selection);
                } else {
                    hideFloatTTSButton();
                }
            });

            // ===== 消息渲染函数 =====
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            function renderSingleMessage(msg, index) {
                const msgDiv = document.createElement('div');
                msgDiv.className = 'message ' + (msg.role === 'user' ? 'user-message' : 'ai-message');
                msgDiv.dataset.index = index;
                if (msg.id != null) {
                    msgDiv.dataset.messageId = msg.id;
                }
                // 新增：支持流式消息标记
                if (msg.streamId) {
                    msgDiv.setAttribute('data-stream-id', msg.streamId);
                }

                if (msg.isLoading) {
                    msgDiv.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
                    chatMessages.appendChild(msgDiv);
                    return msgDiv;
                }

                const contentDiv = document.createElement('div');
                contentDiv.className = 'message-content';

                if (msg.file_name && msg.role === 'user') {
                    const fileCard = document.createElement('div');
                    fileCard.style.cssText = 'display:inline-flex; align-items:center; gap:6px; padding:6px 10px; background:rgba(0,100,200,0.25); border:1px solid rgba(0,150,255,0.4); border-radius:6px; margin-bottom:6px; font-size:13px; color:#a0d0ff;';
                    fileCard.innerHTML = '<span>📄</span><span>' + escapeHtml(msg.file_name) + '</span>';
                    contentDiv.appendChild(fileCard);
                }

                if (msg.content) {
                    const textDiv = document.createElement('div');
                    textDiv.textContent = msg.content;
                    contentDiv.appendChild(textDiv);
                }

                msgDiv.appendChild(contentDiv);

                if (msg.image_url && msg.role === 'user') {
                    const img = document.createElement('img');
                    img.src = msg.image_url;
                    img.className = 'chat-image';
                    img.style.maxHeight = '120px';
                    img.style.borderRadius = '4px';
                    img.style.marginTop = '6px';
                    img.style.border = '1px solid rgba(255,255,255,0.2)';
                    img.onerror = function() { this.style.display = 'none'; };
                    msgDiv.appendChild(img);
                }

                const timeDiv = document.createElement('div');
                timeDiv.className = 'timestamp';
                timeDiv.textContent = formatTime(msg.timestamp);
                msgDiv.appendChild(timeDiv);

                if (msg.role === 'assistant') {
                    const actionsDiv = document.createElement('div');
                    actionsDiv.className = 'message-actions';
                    const ttsBtn = document.createElement('button');
                    ttsBtn.className = 'tts-btn';
                    ttsBtn.textContent = '🔊';
                    ttsBtn.title = '朗读';
                    ttsBtn.onclick = function() { playSingleTTS(msg.content, ttsBtn); };
                    actionsDiv.appendChild(ttsBtn);
                    msgDiv.appendChild(actionsDiv);
                }

                chatMessages.appendChild(msgDiv);
                return msgDiv;
            }

            function renderHistory() {
                if (!chatMessages) return;
                ChatSearch.clearHighlight();
                chatMessages.innerHTML = '';
                AppState.conversationHistory.forEach(function(msg, index) {
                    renderSingleMessage(msg, index);
                });
                chatMessages.scrollTop = chatMessages.scrollHeight;
                ChatNav.render();
                if (ChatSearch.isOpen) {
                    const input = document.getElementById('search-input');
                    if (input) ChatSearch.search(input.value);
                }
            }

            function appendMessage(msg) {
                if (!chatMessages) return null;
                const el = renderSingleMessage(msg, AppState.conversationHistory.length - 1);
                chatMessages.scrollTop = chatMessages.scrollHeight;
                ChatNav.refresh();
                return el;
            }

            // ===== AppState: 会话管理全局状态 =====
            const AppState = {
                currentSessionId: null,
                conversationHistory: [],
                sessions: [],
                isSidebarOpen: true,
                _saveTimer: null,
                _isSaving: false,
                _dirty: false,
                pendingSessions: new Set(),

                async init() {
                    await this.loadSessions();
                    const lastId = localStorage.getItem('lastSessionId');
                    if (lastId && this.sessions.find(function(s) { return s.id === lastId && !s.is_archived; })) {
                        await this.loadSession(lastId);
                    } else if (this.sessions.length > 0) {
                        await this.loadSession(this.sessions[0].id);
                    } else {
                        await this.createNewSession();
                    }
                    this.isSidebarOpen = localStorage.getItem('sidebarOpen') !== 'false';
                    this._applySidebarState();
                },

                async loadSessions() {
                    try {
                        const res = await fetch('./api/sessions');
                        const data = await res.json();
                        if (data.status === 'success') {
                            this.sessions = data.sessions || [];
                            this._renderSessionList();
                        }
                    } catch (e) {
                        console.error('[AppState] loadSessions failed:', e);
                    }
                },

                async loadSession(sessionId) {
                    if (this.currentSessionId === sessionId) return;
                    if (this.currentSessionId && this._dirty) {
                        await this._doSave();
                    }
                    try {
                        const res = await fetch('./api/sessions/' + sessionId);
                        const data = await res.json();
                        if (data.status === 'success') {
                            this.currentSessionId = sessionId;
                            this.conversationHistory = (data.messages || []).map(function(m) {
                                return {
                                    id: m.id,
                                    role: m.role,
                                    content: m.content,
                                    image_url: m.image_path ? '/api/sessions/' + sessionId + '/images/' + m.image_path.split('/').pop() : null,
                                    file_name: m.file_name,
                                    file_path: m.file_path,
                                    created_at: m.created_at,
                                    timestamp: m.timestamp
                                };
                            });
                            localStorage.setItem('lastSessionId', sessionId);
                            this._dirty = false;
                            renderHistory();
                            ChatNav.render();
                            this._highlightActiveSession();
                            // 同步当前会话的 loading 状态
                            if (sessionLoading) {
                                sessionLoading.style.display = this.pendingSessions.has(sessionId) ? 'flex' : 'none';
                            }
                            // 切换会话时清理上传预览（图片/文件/摄像头），防止附件泄漏到新会话
                            pendingImageBase64 = null;
                            clearUpload();
                            clearFilePreview();
                            pendingFileContent = null;
                            pendingFileName = null;
                            closeCamera();
                            // 更新侧边栏标题
                            const s = this.sessions.find(function(s) { return s.id === sessionId; });
                            if (s && data.title && data.title !== s.title) {
                                s.title = data.title;
                                this._renderSessionList();
                            }
                        } else {
                            // 会话不存在（可能已被删除），从列表中移除并刷新
                            console.warn('[AppState] loadSession: session not found, removing from list:', sessionId);
                            this.sessions = this.sessions.filter(function(s) { return s.id !== sessionId; });
                            this._renderSessionList();
                            showToast('该会话不存在或已被删除');
                        }
                    } catch (e) {
                        console.error('[AppState] loadSession failed:', e);
                    }
                },

                async createNewSession() {
                    try {
                        const res = await fetch('./api/sessions/new', { method: 'POST' });
                        const data = await res.json();
                        if (data.status === 'success') {
                            this.currentSessionId = data.id;
                            this.conversationHistory = [];
                            this.sessions.unshift({
                                id: data.id,
                                title: data.title || '新对话',
                                created_at: data.created_at,
                                updated_at: data.updated_at,
                                message_count: 0,
                                is_archived: false
                            });
                            localStorage.setItem('lastSessionId', data.id);
                            this._dirty = false;
                            renderHistory();
                            this._renderSessionList();
                            this._highlightActiveSession();
                            // 清空图片上下文
                            lastImageBase64 = null;
                            imageHistory = [];
                            pendingImageBase64 = null;
                            clearUpload();
                            clearFilePreview();
                            pendingFileContent = null;
                            pendingFileName = null;
                            closeCamera();
                        }
                    } catch (e) {
                        console.error('[AppState] createNewSession failed:', e);
                    }
                },

                async deleteSession(sessionId, sessionTitle) {
                    const ok = await Modal.show({
                        title: '删除会话',
                        message: '确定要删除会话「' + (sessionTitle || '新对话') + '」吗？此操作不可恢复。',
                        confirmText: '删除',
                        cancelText: '取消'
                    });
                    if (!ok) return;
                    try {
                        const res = await fetch('./api/sessions/' + sessionId, { method: 'DELETE' });
                        const data = await res.json();
                        if (data.status === 'success') {
                            this.sessions = this.sessions.filter(function(s) { return s.id !== sessionId; });
                            // 清除 localStorage 中残留的 lastSessionId
                            if (localStorage.getItem('lastSessionId') === sessionId) {
                                localStorage.removeItem('lastSessionId');
                                // console.log('[AppState] deleteSession: cleared lastSessionId from localStorage');
                            }
                            if (this.currentSessionId === sessionId) {
                                this.currentSessionId = null;
                                if (this.sessions.length > 0) {
                                    await this.loadSession(this.sessions[0].id);
                                } else {
                                    await this.createNewSession();
                                }
                            }
                            this._renderSessionList();
                        } else {
                            // 删除失败（可能已被其他客户端删除），刷新列表
                            console.warn('[AppState] deleteSession failed on server, refreshing list');
                            await this.loadSessions();
                        }
                    } catch (e) {
                        console.error('[AppState] deleteSession failed:', e);
                    }
                },

                async renameSession(sessionId, newTitle) {
                    try {
                        const res = await fetch('./api/sessions/' + sessionId, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ title: newTitle })
                        });
                        const data = await res.json();
                        if (data.status === 'success') {
                            const s = this.sessions.find(function(s) { return s.id === sessionId; });
                            if (s) s.title = newTitle;
                            this._renderSessionList();
                        }
                    } catch (e) {
                        console.error('[AppState] renameSession failed:', e);
                    }
                },

                pushMessage(msg) {
                    this.conversationHistory.push(msg);
                    this._dirty = true;
                    debounceSave();
                },

                _renderSessionList() {
                    const listEl = document.getElementById('session-list');
                    if (!listEl) return;
                    listEl.innerHTML = '';
                    this.sessions.forEach(function(s) {
                        const item = document.createElement('div');
                        item.className = 'session-item' + (s.id === AppState.currentSessionId ? ' active' : '');
                        item.dataset.id = s.id;
                        const titleText = escapeHtml(s.title || '新对话');
                        const metaText = formatDateTime(s.updated_at) + ' · ' + (s.message_count || 0) + '条';
                        const pendingSpinner = AppState.pendingSessions.has(s.id) ? '<span class="session-pending-spinner" title="小月正在思考与回答..."></span>' : '';
                        item.innerHTML = '<div class="session-item-main"><span class="session-title">' + titleText + pendingSpinner + '</span><span class="session-meta">' + metaText + '</span></div><button class="session-more-btn" title="更多">⋯</button><div class="session-menu" style="display:none;"><div class="session-menu-item" data-action="rename">✏️ 重命名</div><div class="session-menu-item" data-action="delete">🗑️ 删除</div></div>';

                        const mainEl = item.querySelector('.session-item-main');
                        if (mainEl) {
                            mainEl.onclick = function() { AppState.loadSession(s.id); };
                        }

                        const moreBtn = item.querySelector('.session-more-btn');
                        const menu = item.querySelector('.session-menu');
                        if (moreBtn && menu) {
                            moreBtn.onclick = function(e) {
                                e.stopPropagation();
                                document.querySelectorAll('.session-menu').forEach(function(m) {
                                    if (m !== menu) m.style.display = 'none';
                                });
                                menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
                            };
                        }

                        item.querySelectorAll('.session-menu-item').forEach(function(menuItem) {
                            menuItem.onclick = function(e) {
                                e.stopPropagation();
                                if (menu) menu.style.display = 'none';
                                const action = menuItem.dataset.action;
                                if (action === 'rename') {
                                    Modal.show({
                                        title: '重命名会话',
                                        message: '请输入新的会话标题：',
                                        showInput: true,
                                        inputValue: s.title || '新对话',
                                        confirmText: '确认',
                                        cancelText: '取消'
                                    }).then(function(newTitle) {
                                        if (newTitle !== false && newTitle.trim() !== '') {
                                            AppState.renameSession(s.id, newTitle.trim());
                                        }
                                    });
                                } else if (action === 'delete') {
                                    AppState.deleteSession(s.id, s.title);
                                }
                            };
                        });

                        listEl.appendChild(item);
                    });
                },

                _highlightActiveSession() {
                    document.querySelectorAll('.session-item').forEach(function(el) {
                        el.classList.toggle('active', el.dataset.id === AppState.currentSessionId);
                    });
                },

                _applySidebarState() {
                    const sidebar = document.getElementById('session-sidebar');
                    const expandBtn = document.getElementById('sidebar-expand-btn');
                    if (sidebar) sidebar.classList.toggle('collapsed', !this.isSidebarOpen);
                    if (expandBtn) expandBtn.style.display = this.isSidebarOpen ? 'none' : 'inline-block';
                },

                async _doSave() {
                    if (!this.currentSessionId || !this._dirty || this._isSaving) return;
                    this._isSaving = true;
                    try {
                        // 转换消息字段：image_url(URL格式) -> image_path，避免覆盖后端已保存的图片路径
                        const messages = this.conversationHistory.map(function(msg) {
                            const mapped = {
                                role: msg.role,
                                content: msg.content,
                                file_name: msg.file_name,
                                file_path: msg.file_path,
                                timestamp: msg.timestamp
                            };
                            if (msg.image_url && typeof msg.image_url === 'string' && msg.image_url.startsWith('/api/sessions/')) {
                                mapped.image_path = msg.image_url.split('/').pop();
                            } else if (msg.image_path) {
                                mapped.image_path = msg.image_path;
                            }
                            return mapped;
                        });
                        await fetch('./api/sessions/' + this.currentSessionId + '/save', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ messages: messages })
                        });
                        this._dirty = false;
                    } catch (e) {
                        console.error('[AppState] save failed:', e);
                    } finally {
                        this._isSaving = false;
                    }
                }
            };

            function debounceSave() {
                AppState._dirty = true;
                if (AppState._saveTimer) clearTimeout(AppState._saveTimer);
                AppState._saveTimer = setTimeout(function() {
                    AppState._doSave();
                }, 5000);
            }

            window.addEventListener('beforeunload', function() {
                if (AppState._dirty && AppState.currentSessionId) {
                    const messages = AppState.conversationHistory.map(function(msg) {
                        const mapped = {
                            role: msg.role,
                            content: msg.content,
                            file_name: msg.file_name,
                            file_path: msg.file_path,
                            timestamp: msg.timestamp
                        };
                        if (msg.image_url && typeof msg.image_url === 'string' && msg.image_url.startsWith('/api/sessions/')) {
                            mapped.image_path = msg.image_url.split('/').pop();
                        } else if (msg.image_path) {
                            mapped.image_path = msg.image_path;
                        }
                        return mapped;
                    });
                    const data = JSON.stringify({ messages: messages });
                    navigator.sendBeacon(
                        '/api/sessions/' + AppState.currentSessionId + '/save',
                        new Blob([data], { type: 'application/json' })
                    );
                }
            });

            // ===== 图片上下文记忆 =====
            let lastImageBase64 = null;
            let imageHistory = [];
            const VISUAL_KEYWORDS = ['图', '图片', '画面', '照片', '这张', '图中', '图里', '图上',
                                     '画像', '截图', '相片', '拍的照片', '刚才的图', '这张图片',
                                     'image', 'picture', 'photo', 'pic', 'look at', 'what is in'];
            function isVisualQuestion(text) {
                if (!text) return false;
                return VISUAL_KEYWORDS.some(function(kw) { return text.includes(kw); });
            }
            function findImageByContext(text) {
                if (!text || imageHistory.length === 0) return lastImageBase64;
                if (text.includes('这张')) {
                    return lastImageBase64;
                }
                if (text.includes('上一张') || text.includes('刚才') || text.includes('之前') || text.includes('前一张')) {
                    return imageHistory.length > 1 ? imageHistory[imageHistory.length - 2].base64 : lastImageBase64;
                }
                return lastImageBase64;
            }
            function hasPrevImageRef(text) {
                if (!text) return false;
                return ['上一张', '前一张', '刚才', '之前', '前一张图'].some(function(kw) { return text.includes(kw); });
            }

            // ===== 图片/文件/摄像头上传逻辑 =====
            let pendingImageBase64 = null;
            let pendingFileContent = null;
            let pendingFileName = null;
            let camStream = null;

            function handleImageUpload(input) {
                // console.log('[Upload] handleImageUpload 被调用, files:', input.files ? input.files.length : 0);
                const file = input.files[0];
                if (!file) {
                    // console.log('[Upload] 未选择文件');
                    input.value = '';
                    return;
                }
                input.value = '';
                if (file.size > 5 * 1024 * 1024) {
                    alert('图片不能超过 5MB');
                    input.value = '';
                    return;
                }
                // console.log('[Upload] 开始读取文件:', file.name, '大小:', file.size);
                const reader = new FileReader();
                reader.onload = function(e) {
                    // console.log('[Upload] 文件读取成功');
                    pendingImageBase64 = e.target.result;
                    showImagePreview(pendingImageBase64, file.name);
                };
                reader.onerror = function(e) {
                    console.error('[Upload] 文件读取失败:', e);
                    alert('图片读取失败');
                    input.value = '';
                };
                reader.readAsDataURL(file);
            }
            window.handleImageUpload = handleImageUpload;

            function showFilePreview(name, preview) {
                document.getElementById('file-preview-name').textContent = '📄 ' + name;
                document.getElementById('file-preview-content').textContent = preview + (preview.length >= 100 ? '...' : '');
                document.getElementById('file-preview').style.display = 'block';
            }

            function handleFileUpload(input) {
                const file = input.files[0];
                if (!file) return;

                const maxSize = 10 * 1024 * 1024; // 10MB
                const allowedExts = ['.txt', '.md', '.pdf', '.docx'];
                const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();

                if (!allowedExts.includes(ext)) {
                    showToast('暂不支持该文件格式，请上传 .txt/.md/.pdf/.docx 文件');
                    input.value = '';
                    return;
                }
                if (file.size > maxSize) {
                    showToast('文件过大，请上传 10MB 以内的文件');
                    input.value = '';
                    return;
                }

                // txt/md 保持原有逻辑（readAsText）
                if (ext === '.txt' || ext === '.md') {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        pendingFileContent = e.target.result;
                        pendingFileName = file.name;
                        showFilePreview(file.name, pendingFileContent.substring(0, 100));
                    };
                    reader.onerror = function() {
                        showToast('文件读取失败');
                    };
                    reader.readAsText(file);
                    input.value = '';
                    return;
                }

                // pdf/docx 通过 FormData 上传到后端解析
                const formData = new FormData();
                formData.append('file', file);

                showToast('正在解析文件...');

                const controller = new AbortController();
                const timeoutId = setTimeout(function() { controller.abort(); }, 10000); // 10秒超时

                apiFetch('/api/parse_file', {
                    method: 'POST',
                    body: formData,
                    signal: controller.signal,
                    skipStatusCheck: true
                })
                .then(function(data) {
                    clearTimeout(timeoutId);
                    if (data.status === 'success') {
                        pendingFileContent = data.text;
                        pendingFileName = file.name;
                        showFilePreview(file.name, pendingFileContent.substring(0, 100));
                        if (data.truncated) {
                            showToast('文件过长，已截取前 100KB');
                        }
                    } else {
                        showToast(data.message || '文件解析失败');
                    }
                })
                .catch(function(err) {
                    clearTimeout(timeoutId);
                    if (err.name === 'AbortError') {
                        showToast('文件解析超时，请重试或分割文件');
                    } else {
                        console.error('文件解析失败:', err);
                        // apiFetch 已对网络错误显示 toast，此处避免重复
                        if (!(err.message && err.message.includes('fetch'))) {
                            showToast('文件解析失败，请检查服务状态');
                        }
                    }
                });

                input.value = '';
            }
            window.handleFileUpload = handleFileUpload;

            function clearFilePreview() {
                pendingFileContent = null;
                pendingFileName = null;
                document.getElementById('file-preview').style.display = 'none';
                document.getElementById('file-preview-name').textContent = '';
                document.getElementById('file-preview-content').textContent = '';
            }
            window.clearFilePreview = clearFilePreview;

            function showImagePreview(base64, filename) {
                const preview = document.getElementById('upload-preview');
                preview.innerHTML = '<img src="' + base64 + '" alt="preview"><span>' + filename + '</span><button onclick="clearUpload()" title="删除">✕</button>';
                preview.style.display = 'flex';
            }

            window.clearUpload = function() {
                pendingImageBase64 = null;
                const preview = document.getElementById('upload-preview');
                preview.innerHTML = '';
                preview.style.display = 'none';
            };

            window.toggleCamera = async function() {
                const panel = document.getElementById('camera-panel');
                if (panel.style.display === 'block') {
                    closeCamera();
                    return;
                }
                try {
                    camStream = await navigator.mediaDevices.getUserMedia({ video: true });
                    const video = document.getElementById('cam-video');
                    video.srcObject = camStream;
                    video.onloadedmetadata = function() {
                        panel.style.display = 'block';
                        // console.log('[Camera] 视频已准备好, 尺寸:', video.videoWidth, 'x', video.videoHeight);
                    };
                } catch (err) {
                    alert('无法访问摄像头：' + err.message);
                }
            };

            window.capturePhoto = function() {
                const video = document.getElementById('cam-video');
                if (!video.videoWidth || !video.videoHeight) {
                    alert('摄像头画面还没准备好，请稍等片刻再试');
                    return;
                }
                const canvas = document.getElementById('cam-canvas');
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = '#000000';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                pendingImageBase64 = canvas.toDataURL('image/jpeg', 0.92);
                // console.log('[Camera] 拍照成功, 尺寸:', canvas.width, 'x', canvas.height, 'base64长度:', pendingImageBase64 ? pendingImageBase64.length : 0);
                if (pendingImageBase64.length < 2000) {
                    console.warn('[Camera] 警告: 图片数据异常偏小，可能是空白帧');
                }
                showImagePreview(pendingImageBase64, '摄像头照片');
                closeCamera();
            };

            window.closeCamera = function() {
                if (camStream) {
                    camStream.getTracks().forEach(function(t) { t.stop(); });
                    camStream = null;
                }
                document.getElementById('camera-panel').style.display = 'none';
            };

            window.toggleUploadMenu = function(event) {
                if (event) event.stopPropagation();
                const menu = document.getElementById('upload-menu');
                if (!menu) return;
                const isHidden = menu.style.display === 'none';
                menu.style.display = isHidden ? 'block' : 'none';
            };

            // 点击页面其他区域关闭上传菜单
            document.addEventListener('click', function(event) {
                const menu = document.getElementById('upload-menu');
                const wrapper = document.querySelector('.upload-menu-wrapper');
                if (menu && wrapper && !wrapper.contains(event.target)) {
                    menu.style.display = 'none';
                }
            });

            // ===== 拖拽上传 =====
            const chatMessagesEl = document.getElementById('chat_messages');
            chatMessagesEl.addEventListener('dragover', function(e) {
                e.preventDefault();
                chatMessagesEl.classList.add('drag-over');
            });
            chatMessagesEl.addEventListener('dragleave', function() {
                chatMessagesEl.classList.remove('drag-over');
            });
            chatMessagesEl.addEventListener('drop', function(e) {
                e.preventDefault();
                chatMessagesEl.classList.remove('drag-over');
                const files = e.dataTransfer.files;
                for (let file of files) {
                    if (file.type.startsWith('image/')) {
                        if (file.size > 5 * 1024 * 1024) {
                            alert('图片不能超过 5MB');
                            continue;
                        }
                        const reader = new FileReader();
                        reader.onload = function(ev) {
                            pendingImageBase64 = ev.target.result;
                            showImagePreview(pendingImageBase64, file.name);
                        };
                        reader.readAsDataURL(file);
                    }
                }
            });

            function updateInfo() {
                fetch('./api/info')
                   .then(function(response) { return response.json(); })
                   .then(function(data) {
                        document.getElementById('cpu_percent').textContent = data.cpu_percent + '%';
                        document.getElementById('memory_percent').textContent = data.memory_percent + '%';
                        document.getElementById('temp').textContent = data.temp + '℃';
                        document.getElementById('wan_info').textContent = data.wan_info;
                        document.getElementById('lan_info').textContent = data.lan_info;
                        document.getElementById('wifi_info').textContent = data.wifi_info;
                        const cpuExp = document.getElementById('cpu_percent_exp');
                        const memExp = document.getElementById('memory_percent_exp');
                        const tempExp = document.getElementById('temp_exp');
                        const wanExp = document.getElementById('wan_info_exp');
                        const lanExp = document.getElementById('lan_info_exp');
                        const wifiExp = document.getElementById('wifi_info_exp');
                        if (cpuExp) cpuExp.textContent = data.cpu_percent + '%';
                        if (memExp) memExp.textContent = data.memory_percent + '%';
                        if (tempExp) tempExp.textContent = data.temp + '℃';
                        if (wanExp) wanExp.textContent = data.wan_info;
                        if (lanExp) lanExp.textContent = data.lan_info;
                        if (wifiExp) wifiExp.textContent = data.wifi_info;
                        live2dUrl.href = data.live2d_url;
                        mmdUrl.href = data.mmd_url;
                        vmdUrl.href = data.vmd_url;
                        vrmUrl.href = data.vrm_url;
                        settingsUrl.href = data.settings_url;
                    })
                   .catch(function(error) {
                        console.error('Error fetching data:', error);
                    });
            }

            // ===== 流式 VLM 消息处理 =====
            async function sendStreamMessage(message, imageBase64) {
                const requestSessionId = AppState.currentSessionId;
                const streamId = 'stream_' + Date.now();

                // 1. 创建占位消息气泡（带 loading 提示）
                const msgDiv = appendMessage({
                    role: 'assistant',
                    content: '正在分析图片…',
                    streamId: streamId
                });
                // 标记为 loading 状态，收到首 token 后替换
                msgDiv.setAttribute('data-stream-loading', 'true');

                // 2. 提前释放 _submitState.isSubmitting，允许用户继续输入
                _submitState.isSubmitting = false;
                updateInputState();

                // 隐藏 session-loading spinner（流式模式用占位消息替代）
                if (sessionLoading) {
                    sessionLoading.style.display = 'none';
                }

                // 3. 建立 SSE 连接（fetch + ReadableStream）
                // 不设置前端超时，由后端 120 秒 API 超时控制
                // K2.6 处理图片可能需要 60 秒以上才开始返回数据
                const response = await fetch('./api/vlm_stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: message,
                        session_id: AppState.currentSessionId,
                        image_base64: imageBase64
                    })
                });

                try {

                    if (!response.ok) {
                        throw new Error('SSE 请求失败: ' + response.status);
                    }

                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';
                    let fullText = '';
                    let firstTokenReceived = false;

                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;

                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n\n');
                        buffer = lines.pop(); // 保留未完整行

                        for (let i = 0; i < lines.length; i++) {
                            const line = lines[i];
                            if (line.startsWith('data: ')) {
                                try {
                                    const data = JSON.parse(line.slice(6));
                                    if (data.type === 'token') {
                                        // 首 token：清除 loading 提示，开始显示真实内容
                                        if (!firstTokenReceived) {
                                            firstTokenReceived = true;
                                            const loadingMsgDiv = document.querySelector('[data-stream-loading="true"][data-stream-id="' + streamId + '"]');
                                            if (loadingMsgDiv) {
                                                const contentDiv = loadingMsgDiv.querySelector('.message-content');
                                                if (contentDiv) {
                                                    contentDiv.textContent = ''; // 清除 "正在分析图片…"
                                                }
                                                loadingMsgDiv.removeAttribute('data-stream-loading');
                                            }
                                        }
                                        appendStreamToken(streamId, data.content);
                                        fullText += data.content;
                                    } else if (data.type === 'done') {
                                        finalizeStreamMessage(streamId, data.full_text || fullText, requestSessionId);
                                        AppState.pendingSessions.delete(requestSessionId);
                                        AppState._renderSessionList();
                                        reader.cancel();
                                        return;
                                    } else if (data.type === 'error') {
                                        showToast('流式响应出错: ' + data.message);
                                        AppState.pendingSessions.delete(requestSessionId);
                                        if (sessionLoading) sessionLoading.style.display = 'none';
                                        AppState._renderSessionList();
                                        // fallback：调用同步 /api/chat
                                        sendNormalMessage(message, imageBase64);
                                        reader.cancel();
                                        return;
                                    }
                                } catch (e) {
                                    console.error('[SSE] 解析数据失败:', e, line);
                                }
                            }
                        }
                    }

                    // 流正常结束但未收到 done（异常情况）
                    finalizeStreamMessage(streamId, fullText, requestSessionId);
                    AppState.pendingSessions.delete(requestSessionId);
                    AppState._renderSessionList();

                } catch (err) {
                    console.error('[SSE] 连接失败:', err);
                    AppState.pendingSessions.delete(requestSessionId);
                    if (sessionLoading) sessionLoading.style.display = 'none';
                    AppState._renderSessionList();
                    showToast('流式连接失败，尝试同步模式');
                    // fallback 到同步模式
                    sendNormalMessage(message, imageBase64);
                }
            }

            function appendStreamToken(streamId, token) {
                const msgDiv = document.querySelector('[data-stream-id="' + streamId + '"]');
                if (!msgDiv) return;
                const contentDiv = msgDiv.querySelector('.message-content');
                if (!contentDiv) return;

                // 追加文本（不使用 innerHTML +=，避免 XSS）
                const textNode = document.createTextNode(token);
                contentDiv.appendChild(textNode);

                autoScroll();
            }

            function finalizeStreamMessage(streamId, fullText, requestSessionId) {
                // 1. 更新 DOM（仅当消息仍在当前显示区域时）
                const msgDiv = document.querySelector('[data-stream-id="' + streamId + '"]');
                if (msgDiv) {
                    msgDiv.removeAttribute('data-stream-id');
                }

                // 2. 保存到后端（必须用请求时的 sessionId，不能用 AppState.currentSessionId）
                if (requestSessionId) {
                    fetch('./api/sessions/' + requestSessionId + '/save', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            messages: [{
                                role: 'assistant',
                                content: fullText,
                                timestamp: Date.now() / 1000
                            }]
                        })
                    }).catch(function(err) { console.error('[Stream] 保存消息失败:', err); });
                }

                // 3. 触发 TTS 自动朗读（仅当用户仍在原会话时）
                if (autoVoiceCheckbox.checked && window.userInteracted && AppState.currentSessionId === requestSessionId) {
                    fetch('./api/tts_segment', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({text: fullText, session_id: requestSessionId})
                    })
                    .then(function(r) { return r.json(); })
                    .then(function(ttsData) {
                        if (ttsData.status === 'success' && ttsData.audio_urls && ttsData.audio_urls.length > 0) {
                            playTtsQueue(ttsData.audio_urls, null);
                            if (ttsData.batch_id && ttsData.total > 1) {
                                startTtsPoll(ttsData.batch_id, ttsData.total);
                            }
                        }
                    })
                    .catch(function(err) {
                        console.error('[Stream] TTS 请求失败:', err);
                    });
                }
            }

            function autoScroll() {
                if (chatMessages) {
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                }
            }

            // ===== 同步消息发送（fallback 或纯文本路径） =====
            async function sendNormalMessage(message, imageBase64, prevImageBase64, fileContent, fileName) {
                const requestSessionId = AppState.currentSessionId;
                const payload = {
                    message: message,
                    session_id: requestSessionId
                };
                if (imageBase64) {
                    payload.image_base64 = imageBase64;
                }
                if (prevImageBase64) {
                    payload.prev_image_base64 = prevImageBase64;
                }
                if (fileContent && fileName) {
                    payload.file_content = fileContent;
                    payload.file_name = fileName;
                }

                fetch('./api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
                .then(function(response) {
                    return response.json();
                })
                .then(function(data) {
                    AppState.pendingSessions.delete(requestSessionId);
                    if (sessionLoading) {
                        sessionLoading.style.display = 'none';
                    }
                    AppState._renderSessionList();

                    if (data.status === 'success') {
                        const assistantMsg = {
                            role: 'assistant',
                            content: data.response,
                            timestamp: Date.now() / 1000
                        };
                        // 只有用户仍在原会话时才更新 DOM，否则消息已保存在后端，切回会话时会自动加载
                        if (AppState.currentSessionId === requestSessionId) {
                            AppState.pushMessage(assistantMsg);
                            appendMessage(assistantMsg);
                        }

                        if (autoVoiceCheckbox.checked && window.userInteracted && AppState.currentSessionId === requestSessionId) {
                            fetch('./api/tts_segment', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({text: data.response, session_id: requestSessionId})
                            })
                            .then(function(r) { return r.json(); })
                            .then(function(ttsData) {
                                if (ttsData.status === 'success' && ttsData.audio_urls && ttsData.audio_urls.length > 0) {
                                    playTtsQueue(ttsData.audio_urls, null);
                                    _submitState.isSubmitting = false;
                                    if (ttsData.batch_id && ttsData.total > 1) {
                                        startTtsPoll(ttsData.batch_id, ttsData.total);
                                    }
                                } else {
                                    _submitState.isSubmitting = false;
                                }
                            })
                            .catch(function(err) {
                                console.error('TTS 请求失败:', err);
                                _submitState.isSubmitting = false;
                            });
                        } else {
                            _submitState.isSubmitting = false;
                        }
                    } else {
                        const errorMsg = {
                            role: 'assistant',
                            content: '抱歉，处理您的请求时出现错误: ' + (data.message || '未知错误'),
                            timestamp: Date.now() / 1000
                        };
                        AppState.pushMessage(errorMsg);
                        appendMessage(errorMsg);
                        _submitState.isSubmitting = false;
                    }
                })
                .catch(function(error) {
                    AppState.pendingSessions.delete(requestSessionId);
                    if (sessionLoading) {
                        sessionLoading.style.display = 'none';
                    }
                    AppState._renderSessionList();
                    console.error('[Send] 请求失败:', error);
                    const errorMsg = {
                        role: 'assistant',
                        content: '抱歉，发送消息时出现错误，请稍后再试。',
                        timestamp: Date.now() / 1000
                    };
                    if (AppState.currentSessionId === requestSessionId) {
                        AppState.pushMessage(errorMsg);
                        appendMessage(errorMsg);
                    }
                    _submitState.isSubmitting = false;
                });
            }

            function updateInputState() {
                const sendBtn = document.getElementById('send_button');
                const chatInput = document.getElementById('chat_input');
                if (sendBtn) {
                    sendBtn.disabled = _submitState.isSubmitting;
                }
                if (chatInput) {
                    chatInput.disabled = _submitState.isSubmitting;
                }
            }

            // ===== 发送消息流程（session 感知） =====
            document.getElementById('send_button').addEventListener('click', async function() {
                let message = document.getElementById('chat_input').value;
                if (message.trim() === '' && !pendingImageBase64 && !pendingFileContent) {
                    return;
                }

                // 前置校验
                if (_submitState.isSubmitting) return;
                _submitState.isSubmitting = true;
                updateInputState();

                // 确保有 session_id
                if (!AppState.currentSessionId) {
                    await AppState.createNewSession();
                }

                let finalImageBase64 = pendingImageBase64;
                let prevImageBase64 = null;
                if (!finalImageBase64 && isVisualQuestion(message) && lastImageBase64) {
                    finalImageBase64 = findImageByContext(message);
                }
                if (finalImageBase64 && hasPrevImageRef(message) && imageHistory.length >= 2) {
                    prevImageBase64 = imageHistory[imageHistory.length - 2].base64;
                }
                if (finalImageBase64 && message.trim() === '') {
                    message = '请描述这张图片';
                }

                // 前端显示用户消息
                const userMsg = {
                    role: 'user',
                    content: message,
                    image_url: finalImageBase64 || null,
                    file_name: pendingFileName || null,
                    timestamp: Date.now() / 1000
                };
                AppState.pushMessage(userMsg);
                appendMessage(userMsg);

                document.getElementById('chat_input').value = '';
                stopTts();

                const requestSessionId = AppState.currentSessionId;
                AppState.pendingSessions.add(requestSessionId);
                if (requestSessionId === AppState.currentSessionId && sessionLoading) {
                    sessionLoading.style.display = 'flex';
                    if (chatMessages) {
                        chatMessages.scrollTop = chatMessages.scrollHeight;
                    }
                }
                AppState._renderSessionList();

                // 图片上下文更新
                if (finalImageBase64 && !lastImageBase64) {
                    lastImageBase64 = finalImageBase64;
                    imageHistory.push({base64: finalImageBase64, time: Date.now()});
                } else if (finalImageBase64 && finalImageBase64 !== lastImageBase64) {
                    lastImageBase64 = finalImageBase64;
                    imageHistory.push({base64: finalImageBase64, time: Date.now()});
                    if (imageHistory.length > 5) imageHistory.shift();
                }
                pendingImageBase64 = null;
                clearUpload();
                clearFilePreview();
                const fileContent = pendingFileContent;
                const fileName = pendingFileName;
                pendingFileContent = null;
                pendingFileName = null;

                // 判断走流式还是同步
                if (finalImageBase64 && preferVlm !== 'off') {
                    // 含图片且 VLM 启用 → 走流式
                    sendStreamMessage(message, finalImageBase64);
                } else {
                    // 纯文本或 VLM 关闭 → 走同步
                    sendNormalMessage(message, finalImageBase64, prevImageBase64, fileContent, fileName);
                }
            });

            document.getElementById('chat_input').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    document.getElementById('send_button').click();
                }
            });

            // ===== clearButton 改造：新建会话 =====
            clearButton.addEventListener('click', function() {
                AppState.createNewSession();
            });

            // ===== 浏览器麦克风连续监听与自动断句 =====
            const SILENCE_THRESHOLD = 20;
            const SILENCE_DURATION = 2000;
            const MAX_SEGMENT_DURATION = 12000;

            let micStream = null;
            let micAudioCtx = null;
            let vadAnalyser = null;
            let vadRafId = null;
            let silenceTimer = null;
            let maxListenTimer = null;
            let lastVadLog = 0;

            let isListening = false;
            let isRecordingSegment = false;
            const _submitState = {};
            Object.defineProperty(_submitState, "isSubmitting", {
                get: function() { return this._val; },
                set: function(v) {
                    if (this._val !== v) { this._val = v; updateInputState(); }
                }
            });
            _submitState.isSubmitting = false;
            let currentSegmentRecorder = null;
            let voiceprintHintShown = false;

            function appendSystemMessage(htmlContent) {
                const chatBox = document.getElementById('chat_messages');
                const div = document.createElement('div');
                div.className = 'system-message';

                const wrapper = document.createElement('div');
                const bubble = document.createElement('div');
                bubble.className = 'system-bubble';
                const icon = document.createElement('span');
                icon.className = 'system-icon';
                icon.textContent = 'ℹ️';
                const text = document.createElement('span');
                text.className = 'system-text';
                // 使用 innerHTML 渲染后端返回的富文本链接，但内容由服务端控制
                text.innerHTML = htmlContent;
                bubble.appendChild(icon);
                bubble.appendChild(text);
                wrapper.appendChild(bubble);
                const timeDiv = document.createElement('div');
                timeDiv.className = 'system-time';
                timeDiv.textContent = new Date().toLocaleTimeString();
                wrapper.appendChild(timeDiv);
                div.appendChild(wrapper);
                chatBox.appendChild(div);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            async function checkVoiceprintBeforeRecord() {
                try {
                    const res = await fetch('./api/voiceprint_status');
                    const status = await res.json();
                    if (status.enabled && !status.bound && !voiceprintHintShown) {
                        voiceprintHintShown = true;
                        appendSystemMessage(
                            '🔐 声纹识别已开启，但您尚未绑定声纹样本。' +
                            '建议前往<a href="' + status.settings_url + '" target="_blank">系统设置 → 声纹识别</a>录制您的声音，防止他人误触发对话。' +
                            '（未绑定期间仍可正常使用语音输入）'
                        );
                    }
                } catch (e) {
                    // console.log('[Voiceprint] 检测失败，跳过提示', e);
                }
            }

            async function _toggleMic() {
                if (asrMode === 'hold') {
                    return;
                }
                checkVoiceprintBeforeRecord();

                if (isListening) {
                    _stopListening();
                    return;
                }
                try {
                    micStream = await navigator.mediaDevices.getUserMedia({audio: true});
                    micAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    const source = micAudioCtx.createMediaStreamSource(micStream);
                    vadAnalyser = micAudioCtx.createAnalyser();
                    vadAnalyser.fftSize = 512;
                    source.connect(vadAnalyser);

                    isListening = true;
                    _updateMicButton('🔴 监听中...');
                    // console.log('[Mic] 监听启动，开始 VAD 检测');

                    _detectSpeechLoop();

                    maxListenTimer = setTimeout(function() {
                        if (isListening) {
                            _stopListening();
                            appendSystemMessage('⏹️ 语音监听已自动关闭（10分钟超时）');
                        }
                    }, 10 * 60 * 1000);

                } catch (err) {
                    console.error('[Mic] 启动失败:', err);
                    alert('麦克风启动失败: ' + err.message);
                }
            }

            function _stopListening() {
                // console.log('[Mic] 正在停止监听...');
                isListening = false;
                isRecordingSegment = false;
                _submitState.isSubmitting = false;
                if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
                if (maxListenTimer) { clearTimeout(maxListenTimer); maxListenTimer = null; }
                if (currentSegmentRecorder && currentSegmentRecorder.state === 'recording') {
                    try { currentSegmentRecorder.stop(); } catch(e) {}
                }
                if (micStream) { micStream.getTracks().forEach(function(t) { t.stop(); }); micStream = null; }
                if (micAudioCtx) { micAudioCtx.close(); micAudioCtx = null; }
                if (vadRafId) { cancelAnimationFrame(vadRafId); vadRafId = null; }
                vadAnalyser = null;
                currentSegmentRecorder = null;
                _updateMicButton('🎤');
                // console.log('[Mic] 监听已完全停止');
            }

            function _updateMicButton(html) {
                const btn = document.getElementById('mic-btn');
                if (btn) {
                    btn.innerHTML = html;
                    if (asrMode === 'hold') {
                        btn.style.backgroundColor = (asrState === ASRState.RECORDING) ? '#cc0000' : '#660000';
                    } else {
                        btn.style.backgroundColor = isListening ? '#cc0000' : '#660000';
                    }
                }
            }

            function _detectSpeechLoop() {
                if (!isListening || !vadAnalyser) {
                    // console.log('[VAD] 检测循环退出');
                    return;
                }

                const dataArray = new Uint8Array(vadAnalyser.frequencyBinCount);
                vadAnalyser.getByteFrequencyData(dataArray);

                const voiceBand = dataArray.slice(2, 10);
                const avg = voiceBand.reduce(function(a, b) { return a + b; }, 0) / voiceBand.length;

                const now = Date.now();
                if (now - lastVadLog > 2000) {
                    // console.log('[VAD] 音量:', Math.round(avg), '阈值:', SILENCE_THRESHOLD,
                    //             '录音中:', isRecordingSegment, '提交中:', _submitState.isSubmitting);
                    lastVadLog = now;
                }

                if (_submitState.isSubmitting) {
                    if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
                    vadRafId = requestAnimationFrame(_detectSpeechLoop);
                    return;
                }

                if (avg > SILENCE_THRESHOLD) {
                    if (!isRecordingSegment) {
                        _startSegmentRecording();
                    }
                    if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
                } else {
                    if (isRecordingSegment && !silenceTimer) {
                        silenceTimer = setTimeout(function() {
                            // console.log('[VAD] 静音超时，触发断句');
                            _stopSegmentRecording();
                        }, SILENCE_DURATION);
                    }
                }

                vadRafId = requestAnimationFrame(_detectSpeechLoop);
            }

            function _startSegmentRecording() {
                if (isRecordingSegment || !micStream) {
                    console.warn('[Rec] 无法开始，isRecordingSegment:', isRecordingSegment, 'micStream:', !!micStream);
                    return;
                }

                currentSegmentRecorder = new MediaRecorder(micStream);
                let chunks = [];

                currentSegmentRecorder.ondataavailable = function(e) {
                    if (e.data && e.data.size > 0) {
                        chunks.push(e.data);
                        // console.log('[Rec] 收到音频块:', e.data.size, 'bytes, 当前总块数:', chunks.length);
                    }
                };

                currentSegmentRecorder.onstop = function() {
                    // console.log('[Rec] 录制停止，收集到', chunks.length, '块音频');
                    isRecordingSegment = false;
                    _updateMicButton('🔴 监听中...');

                    if (chunks.length === 0) {
                        console.warn('[Rec] 无音频数据，跳过提交');
                        return;
                    }
                    const blob = new Blob(chunks, { type: 'audio/webm' });
                    // console.log('[Rec] 生成 Blob:', blob.size, 'bytes');
                    _submitAudio(blob);
                };

                currentSegmentRecorder.onerror = function(e) {
                    console.error('[Rec] MediaRecorder 错误:', e);
                    isRecordingSegment = false;
                };

                isRecordingSegment = true;
                _updateMicButton('🔴 录音中...');
                // console.log('[Rec] 开始新录制段, MediaRecorder 状态:', currentSegmentRecorder.state);

                currentSegmentRecorder.start(100);

                setTimeout(function() {
                    if (isRecordingSegment && currentSegmentRecorder && currentSegmentRecorder.state === 'recording') {
                        // console.log('[Rec] 达到最大时长，强制截断');
                        currentSegmentRecorder.stop();
                    }
                }, MAX_SEGMENT_DURATION);
            }

            function _stopSegmentRecording() {
                if (!isRecordingSegment || !currentSegmentRecorder) {
                    // console.log('[Rec] 无需停止，isRecordingSegment:', isRecordingSegment);
                    return;
                }
                // console.log('[Rec] 触发停止, MediaRecorder 状态:', currentSegmentRecorder.state);
                if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
                if (currentSegmentRecorder.state === 'recording') {
                    currentSegmentRecorder.stop();
                }
            }

            async function _submitAudio(audioBlob) {
                if (_submitState.isSubmitting) {
                    // console.log('[ASR] 正在处理中，丢弃这段音频（防回声）');
                    return;
                }
                _submitState.isSubmitting = true;
                // console.log('[ASR] 提交音频，大小:', audioBlob.size, 'bytes');

                const formData = new FormData();
                formData.append('audio', audioBlob, 'voice.webm');

                try {
                    const res = await fetch('./api/asr', {
                        method: 'POST',
                        body: formData
                    });
                    // console.log('[ASR] 响应状态:', res.status);
                    const data = await res.json();
                    // console.log('[ASR] 返回:', data);

                    if (data.text && data.text.trim()) {
                        document.getElementById('chat_input').value = data.text.trim();
                        document.getElementById('send_button').click();
                        asrState = ASRState.IDLE;
                        _updateMicButton('🎤');
                    } else {
                        console.warn('[ASR] 返回空文本');
                        _submitState.isSubmitting = false;
                    }
                } catch (e) {
                    console.error('[ASR] 失败:', e);
                    _submitState.isSubmitting = false;
                }
            }

            window.toggleMic = _toggleMic;

            // ===== 按住说话模式 =====
            async function onHoldStart() {
                if (asrState !== ASRState.IDLE) return;
                if (asrMode !== 'hold') return;
                stopTts();
                asrState = ASRState.RECORDING;
                recordingStartTime = Date.now();
                audioChunks = [];
                try {
                    holdMicStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                        ? 'audio/webm;codecs=opus'
                        : 'audio/webm';
                    mediaRecorder = new MediaRecorder(holdMicStream, { mimeType: mimeType });
                    mediaRecorder.ondataavailable = function(e) {
                        if (e.data && e.data.size > 0) audioChunks.push(e.data);
                    };
                    mediaRecorder.onstop = function() {
                        if (asrState !== ASRState.PROCESSING) return;
                        if (audioChunks.length === 0) {
                            asrState = ASRState.IDLE;
                            _submitState.isSubmitting = false;
                            return;
                        }
                        const blob = new Blob(audioChunks, { type: 'audio/webm' });
                        _submitHoldAudio(blob);
                    };
                    mediaRecorder.start(100);
                    startWaveform(holdMicStream);
                    _updateMicButton('🔴 录音中...');
                } catch (err) {
                    console.error('[Hold] 启动失败:', err);
                    asrState = ASRState.IDLE;
                    showStatusToast('麦克风启动失败');
                }
            }

            function onHoldEnd() {
                if (asrState !== ASRState.RECORDING) return;
                const duration = Date.now() - recordingStartTime;
                stopWaveform();
                if (duration < 500) {
                    showStatusToast('说话时间太短，请重试');
                    if (mediaRecorder && mediaRecorder.state === 'recording') {
                        try { mediaRecorder.stop(); } catch(e) {}
                    }
                    cleanupHoldResources();
                    asrState = ASRState.IDLE;
                    _updateMicButton('🎤');
                    return;
                }
                asrState = ASRState.PROCESSING;
                _submitState.isSubmitting = true;
                _updateMicButton('⏳ 处理中...');
                if (mediaRecorder && mediaRecorder.state === 'recording') {
                    mediaRecorder.stop();
                }
            }

            async function _submitHoldAudio(audioBlob) {
                // console.log('[Hold] 提交音频，大小:', audioBlob.size, 'bytes');
                const formData = new FormData();
                formData.append('audio', audioBlob, 'voice.webm');
                try {
                    const res = await fetch('./api/asr', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    // console.log('[Hold] ASR 返回:', data);
                    if (data.text && data.text.trim()) {
                        document.getElementById('chat_input').value = data.text.trim();
                        document.getElementById('send_button').click();
                        asrState = ASRState.IDLE;
                        _updateMicButton('🎤');
                    } else {
                        showStatusToast('未能识别语音，请重试');
                        _submitState.isSubmitting = false;
                        asrState = ASRState.IDLE;
                        _updateMicButton('🎤');
                    }
                } catch (e) {
                    console.error('[Hold] ASR 失败:', e);
                    showStatusToast('语音识别失败');
                    _submitState.isSubmitting = false;
                    asrState = ASRState.IDLE;
                    _updateMicButton('🎤');
                }
                cleanupHoldResources();
            }

            function cleanupHoldResources() {
                if (holdMicStream) {
                    holdMicStream.getTracks().forEach(function(t) { t.stop(); });
                    holdMicStream = null;
                }
                if (holdAudioCtx) {
                    holdAudioCtx.close();
                    holdAudioCtx = null;
                }
                if (holdWaveformRaf) {
                    cancelAnimationFrame(holdWaveformRaf);
                    holdWaveformRaf = null;
                }
                const waveCanvas = document.getElementById('waveform-canvas');
                if (waveCanvas && waveCanvas.parentNode) {
                    waveCanvas.parentNode.removeChild(waveCanvas);
                }
                holdAnalyser = null;
                holdDataArray = null;
                mediaRecorder = null;
                audioChunks = [];
            }

            function startWaveform(stream) {
                let canvas = document.getElementById('waveform-canvas');
                if (!canvas) {
                    canvas = document.createElement('canvas');
                    canvas.id = 'waveform-canvas';
                    canvas.width = 200;
                    canvas.height = 40;
                    const voiceBar = document.querySelector('.voice-bar');
                    if (voiceBar) voiceBar.appendChild(canvas);
                }
                canvas.style.display = 'block';
                holdAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const source = holdAudioCtx.createMediaStreamSource(stream);
                holdAnalyser = holdAudioCtx.createAnalyser();
                holdAnalyser.fftSize = 256;
                source.connect(holdAnalyser);
                holdDataArray = new Uint8Array(holdAnalyser.frequencyBinCount);
                drawWaveform();
            }

            function drawWaveform() {
                if (!holdAnalyser || asrState !== ASRState.RECORDING) return;
                const canvas = document.getElementById('waveform-canvas');
                if (!canvas) return;
                const ctx = canvas.getContext('2d');
                const w = canvas.width;
                const h = canvas.height;
                holdAnalyser.getByteFrequencyData(holdDataArray);
                ctx.clearRect(0, 0, w, h);
                const barCount = 30;
                const barWidth = w / barCount;
                const step = Math.floor(holdDataArray.length / barCount);
                for (let i = 0; i < barCount; i++) {
                    const val = holdDataArray[i * step];
                    const barHeight = (val / 255) * h * 0.9;
                    const x = i * barWidth;
                    const y = h - barHeight;
                    ctx.fillStyle = '#4fc3f7';
                    ctx.fillRect(x + 1, y, barWidth - 2, barHeight);
                }
                holdWaveformRaf = requestAnimationFrame(drawWaveform);
            }

            function stopWaveform() {
                if (holdWaveformRaf) {
                    cancelAnimationFrame(holdWaveformRaf);
                    holdWaveformRaf = null;
                }
                const canvas = document.getElementById('waveform-canvas');
                if (canvas) {
                    const ctx = canvas.getContext('2d');
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    canvas.style.display = 'none';
                }
            }

            // 空格键快捷键
            let spaceKeyPressed = false;
            document.addEventListener('keydown', function(e) {
                if (e.code === 'Space' && document.activeElement !== document.getElementById('chat_input')) {
                    if (!spaceKeyPressed && asrMode === 'hold' && asrState === ASRState.IDLE) {
                        e.preventDefault();
                        spaceKeyPressed = true;
                        onHoldStart();
                    }
                }
            });
            document.addEventListener('keyup', function(e) {
                if (e.code === 'Space' && spaceKeyPressed) {
                    e.preventDefault();
                    spaceKeyPressed = false;
                    onHoldEnd();
                }
            });

            // 麦克风按钮按住说话事件绑定
            function bindHoldEvents() {
                const micBtn = document.getElementById('mic-btn');
                if (!micBtn) return;
                micBtn.addEventListener('mousedown', function(e) {
                    if (asrMode === 'hold') {
                        e.preventDefault();
                        onHoldStart();
                    }
                });
                micBtn.addEventListener('mouseup', function() {
                    if (asrMode === 'hold') onHoldEnd();
                });
                micBtn.addEventListener('mouseleave', function() {
                    if (asrMode === 'hold' && asrState === ASRState.RECORDING) onHoldEnd();
                });
                micBtn.addEventListener('touchstart', function(e) {
                    if (asrMode === 'hold') {
                        e.preventDefault();
                        onHoldStart();
                    }
                });
                micBtn.addEventListener('touchend', function() {
                    if (asrMode === 'hold') onHoldEnd();
                });
            }

            // 从 /api/info 读取 asr_mode 并初始化
            function initAsrModeFromServer() {
                fetch('./api/info')
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        const serverMode = data.asr_mode || 'vad';
                        const savedMode = localStorage.getItem('asrMode');
                        asrMode = savedMode || serverMode;
                        localStorage.setItem('asrMode', asrMode);
                        initAsrModeSelector();
                        bindHoldEvents();
                        const micBtn = document.getElementById('mic-btn');
                        if (micBtn) {
                            micBtn.title = asrMode === 'hold' ? '按住说话（或按空格键）' : '语音输入（VAD自动监听）';
                        }
                    })
                    .catch(function() {
                        initAsrModeSelector();
                        bindHoldEvents();
                    });
            }
            initAsrModeFromServer();

            updateInfo();
            setInterval(updateInfo, 5000);

            // ===== 角色面板 (Day 2) =====
            const charPanel = document.getElementById('char-panel');
            const charIframe = document.getElementById('char-iframe');
            const charLoading = document.getElementById('char-loading');
            const collapseBtn = document.getElementById('char-collapse-btn');
            const closeBtn = document.getElementById('char-close-btn');
            const phoneTime = document.getElementById('phone-time');
            const charTabs = document.querySelectorAll('.char-tab');
            let currentCharType = localStorage.getItem('charType') || 'live2d';
            let panelCollapsed = localStorage.getItem('charPanelCollapsed') !== 'false';
            let charIframeFirstLoaded = false;

            function detectProxyPrefix() {
                const path = window.location.pathname;
                if (path.startsWith('/state/')) {
                    return '/state';
                }
                return '';
            }

            function getCharUrl(type) {
                const proxyPrefix = detectProxyPrefix();
                if (proxyPrefix) {
                    return proxyPrefix + '/' + type + '/';
                }
                const urlMap = {
                    live2d: live2dUrl,
                    mmd: mmdUrl,
                    vrm: vrmUrl
                };
                const el = urlMap[type];
                if (!el || !el.href) return '';
                try {
                    const url = new URL(el.href);
                    url.hostname = window.location.hostname;
                    return url.toString();
                } catch (e) {
                    return el.href;
                }
            }

            function loadCharIframe(type) {
                const url = getCharUrl(type);
                if (!url) return;
                charLoading.style.display = 'flex';
                const currentSrc = charIframe.getAttribute('src') || '';
                if (currentSrc === '' || currentSrc === 'about:blank') {
                    charIframe.src = url;
                } else {
                    charIframe.src = 'about:blank';
                    requestAnimationFrame(function() {
                        requestAnimationFrame(function() {
                            charIframe.src = url;
                        });
                    });
                }
                currentCharType = type;
                localStorage.setItem('charType', type);
                charTabs.forEach(function(t) {
                    t.classList.toggle('active', t.dataset.type === type);
                });
            }

            charIframe.addEventListener('load', function() {
                if (charIframe.src && charIframe.src !== 'about:blank') {
                    charLoading.style.display = 'none';
                }
            });

            charTabs.forEach(function(tab) {
                tab.addEventListener('click', function() {
                    const type = tab.dataset.type;
                    if (type !== currentCharType) {
                        loadCharIframe(type);
                    }
                });
            });

            function setPanelCollapsed(collapsed) {
                panelCollapsed = collapsed;
                charPanel.classList.toggle('collapsed', collapsed);
                collapseBtn.textContent = collapsed ? '◀' : '▶';
                collapseBtn.title = collapsed ? '展开角色面板' : '折叠角色面板';
                localStorage.setItem('charPanelCollapsed', collapsed);
            }

            collapseBtn.addEventListener('click', function() {
                setPanelCollapsed(!panelCollapsed);
            });
            closeBtn.addEventListener('click', function() {
                setPanelCollapsed(true);
            });

            if (panelCollapsed) {
                setPanelCollapsed(true);
            }

            function updatePhoneTime() {
                const now = new Date();
                phoneTime.textContent = now.getHours().toString().padStart(2, '0') + ':' +
                    now.getMinutes().toString().padStart(2, '0');
            }
            updatePhoneTime();
            setInterval(updatePhoneTime, 30000);

            // 轮询等待 /api/info 返回 URL 后再加载角色，避免固定 3s 延迟导致 URL 未就绪
            function tryInitCharIframe() {
                if (charIframeFirstLoaded || panelCollapsed) return;
                const url = getCharUrl(currentCharType);
                if (url) {
                    loadCharIframe(currentCharType);
                    charIframeFirstLoaded = true;
                } else {
                    setTimeout(tryInitCharIframe, 200);
                }
            }
            setTimeout(tryInitCharIframe, 100);

            // ===== 侧边栏事件绑定 =====
            const newSessionBtn = document.getElementById('new-session-btn');
            const sidebarToggle = document.getElementById('sidebar-toggle');
            const sidebarExpandBtn = document.getElementById('sidebar-expand-btn');
            if (newSessionBtn) {
                newSessionBtn.addEventListener('click', function() {
                    AppState.createNewSession();
                });
            }
            if (sidebarToggle) {
                sidebarToggle.addEventListener('click', function() {
                    AppState.isSidebarOpen = !AppState.isSidebarOpen;
                    document.getElementById('session-sidebar').classList.toggle('collapsed', !AppState.isSidebarOpen);
                    localStorage.setItem('sidebarOpen', AppState.isSidebarOpen);
                    if (sidebarExpandBtn) {
                        sidebarExpandBtn.style.display = AppState.isSidebarOpen ? 'none' : 'inline-block';
                    }
                });
            }
            if (sidebarExpandBtn) {
                sidebarExpandBtn.addEventListener('click', function() {
                    AppState.isSidebarOpen = true;
                    document.getElementById('session-sidebar').classList.toggle('collapsed', false);
                    localStorage.setItem('sidebarOpen', 'true');
                    sidebarExpandBtn.style.display = 'none';
                });
            }

            // 点击页面其他地方关闭会话菜单
            document.addEventListener('click', function() {
                document.querySelectorAll('.session-menu').forEach(function(m) {
                    m.style.display = 'none';
                });
            });

            // ===== 初始化 AppState =====
            AppState.init();

            // ===== VLM 配置 =====
            let preferVlm = 'off';
            async function initVlmConfig() {
                try {
                    const res = await fetch('./api/get_config');
                    const cfg = await res.json();
                    preferVlm = cfg.prefer_vlm || 'off';
                } catch (e) {
                    console.log('[VLM] 加载配置失败', e);
                }
            }
            initVlmConfig();

            // ===== 预设快捷切换 =====
            const PRESET_MAP = {
                "balanced": { temperature: 0.7, max_tokens: 4096, top_p: 0.9 },
                "analysis": { temperature: 0.3, max_tokens: 8192, top_p: 0.5 },
                "creative": { temperature: 0.95, max_tokens: 4096, top_p: 1.0 }
            };

            async function initPresetSelect() {
                try {
                    const res = await fetch('./api/get_config');
                    const cfg = await res.json();
                    const presetSelect = document.getElementById('preset-select');
                    if (presetSelect && cfg.llm_preset) {
                        presetSelect.value = cfg.llm_preset;
                    }
                } catch (e) {
                    // console.log('[Preset] 加载当前预设失败', e);
                }
            }

            async function savePreset(preset) {
                try {
                    const res = await fetch('./api/save_preset', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ preset: preset })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        showToast('已切换为：' + (preset === 'balanced' ? '日常聊天' : preset === 'analysis' ? '深度分析' : '创意发散'));
                    } else {
                        showToast('预设保存失败：' + (data.message || '未知错误'));
                    }
                } catch (e) {
                    console.error('[Preset] 保存失败', e);
                    showToast('预设保存失败');
                }
            }

            const presetSelect = document.getElementById('preset-select');
            if (presetSelect) {
                initPresetSelect();
                presetSelect.addEventListener('change', function() {
                    savePreset(this.value);
                });
            }

            // ===== 模型切换面板（P3 Day 5 新增） =====
            function showModelSwitcher() {
                let panel = document.getElementById('model-switcher-panel');
                if (panel) {
                    panel.remove();
                    return;
                }

                const btn = document.getElementById('btn-switch-model');
                const btnRect = btn ? btn.getBoundingClientRect() : null;

                panel = document.createElement('div');
                panel.id = 'model-switcher-panel';
                panel.style.cssText = 'position:fixed;background:#1e1e1e;border:1px solid #444;border-radius:8px;padding:12px;min-width:220px;z-index:1000;box-shadow:0 4px 12px rgba(0,0,0,0.5);';

                // 定位在按钮上方
                if (btnRect) {
                    const panelHeight = 280;
                    let top = btnRect.top - panelHeight;
                    if (top < 10) top = btnRect.bottom + 10;
                    panel.style.top = top + 'px';
                    panel.style.left = Math.max(10, btnRect.left - 180) + 'px';
                } else {
                    panel.style.bottom = '60px';
                    panel.style.right = '10px';
                }

                panel.innerHTML = `
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <strong style="color:#fff;">⚙️ 切换模型</strong>
                        <button onclick="document.getElementById('model-switcher-panel').remove()" style="background:none;border:none;color:#999;cursor:pointer;">✕</button>
                    </div>
                    <div id="model-list" style="max-height:200px;overflow-y:auto;margin-bottom:8px;"></div>
                    <button onclick="refreshModelList()" style="width:100%;padding:6px;background:#2d2d2d;border:1px solid #555;color:#fff;border-radius:4px;cursor:pointer;">🔄 刷新模型列表</button>
                `;

                document.body.appendChild(panel);
                refreshModelList();
            }

            async function refreshModelList() {
                const listDiv = document.getElementById('model-list');
                if (!listDiv) return;
                listDiv.innerHTML = '<div style="color:#999;padding:8px;">加载中...</div>';

                try {
                    const resp = await fetch('./api/openai_models');
                    const data = await resp.json();

                    if (data.status === 'success' && data.models.length > 0) {
                        listDiv.innerHTML = '';
                        data.models.forEach(model => {
                            const item = document.createElement('div');
                            item.style.cssText = 'padding:6px 8px;cursor:pointer;color:#ddd;border-radius:4px;';
                            item.textContent = model;
                            item.onmouseenter = function() { this.style.background = '#333'; };
                            item.onmouseleave = function() { this.style.background = 'transparent'; };
                            item.onclick = () => switchToModel(model);
                            listDiv.appendChild(item);
                        });
                    } else {
                        listDiv.innerHTML = '<div style="color:#f66;padding:8px;">' + (data.message || '无可用模型') + '</div>';
                    }
                } catch (e) {
                    listDiv.innerHTML = '<div style="color:#f66;padding:8px;">获取失败: ' + e.message + '</div>';
                }
            }

            async function switchToModel(modelName) {
                try {
                    const resp = await fetch('./api/save_preset', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ openai_llm_model: modelName })
                    });
                    const data = await resp.json();

                    if (data.status === 'success') {
                        showToast('已切换到模型: ' + modelName);
                        const panel = document.getElementById('model-switcher-panel');
                        if (panel) panel.remove();
                    } else {
                        showToast('切换失败: ' + (data.message || '未知错误'));
                    }
                } catch (e) {
                    showToast('切换异常: ' + e.message);
                }
            }

            // 暴露到全局，供 HTML onclick 调用
            window.showModelSwitcher = showModelSwitcher;
            window.refreshModelList = refreshModelList;
            window.switchToModel = switchToModel;

            // ===== GlobalSearch: 全局搜索组件（P2 Day 5 新增） =====
            const GlobalSearch = {
                _timer: null,
                _lastKeyword: '',

                init() {
                    const self = this;
                    const input = document.getElementById('global-search-input');
                    const closeBtn = document.getElementById('global-search-close');

                    if (input) {
                        input.addEventListener('input', function(e) {
                            clearTimeout(self._timer);
                            const keyword = e.target.value.trim();
                            if (!keyword) {
                                self._hideResults();
                                return;
                            }
                            self._timer = setTimeout(function() { self._doSearch(keyword); }, 500);
                        });

                        input.addEventListener('keydown', function(e) {
                            if (e.key === 'Escape') {
                                self._hideResults();
                                input.blur();
                            }
                        });
                    }

                    if (closeBtn) {
                        closeBtn.addEventListener('click', function() { self._hideResults(); });
                    }

                    // 点击外部关闭结果浮层
                    document.addEventListener('click', function(e) {
                        const box = document.getElementById('global-search-box');
                        if (box && !box.contains(e.target)) {
                            self._hideResults();
                        }
                    });
                },

                async _doSearch(keyword) {
                    if (keyword === this._lastKeyword) return;
                    this._lastKeyword = keyword;

                    const listEl = document.getElementById('global-search-list');
                    if (!listEl) return;
                    listEl.innerHTML = '<div style="padding:12px;text-align:center;color:#888;">搜索中...</div>';
                    this._showResults();

                    try {
                        const data = await apiFetch('/api/search', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({q: keyword}),
                            skipStatusCheck: true
                        });

                        if (data.status === 'success') {
                            this._renderResults(data.results, keyword, data.has_more);
                            const countEl = document.getElementById('global-search-count');
                            if (countEl) {
                                countEl.textContent = data.total + ' 条结果' + (data.has_more ? '（仅显示前 50 条）' : '');
                            }
                        } else {
                            listEl.innerHTML = '<div style="padding:12px;color:#f88;">' + escapeHtml(data.message || '搜索失败') + '</div>';
                        }
                    } catch (err) {
                        listEl.innerHTML = '<div style="padding:12px;color:#f88;">搜索失败，请检查网络</div>';
                    }
                },

                _renderResults(results, keyword, hasMore) {
                    const listEl = document.getElementById('global-search-list');
                    if (!listEl) return;

                    if (results.length === 0) {
                        listEl.innerHTML = '<div style="padding:12px;text-align:center;color:#888;">未找到匹配结果</div>';
                        return;
                    }

                    // 构建高亮正则（escape 正则特殊字符）
                    const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    const highlightRe = new RegExp('(' + escapedKeyword + ')', 'gi');

                    listEl.innerHTML = results.map(function(group) {
                        const matchesHtml = group.matches.map(function(m) {
                            const preview = escapeHtml(m.content_preview).replace(highlightRe, '<mark>$1</mark>');
                            const roleIcon = m.role === 'user' ? '🧑' : '🤖';
                            return '<div class="search-result-match"' +
                                ' data-session-id="' + escapeHtml(group.session_id) + '"' +
                                ' data-message-id="' + escapeHtml(String(m.message_id)) + '"' +
                                ' data-keyword="' + escapeHtml(keyword) + '">' +
                                '<span class="search-result-role">' + roleIcon + '</span>' + preview +
                                '</div>';
                        }).join('');

                        return '<div class="search-result-group">' +
                            '<div class="search-result-title" data-session-id="' + escapeHtml(group.session_id) + '">' +
                            '📁 ' + escapeHtml(group.session_title) + '（' + group.matches.length + ' 条）' +
                            (group.is_archived ? '<span style="color:#888;font-size:10px;">[已归档]</span>' : '') +
                            '</div>' +
                            matchesHtml +
                            '</div>';
                    }).join('') + (hasMore ?
                        '<div style="padding:8px 12px;text-align:center;color:#888;font-size:11px;">结果过多，请细化关键词</div>' : '');

                    // 绑定点击事件：点击匹配项 → 跳转
                    const self = this;
                    listEl.querySelectorAll('.search-result-match').forEach(function(el) {
                        el.addEventListener('click', function() {
                            const sid = el.dataset.sessionId;
                            const mid = parseInt(el.dataset.messageId);
                            const kw = el.dataset.keyword;
                            self._jumpToMessage(sid, mid, kw);
                        });
                    });

                    // 绑定点击事件：点击标题 → 切换会话
                    listEl.querySelectorAll('.search-result-title').forEach(function(el) {
                        el.addEventListener('click', function() {
                            const sid = el.dataset.sessionId;
                            AppState.loadSession(sid);
                            self._hideResults();
                        });
                    });
                },

                async _jumpToMessage(sessionId, messageId, keyword) {
                    this._hideResults();

                    // 1. 切换会话（已归档会自动恢复，复用 P1 归档恢复逻辑）
                    await AppState.loadSession(sessionId);

                    // 2. 渲染完成后，找到目标消息
                    const msgEl = document.querySelector('.message[data-message-id="' + messageId + '"]');
                    if (!msgEl) {
                        showToast('消息定位失败');
                        return;
                    }

                    // 3. 滚动到消息并高亮
                    msgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    msgEl.classList.add('highlight');
                    setTimeout(function() { msgEl.classList.remove('highlight'); }, 2000);

                    // 4. 触发当前会话搜索高亮（复用 Day 4 ChatSearch 能力）
                    // 注意：此处仅高亮文本不打开搜索浮层，保持界面简洁
                    ChatSearch.search(keyword);
                },

                _showResults() {
                    const el = document.getElementById('global-search-results');
                    if (el) el.classList.remove('hidden');
                },

                _hideResults() {
                    const el = document.getElementById('global-search-results');
                    if (el) el.classList.add('hidden');
                    this._lastKeyword = '';
                    clearTimeout(this._timer);
                }
            };

            // ===== ChatNav: 对话导航栏组件（P2 Day 3 新增） =====
            const ChatNav = {
                isOpen: true,
                _toggleBound: false,

                init() {
                    const saved = localStorage.getItem('chatNavOpen');
                    this.isOpen = saved !== 'false';
                    this._applyState();

                    const toggleBtn = document.getElementById('chat-nav-toggle');
                    if (toggleBtn && !this._toggleBound) {
                        this._toggleBound = true;
                        const self = this;
                        toggleBtn.addEventListener('click', function() {
                            self.isOpen = !self.isOpen;
                            self._applyState();
                            localStorage.setItem('chatNavOpen', self.isOpen);
                        });
                    }
                },

                _applyState() {
                    const panel = document.getElementById('chat-nav-panel');
                    const btn = document.getElementById('chat-nav-toggle');
                    if (!panel || !btn) return;
                    panel.classList.toggle('collapsed', !this.isOpen);
                    btn.textContent = this.isOpen ? '▶' : '◀';
                    btn.title = this.isOpen ? '折叠导航栏' : '展开导航栏';
                },

                render() {
                    const container = document.getElementById('chat-nav-content');
                    if (!container) return;
                    container.innerHTML = '';

                    const history = AppState.conversationHistory;
                    if (history.length === 0) return;

                    // 超过 100 条提示
                    if (history.length > 100) {
                        const hint = document.createElement('div');
                        hint.className = 'nav-hint';
                        hint.textContent = '会话过长，仅显示最近 100 条';
                        container.appendChild(hint);
                    }

                    const displayHistory = history.slice(-100);

                    // 按轮次分组（user + assistant 为一轮）
                    let currentRound = [];
                    let currentIndices = [];
                    let roundIndex = 0;

                    displayHistory.forEach(function(msg, localIndex) {
                        const globalIndex = history.length > 100
                            ? history.length - 100 + localIndex
                            : localIndex;

                        if (msg.role === 'user') {
                            if (currentRound.length > 0) {
                                ChatNav._renderRound(container, currentRound, currentIndices, roundIndex);
                                roundIndex++;
                            }
                            currentRound = [msg];
                            currentIndices = [globalIndex];
                        } else {
                            currentRound.push(msg);
                            currentIndices.push(globalIndex);
                        }
                    });

                    if (currentRound.length > 0) {
                        ChatNav._renderRound(container, currentRound, currentIndices, roundIndex);
                    }
                },

                _renderRound(container, roundMsgs, roundIndices, roundIdx) {
                    const roundDiv = document.createElement('div');
                    roundDiv.className = 'nav-round';

                    const header = document.createElement('div');
                    header.className = 'nav-round-header';
                    header.innerHTML = '<span>▼</span><span>第 ' + (roundIdx + 1) + ' 轮</span>';
                    header.addEventListener('click', function() {
                        roundDiv.classList.toggle('collapsed');
                        const arrow = header.querySelector('span');
                        if (arrow) {
                            arrow.textContent = roundDiv.classList.contains('collapsed') ? '▶' : '▼';
                        }
                    });

                    const content = document.createElement('div');
                    content.className = 'nav-round-content';

                    const self = this;
                    roundMsgs.forEach(function(msg, idx) {
                        const globalIdx = roundIndices[idx];
                        const item = document.createElement('div');
                        item.className = 'nav-item nav-item-' + msg.role;
                        item.dataset.index = globalIdx;

                        const icon = msg.role === 'user' ? '🧑' : '🤖';
                        const preview = (msg.content || '').substring(0, 15);
                        const time = self._formatTime(msg.timestamp);

                        item.innerHTML = '<div>' + icon + ' ' + escapeHtml(preview) + (msg.content && msg.content.length > 15 ? '...' : '') + '</div>' +
                                         '<div class="nav-item-time">' + time + '</div>';
                        item.addEventListener('click', function() {
                            self.jumpTo(globalIdx);
                        });
                        content.appendChild(item);
                    });

                    roundDiv.appendChild(header);
                    roundDiv.appendChild(content);
                    container.appendChild(roundDiv);
                },

                jumpTo(index) {
                    const msgEl = document.querySelector('.message[data-index="' + index + '"]');
                    if (!msgEl) return;

                    msgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    msgEl.classList.add('highlight');
                    setTimeout(function() { msgEl.classList.remove('highlight'); }, 1000);

                    // 更新导航栏 active 状态
                    document.querySelectorAll('.nav-item').forEach(function(el) { el.classList.remove('active'); });
                    const activeItem = document.querySelector('.nav-item[data-index="' + index + '"]');
                    if (activeItem) {
                        activeItem.classList.add('active');
                    }
                },

                refresh() {
                    // 简单实现：直接重绘（50 条以内性能足够，< 100ms）
                    this.render();
                },

                _formatTime(timestamp) {
                    if (!timestamp) return '';
                    const d = new Date(timestamp * 1000);
                    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
                }
            };

            // ===== 搜索高亮辅助函数（P2 Day 4 新增） =====
            function escapeRegExp(string) {
                return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            }

            function highlightTextInElement(element, keyword) {
                const walker = document.createTreeWalker(
                    element,
                    NodeFilter.SHOW_TEXT,
                    null,
                    false
                );

                const nodesToReplace = [];
                let node;
                while (node = walker.nextNode()) {
                    if (node.textContent.toLowerCase().includes(keyword.toLowerCase())) {
                        nodesToReplace.push(node);
                    }
                }

                nodesToReplace.forEach(function(textNode) {
                    const parent = textNode.parentNode;

                    // 跳过已高亮的 mark 标签
                    if (parent.tagName === 'MARK' && parent.classList.contains('search-highlight')) {
                        return;
                    }

                    // 跳过 <code>/<pre> 标签内的文本，不破坏代码块
                    let ancestor = parent;
                    while (ancestor && ancestor !== element) {
                        if (ancestor.tagName === 'CODE' || ancestor.tagName === 'PRE') {
                            return;
                        }
                        ancestor = ancestor.parentNode;
                    }

                    const parts = textNode.textContent.split(
                        new RegExp('(' + escapeRegExp(keyword) + ')', 'gi')
                    );
                    const fragment = document.createDocumentFragment();

                    parts.forEach(function(part, i) {
                        if (i % 2 === 1) {
                            const mark = document.createElement('mark');
                            mark.className = 'search-highlight';
                            mark.textContent = part;
                            fragment.appendChild(mark);
                        } else {
                            fragment.appendChild(document.createTextNode(part));
                        }
                    });

                    parent.replaceChild(fragment, textNode);
                });
            }

            function clearHighlights() {
                document.querySelectorAll('mark.search-highlight').forEach(function(mark) {
                    const parent = mark.parentNode;
                    parent.insertBefore(document.createTextNode(mark.textContent), mark);
                    parent.removeChild(mark);
                    parent.normalize(); // 合并相邻文本节点
                });
            }

            // ===== ChatSearch 组件（P2 Day 4 新增） =====
            const ChatSearch = {
                matches: [],        // [{msgIndex, el, markIndex}]
                currentIndex: -1,
                isOpen: false,
                _timer: null,

                init() {
                    const self = this;
                    document.addEventListener('keydown', function(e) {
                        // Ctrl+F 唤起（输入框聚焦时不触发）
                        if (e.ctrlKey && e.key === 'f') {
                            const active = document.activeElement;
                            if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) {
                                return;
                            }
                            e.preventDefault();
                            self.open();
                        }
                        // Esc 关闭
                        else if (e.key === 'Escape') {
                            if (self.isOpen) self.close();
                        }
                        // Enter / Shift+Enter 切换
                        else if (e.key === 'Enter' && self.isOpen) {
                            e.preventDefault();
                            if (e.shiftKey) self.prev();
                            else self.next();
                        }
                    });

                    const closeBtn = document.getElementById('search-close');
                    const prevBtn = document.getElementById('search-prev');
                    const nextBtn = document.getElementById('search-next');
                    const input = document.getElementById('search-input');
                    const searchBtn = document.getElementById('search-btn');

                    if (closeBtn) closeBtn.addEventListener('click', function() { self.close(); });
                    if (prevBtn) prevBtn.addEventListener('click', function() { self.prev(); });
                    if (nextBtn) nextBtn.addEventListener('click', function() { self.next(); });
                    if (searchBtn) searchBtn.addEventListener('click', function() { self.open(); });

                    if (input) {
                        input.addEventListener('input', function() {
                            clearTimeout(self._timer);
                            self._timer = setTimeout(function() { self.search(input.value); }, 300);
                        });
                    }
                },

                open() {
                    this.isOpen = true;
                    const floatEl = document.getElementById('search-float');
                    const input = document.getElementById('search-input');
                    if (floatEl) floatEl.style.display = 'block';
                    if (input) {
                        input.focus();
                        input.select();
                    }
                },

                close() {
                    this.isOpen = false;
                    const floatEl = document.getElementById('search-float');
                    const input = document.getElementById('search-input');
                    if (floatEl) floatEl.style.display = 'none';
                    if (input) input.value = '';
                    this.clearHighlight();
                    clearTimeout(this._timer);
                },

                search(keyword) {
                    this.clearHighlight();
                    this.matches = [];
                    this.currentIndex = -1;

                    if (!keyword.trim()) {
                        this._updateCount();
                        return;
                    }

                    const history = AppState.conversationHistory;

                    const self = this;
                    history.forEach(function(msg, msgIndex) {
                        if (!msg.content || !msg.content.toLowerCase().includes(keyword.toLowerCase())) {
                            return;
                        }

                        const msgEl = document.querySelector('.message[data-index="' + msgIndex + '"]');
                        if (!msgEl) return;

                        const contentDiv = msgEl.querySelector('.message-content');
                        if (!contentDiv) return;

                        highlightTextInElement(contentDiv, keyword);

                        // 收集该消息中的所有 mark
                        const marks = contentDiv.querySelectorAll('mark.search-highlight');
                        marks.forEach(function(mark) {
                            self.matches.push({ msgIndex: msgIndex, el: mark });
                        });
                    });

                    if (this.matches.length > 0) {
                        this.currentIndex = 0;
                        this._highlightCurrent();
                    }
                    this._updateCount();
                },

                next() {
                    if (this.matches.length === 0) return;
                    this.currentIndex = (this.currentIndex + 1) % this.matches.length;
                    this._highlightCurrent();
                },

                prev() {
                    if (this.matches.length === 0) return;
                    this.currentIndex = (this.currentIndex - 1 + this.matches.length) % this.matches.length;
                    this._highlightCurrent();
                },

                _highlightCurrent() {
                    document.querySelectorAll('mark.search-highlight.current').forEach(function(m) {
                        m.classList.remove('current');
                    });

                    const match = this.matches[this.currentIndex];
                    if (match) {
                        match.el.classList.add('current');
                        match.el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                    this._updateCount();
                },

                _updateCount() {
                    const count = this.matches.length;
                    const current = count > 0 ? this.currentIndex + 1 : 0;
                    const countEl = document.getElementById('search-count');
                    if (countEl) countEl.textContent = current + '/' + count;
                },

                clearHighlight() {
                    clearHighlights();
                    this.matches = [];
                    this.currentIndex = -1;
                }
            };

            ChatNav.init();
            ChatSearch.init();
            GlobalSearch.init();
        });
