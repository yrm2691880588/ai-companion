# 语音技术选型：复用现有栈，只补必要依赖

## 背景

用户要求技术栈由实现方决定，原则是“正规、不重复造轮子、有成熟方案就用”。
现有栈：FastAPI + SQLAlchemy + httpx + Pydantic（后端），React 19 + TS + Vite（前端）。

## 决定

### 前端

| 能力 | 方案 | 理由 |
|---|---|---|
| 录音 | 浏览器原生 `MediaRecorder` | 无需第三方库，Web/手机浏览器通用 |
| 音频播放 | 原生 `Audio` 元素 | 同上；不引入播放器库 |
| 音量可视化 | Canvas + `AnalyserNode`（Web Audio API） | 原生，十几行代码 |
| 状态管理 | 现有 React state | 不引入 Zustand/Redux，语音状态是局部 UI 状态 |

不引入：`wavesurfer.js`（可视化过重）、`recordrtc`（自带上传与服务端耦合）、
`react-voice-visualizer`（绑定特定 UI 形态）。

### 后端

| 能力 | 方案 | 理由 |
|---|---|---|
| 文件上传 | `python-multipart` + FastAPI `UploadFile` | FastAPI 官方标准做法 |
| 音频临时存储 | 本地文件 + 短期签名 URL 端点 | 不引入对象存储，本地工具足够 |
| 供应商调用 | 现有 `httpx.AsyncClient` | 已有；不引入各家 SDK |
| 配置存储 | 复用 `SecretBox` 加密 + 新表 | 与模型供应商同一套加密口径 |
| 重试 | 现有重试思路（仅在未产生副作用前） | 不引入 tenacity 等依赖 |

不引入：火山/阿里 SDK（各家 SDK 体积大、版本耦合；HTTP 直连更容易抽象多供应商）。

### 供应商适配

- 统一接口 `VoiceProvider`：`list_voices()`、`transcribe(audio, fmt)`、`synthesize(text, voice_id, params)`；
- 首个实现：火山引擎（一句话识别 + TTS）；
- 第二个实现：留接口位，不指定具体厂商（避免过度承诺）。

## 理由

这四项能力都有浏览器/框架原生方案，引入第三方库只会增加体积与升级负担；
而各家语音 SDK 的认证与字段各不相同，反而让抽象层更难做。

## 后果

- 需要新增依赖：`python-multipart`（后端）；前端零新增依赖；
- 音频临时文件需要清理策略（定时删除超过 1 小时的）；
- 火山 API 的签名/鉴权细节要自己实现一层（约 100 行）。
