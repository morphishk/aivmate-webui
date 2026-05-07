# AivMate-WebUI  技术栈调研报告

> 生成时间：2026-05-06
> 调研范围：后端、前端、AI/ML、数据层、部署基础设施

---

## 一、项目概述

**AivMate-WebUI**（GitHub 名 `aivmate-webui`）是一款基于 Linux 的 AI 虚拟伙伴系统，支持多形态交互（语音、文字、图像）、多角色展示（Live2D / MMD 3D / VRM 3D）以及机器人运动控制。项目采用 Python 后端 + 原生 JavaScript 前端的技术架构，面向 ARM/X86 的迷你主机、NAS 和开发板部署。

---

## 二、后端技术栈

### 2.1 核心运行时

| 技术 | 版本/说明 | 用途 |
|------|-----------|------|
| **Python** | 3.12 | 主开发语言 |
| **Flask** | ≥3.0.0 | Web 框架（聊天页 `web_state.py`、设置页 `web_settings.py`） |
| **Werkzeug** | Flask 内置 | 开发服务器（生产环境使用 nginx 反代） |
| **Threading** | 标准库 | 多线程并发（每个子服务独立线程） |
| **SQLite3** | 标准库 | 对话历史持久化 (`conversations.db`) |

### 2.2 服务架构模式

项目采用 **"单进程多线程 + 多端口多服务"** 的架构：

```
main.py (主进程)
├── Thread: run_state_web    → Flask @ 5260  (聊天页主服务)
│   └── AgentRegistry.discover_and_register()  ← 启动时自动注册 Agent
├── Thread: run_settings_web → Flask @ 5250  (系统设置页)
├── Thread: run_live2d       → Flask @ 5261  (Live2D 角色面板)
├── Thread: run_mmd          → Flask @ 5262  (MMD 3D 角色面板)
├── Thread: run_vrm          → Flask @ 5263  (VRM 3D 角色面板)
├── Thread: sense_voice_main → ASR 语音交互主循环
├── Thread: run_ase          → 主动感知引擎（定时触发对话）
└── Thread: _start_archive_timer → 会话归档定时器
```

> ⚠️ **架构风险**：Flask 内置开发服务器 (`app.run()`) 并非生产级 WSGI，高并发下性能有限。当前通过 nginx 反向代理缓解，但未使用 Gunicorn/uWSGI 等正式 WSGI 容器。

### 2.3 网络与系统

| 技术 | 用途 |
|------|------|
| `requests` | HTTP 客户端（调用外部 LLM/TTS API） |
| `psutil` | 系统状态监控（CPU、内存、温度） |
| `pywifi` | WiFi 信号强度检测 |
| `ping3` | 网络延迟检测 |
| `pygame` | 音频播放控制 |
| `concurrent.futures.ThreadPoolExecutor` | 标准库 | Agent 执行 10s 超时控制（防止外部 API 挂起阻塞 Flask 线程） |

---

## 三、前端技术栈

### 3.1 核心框架

| 技术 | 说明 |
|------|------|
| **原生 JavaScript (Vanilla JS)** | 无 Vue/React/Angular 等现代前端框架 |
| **原生 Fetch API** | HTTP 请求（无 Axios） |
| **原生 DOM API** | 直接操作 DOM，无 jQuery |
| **SSE (Server-Sent Events)** | 流式对话响应 (`ReadableStream`) |
| **发布/订阅模式** | `VoiceController.onChange()` 解耦语音状态与 DOM 渲染 |

> 前端代码集中在 `dist/assets/js/state-web.js`（单文件，约 2500+ 行），CSS 在 `dist/assets/css/state-web.css`。

### 3.2 3D/2D 角色渲染引擎

| 角色类型 | 技术栈 | 核心库 |
|----------|--------|--------|
| **Live2D** | PixiJS + Live2D Cubism Core | `pixi.min.js`, `live2d.min.js`, `live2dcubismcore.min.js` |
| **MMD 3D** | Three.js + MMDLoader + Ammo.js | `three.min.js`, `MMDLoader.js`, `ammo.js` |
| **VRM 3D** | Three.js + @pixiv/three-vrm | `three.module.js`, `three-vrm.module.min.js`, `GLTFLoader.js` |

### 3.3 前端构建与部署

- **无构建工具**：没有 Webpack/Vite/Rollup，前端代码手写后直接部署
- **无包管理器**：没有 npm/yarn/pnpm，JS 库以静态文件形式存放在 `dist/assets/`
- **版本控制**：CSS/JS 通过 URL 参数 `?v=N` 手动控制缓存（当前 `v=4`）

---

## 四、AI / ML 技术栈

### 4.1 大语言模型 (LLM)

| 提供商/方案 | SDK/API | 说明 |
|-------------|---------|------|
| **智谱 AI (ZhipuAI)** | `zhipuai` SDK | 默认 LLM，支持 GLM-4 系列 |
| **OpenAI 兼容** | `openai` SDK (≥1.0) | SiliconCloud、腾讯云、讯飞云等 |
| **Ollama** | `openai` SDK (本地 URL) | 本地/局域网部署 |
| **LM Studio** | `openai` SDK (局域网 URL) | 局域网模型服务 |
| **RKLLM** | HTTP API | 瑞芯微 NPU 加速推理 (RK3588/3576) |
| **Dify** | HTTP API | 本地知识库 + Agent |
| **AnythingLLM** | HTTP API | 本地知识库 |

**关键组件**：`llm_client.py` —— 自定义的 OpenAI 兼容客户端，绕过 `zhipuai` 的 monkey-patch，支持流式 SSE 和 UTF-8 修复。

### 4.2 视觉语言模型 (VLM)

| 提供商 | 模型示例 |
|--------|----------|
| 智谱 AI | GLM-4.6V-Flash |
| OpenAI 兼容 | Qwen/Qwen3-VL-8B-Instruct |
| Ollama | qwen3-vl:2b-instruct |
| LM Studio | 局域网 VLM |
| **本地集成** | YOLO + RapidOCR + LLM (vlm.py 中实现) |

### 4.3 语音识别 (ASR)

| 技术 | 库/模型 | 说明 |
|------|---------|------|
| **SenseVoice** | `sherpa-onnx` | 本地 ASR 引擎，支持多语言 |
| **声纹识别** | `sherpa-onnx` (campplus) | 3D-Speaker 模型，识别说话人身份 |
| **音频事件检测** | `sherpa-onnx` (zipformer-small) | 识别环境音（口哨、敲门、动物叫声等） |

### 4.4 语音合成 (TTS)

| 引擎 | 类型 | 说明 |
|------|------|------|
| **edge-tts** | 云端 | 微软 Edge 在线语音合成 |
| **VITS-ONNX (Piper)** | 本地 | `sherpa-onnx` 内置，中文女声模型 |
| **GPT-SoVITS** | 局域网 | 语音克隆 |
| **CosyVoice** | 局域网 | 阿里语音合成 |
| **Qwen-TTS** | 局域网 | 通义语音合成 |
| **Index-TTS** | 局域网 | 第三方 TTS 服务 |
| **VoxCPM** | 局域网 | 第三方 TTS 服务 |
| **Custom TTS** | 云端 API | 通过 OpenAI 兼容 API 调用 |

### 4.5 计算机视觉 (CV)

| 技术 | 库 | 用途 |
|------|-----|------|
| **YOLO** | `ultralytics` (YOLOv11) | 物体检测、分类 |
| **OCR** | `rapidocr_openvino` | 图片文字识别 |
| **人脸识别** | `face_recognition` | 用户身份识别 |
| **手势识别** | `mediapipe` | 手势控制机器人 |
| **图像处理** | `opencv-python` | 摄像头采集、预处理 |

---

## 五、数据存储

| 存储类型 | 技术 | 用途 |
|----------|------|------|
| **关系型数据库** | SQLite3 | 对话历史、会话管理 (`data/db/conversations.db`) |
| **配置文件** | JSON | 系统配置 (`config.json`, `config_default.json`) |
| **文件系统** | 本地磁盘 | 会话图片、附件、TTS 缓存、音频缓存 |
| **运行时缓存** | 内存 (Python dict/list) | 会话状态、临时数据 |
| **归档存储** | ZIP | 会话归档 (`data/archive/YYYY-MM/session_id.zip`) |

> SQLite 以单文件形式存储，通过 `check_same_thread=False` 支持多线程访问。

### 5.1 数据库 Schema 演进（迭代新增）

`conversation.py` 实现了幂等式表迁移：

```sql
-- Agent WebUI 迭代时新增列
ALTER TABLE messages ADD COLUMN agent_id TEXT;
ALTER TABLE messages ADD COLUMN agent_result TEXT;
```

迁移策略：
- 启动时通过 `PRAGMA table_info(messages)` 检查列是否存在
- 幂等执行：已存在则跳过，避免重复 ALTER 报错
- `save_message()` 支持 `agent_id` / `agent_result` 参数
- `get_session_messages()` 返回新字段，前端根据 `agent_result.type` 渲染结构化卡片

---

## 六、部署与基础设施

### 6.1 容器化

| 技术 | 说明 |
|------|------|
| **Docker** | 容器运行时 |
| **Docker Compose** | 编排 AivMate-WebUI + nginx 两个服务 |
| **基础镜像** | `smanx/opencode:latest` |
| **Python 环境** | `/opt/venv` 虚拟环境 |

**启动流程**（`start.sh`）：
1. 启动 Open Code Web UI
2. 启动 AivMate-WebUI 主程序

### 6.2 反向代理

| 技术 | 用途 |
|------|------|
| **nginx** | 统一入口（端口 8080 → 映射到宿主机 5260），SSE 长连接优化 |

nginx 配置要点：
- `/` → 聊天页 (5260)
- `/live2d/` → Live2D (5261)
- `/mmd/` → MMD (5262)
- `/vrm/` → VRM (5263)
- `/settings/` → 系统设置 (5250)
- `/api/vlm_stream` → SSE 流式接口（特殊处理 `proxy_buffering off`）

### 6.3 端口分配

| 端口 | 服务 | 外部暴露 |
|------|------|----------|
| 5250 | 系统设置 (web_settings) | ❌ 仅内部（nginx 反代 `/settings/`） |
| 5260 | 聊天页主服务 (web_state) | ❌ 仅内部（nginx 反代 `/`） |
| 5261 | Live2D 角色面板 | ❌ 仅内部（nginx 反代 `/live2d/`） |
| 5262 | MMD 3D 角色面板 | ❌ 仅内部（nginx 反代 `/mmd/`） |
| 5263 | VRM 3D 角色面板 | ❌ 仅内部（nginx 反代 `/vrm/`） |
| 3000 | Open Code Web UI | ✅ 对外暴露 |

---

## 七、Agent / 智能体框架

### 7.1 Agent 体系架构（迭代新增）

项目从 `function.py` 中的简单函数调用，升级为 **装饰器注册 + 自动发现** 的插件化 Agent 框架：

```
agents/
├── __init__.py
├── agent_base.py          # BaseAgent + AgentContext + AgentResult
├── agent_registry.py      # AgentRegistry 单例 + @register 装饰器
├── auto_agent_router.py   # 关键词/斜杠命令路由
├── weather_agent.py       # Open-Meteo API → card 类型
├── news_agent.py          # 百度热搜 API → list 类型
└── search_agent.py        # 百度搜索 → text 类型
```

**核心机制**：
- **装饰器注册**：`@register` 自动将 Agent 元数据注册到 `AgentRegistry`
- **自动发现**：`AgentRegistry.discover_and_register()` 遍历 `agents/` 目录动态加载
- **路由分发**：`AutoAgentRouter` 根据关键词或 `/command` 斜杠命令自动匹配 Agent
- **执行超时**：`web_state.py` 使用 `ThreadPoolExecutor` + `future.result(timeout=10)` 防止外部 API 挂起阻塞 Flask 线程
- **结果标准化**：`AgentResult(type="card|list|text|error", data=...)` 统一返回格式

### 7.2 前端 Agent 交互体系

| 组件 | 技术 | 功能 |
|------|------|------|
| `AgentStore` | 原生 JS 类 | Agent 元数据缓存、执行、结果管理 |
| `SlashCommandPicker` | 原生 DOM + 键盘事件 | 输入 `/` 弹出命令选择器，支持 ↑↓ Enter Esc |
| `ToggleSwitches` | 原生 DOM + Fetch API | 🌐 联网 / 🧠 感知 / 👤 人脸 持久化开关 |
| `AgentMessageRenderer` | 原生 DOM | 根据 `agent_result.type` 路由渲染卡片/列表/文本 |
| `CardTemplates` | HTML 模板字符串 | weather 卡片、news 列表等结构化渲染 |
| `HAPanel` | 原生 DOM + CSS 动画 | HomeAssistant 右侧抽屉面板（设备列表+开关控制） |
| `AgentToolbar` | 原生 DOM | 双层按钮布局（上排大按钮 / 下排小按钮） |

### 7.3 原有 Agent 功能

`function.py` 中保留的多 Agent 调用能力：

| Agent | 功能 |
|-------|------|
| `search()` | 联网搜索 (`websearch.py`) |
| `get_news()` | 新闻查询（百度热搜 API） |
| `get_weather()` | 天气查询（Open-Meteo API） |
| `homeassistant_control()` | Home Assistant 智能家居控制 |
| `yolo_ocr_cam()` | 摄像头物体检测 + OCR |
| `face_detect()` | 人脸识别 |
| `hand_gesture()` | 手势识别 |
| `get_info()` | 系统状态（CPU/内存/温度/WiFi） |

---

## 八、前端架构升级（迭代新增）

### 8.1 VoiceController 状态机重构

将语音控制从 DOM 操作中解耦，采用 **发布/订阅模式**：

```
VoiceController（纯状态机，零 DOM 操作）
├── state: 'idle' | 'listening' | 'recording' | 'processing'
├── mode: 'vad' | 'hold'
├── setState(newState) → 触发 onStateChange 回调
└── onStateChange: (state, mode) => void
```

**收益**：消除 DOM 双写、集中管理 5 种按钮状态、防御性检查降级为状态机校验。

### 8.2 全局错误过滤

屏蔽浏览器插件、webpack 监控 SDK 等外部注入脚本导致的控制台报错：
- 过滤 `dp.js`、`chrome-extension://`、`webpack://`、`blob:` 来源的错误
- 避免外部脚本污染控制台，干扰调试

### 8.3 iframe 加载状态管理

`charIframe`（Live2D/MMD/VRM 面板）添加完整的生命周期管理：
- **10 秒超时**：未加载完成显示友好提示
- **error 事件监听**：加载失败提示检查服务是否启动
- **空内容检测**：跨域安全检测 iframe 内容是否为空

---

## 九、网络与搜索优化（迭代新增）

### 9.1 百度搜索反爬优化

| 优化项 | 说明 |
|--------|------|
| User-Agent 更新 | Chrome 68 → Chrome 120 |
| 请求间隔 | 分页请求间增加 `time.sleep(1)` |
| 反爬检测 | 检测 `security_verify` 页面，提前退出 |
| 超时控制 | `parse_html()` 增加 `timeout=10` |
| LLM Fallback | `ol_search()` 中 `function_llm()` 失败时返回原始搜索摘要 |

### 9.2 3D 角色错误收敛

| 模块 | 机制 | 说明 |
|------|------|------|
| **MMD** | 失败计数器 | `api/get_mouth_y` 连续失败 3 次后停止 `setInterval` 轮询 |
| **VRM** | 失败计数器 | `is_audio_playing` 连续失败 3 次后停止轮询 |

---

## 十、已知技术债务与风险

| 风险项 | 严重程度 | 说明 |
|--------|----------|------|
| Flask 开发服务器 | ⚠️ 中 | 生产环境应替换为 Gunicorn/uWSGI |
| 单文件前端 | ⚠️ 低 | state-web.js 超过 2500 行，维护成本高 |
| 无前端构建 | ⚠️ 低 | 缺乏类型检查、代码分割、Tree Shaking |
| SQLite 并发 | ⚠️ 低 | `check_same_thread=False` 虽可行，但高并发下可能锁竞争 |
| openvino 版本锁定 | ⚠️ 中 | Dockerfile 中硬编码 `openvino==2024.6.0`，升级需谨慎 |
| 线程管理 | ⚠️ 中 | daemon 线程异常退出可能导致服务静默失效 |
| 内存泄漏 | ⚠️ 低 | pygame mixer 未显式退出，长期运行可能累积 |
| `_submitState.isSubmitting` 全局锁 | ⚠️ 中 | 一个锁被用于输入框/发送按钮/VAD循环/TTS队列多个子系统，长期建议提取 `submitMessage()` 独立函数 |
| 百度搜索 DOM 依赖 | ⚠️ 中 | `websearch.py` 硬编码 `#content_left`、`.c-abstract` 等选择器，百度改版即失效 |
| 旧消息兼容 | ⚠️ 低 | 历史消息 `agent_id`/`agent_result` 为 null，前端已做 text fallback |

---

## 十一、总结

AivMate-WebUI 是一个典型的 **Python 全栈 + AI 集成** 项目，技术选型务实：

- **后端**：Flask 轻量框架 + 多线程服务拆分，适合中小型部署
- **前端**：原生 JS 无框架，3D 渲染依赖 Three.js 生态
- **AI**：云端 API + 本地 ONNX 模型混合架构，兼顾性能和成本
- **部署**：Docker + nginx，符合现代容器化标准

### 迭代后的架构演进

相比原始版本，本轮迭代在以下方面进行了架构升级：

1. **Agent 插件化**：从 `function.py` 的硬编码函数调用 → `agents/` 目录的装饰器注册 + 自动发现框架
2. **前端组件化**：从单一事件监听 → `AgentStore` + `VoiceController` 状态机 + 发布/订阅模式
3. **容错收敛**：MMD/VRM 轮询从无限报错 → 失败 3 次后优雅停止；百度搜索增加反爬检测和 LLM fallback
4. **部署标准化**：新增 mihomo 代理自启动、SSH 密钥自动初始化、`.env` 环境变量注入

项目的核心复杂度在于 **AI 模型的多端适配**（云端/局域网/本地）和 **多模态输入输出**（语音/图像/文字/3D 角色）的协同，而非 Web 框架本身。
