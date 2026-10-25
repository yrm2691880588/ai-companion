# AI 伴侣系统 V1.0

多角色 AI 伴侣平台：一句话生成 7 维人设、模板库、多伴侣隔离、流式对话、长期记忆、长对话压缩、社交演练。
后端为 Python/FastAPI 模块化单体，模型层可插拔（默认 DeepSeek 官方 1M 上下文，支持多家预设与本地模型）。

## 当前进度（M0 进行中）

| 模块 | 状态 |
|---|---|
| 模型网关（OpenAI/Anthropic 适配、SSE 解析、错误归一） | ✅ 已完成并有测试 |
| 模型注册表 + 9 类预设 + 任务路由 + 降级链 | ✅ 已完成并有测试 |
| 定价与成本预算（高峰/空闲、缓存命中、成本倒推 token 上限） | ✅ 已完成并有测试 |
| 供应商密钥信封加密、SSRF 防护 | ✅ 已完成并有测试 |
| 模型层数据表与迁移（5 张表） | ✅ 已在真实 Postgres(pgvector 0.8.7) 上跑通 |
| 调用记账（llm_calls，含失败尝试）与用量统计接口 | ✅ 已落库，实测 10 次调用可查 |
| 人设 7 维 Schema + 校验 + 提示词编译 | ✅ 已完成（[说明](docs/人设Schema与伴侣接口.md)） |
| 一句话生成人设（真实 DeepSeek 生成并落库） | ✅ 已跑通，示例见文档 |
| 伴侣创建 / 列表 / 详情 / 改人设（版本化）/ 单维重写 | ✅ 接口与测试完成 |
| 模板库（5 类 × 2 个）+ 从模板创建 + 删除伴侣 | ✅ 真实库验证通过 |
| 对话主链路：会话/消息/SSE/人设注入/历史承接 | ✅ 真实 DeepSeek 两轮对话验证（[说明](docs/对话接口与SSE.md)） |
| 长期记忆：自动抽取/去重/跨会话召回/可看可删/总开关 | ✅ 真实链路验证（[说明](docs/记忆与上下文.md)） |
| 上下文压缩：预算裁剪 + 早期对话摘要 + 摘要查看 | ✅ 真实链路验证（[说明](docs/上下文压缩.md)） |
| 演练模式：5 个场景 + 扮演 + 回合上限 + 复盘 | ✅ 真实链路验证（[说明](docs/演练与安全.md)） |
| 安全兜底：危机识别 + 角色口吻提示 + 事件留痕 | ✅ 单测与接口测试 |
| 每日额度：60 轮/日、失败返还、额度查询、前端提示 | ✅ 真库原子计数验证（[说明](docs/额度与内容安全.md)） |
| 登录：手机验证码 + httpOnly Cookie 会话 | ✅ 真库验证（[说明](docs/登录与账号.md)） |
| 强制登录：未登录自动跳登录页，匿名数据可迁移 | ✅ 已验证（[说明](docs/登录与账号.md)） |
| 内容边界：成年人自愿亲密放开，仅保留未成年/非自愿/违法等红线 | ✅ 真实模型验证（[说明](docs/内容边界与成年模式.md)） |
| 人设生成忠实于用户描述 + 伴侣头像上传 | ✅ 真实模型/真库验证（[说明](docs/伴侣头像与人设忠实度.md)） |
| 删除伴侣：软删 + 异步硬清 + 补偿对账 | ✅ 真库验证全部归零（[说明](docs/删除与数据清理.md)） |
| P1：重新生成（原地替换）+ 数据导出 | ✅ 真实链路验证（[对话说明](docs/对话接口与SSE.md)） |
| 管理员：角色、额度开关、统一模型配置、审计 | ✅ 真库验证（[说明](docs/管理员与系统设置.md)） |
| 粉色恋爱主题 + 6 套预设 + 自定义主色 | ✅ 已应用（[说明](docs/一键启动.md)） |
| 一键启动：双击脚本、自动开页 | ✅ 实测页面与接口同源可用（[说明](docs/一键启动.md)） |
| 前端（H5）：伴侣/创建/对话/记忆/演练/模型设置/登录 | ✅ 已联调（[说明](docs/前端说明.md)） |
| HTTP API（模型只读接口、健康检查） | ✅ 可用 |
| DeepSeek 官方真实调用 | ✅ 已跑通（流式、JSON、缓存命中、延迟与成本已实测） |
| 向量召回、断线续传、App 壳 | ⏳ V1.1 |

> 设计文档在 `docs/`：总体计划、后端与架构、前端方案、模型接入方案、修订说明。

## 目录结构

```
backend/            FastAPI 后端（app/ 业务，alembic/ 迁移，tests/ 测试）
frontend/           前端 H5（React 19 + TS + Vite，端口 5273）
docker/             docker-compose：Postgres(pgvector) + Redis + MinIO + API + Web
scripts/            PowerShell 开发脚本（安装、测试、起前后端）
docs/               方案、接口与实测文档
```

## 快速开始（Windows PowerShell 7）

### 普通用户：双击启动

1. 打开项目文件夹；
2. 双击 **`启动AI伴侣.bat`**；
3. 浏览器自动打开 `http://127.0.0.1:8000/`；
4. **先用手机号 + 验证码登录**（开发模式验证码直接显示），再创建伴侣。

关闭窗口即停止服务。详细说明见 [一键启动](docs/一键启动.md)。

> 之前未登录时创建的数据落在 `dev-user` 下，登录后不会自动出现。用迁移脚本转到你的账号：
> `backend/.venv/Scripts/python.exe scripts/claim_user_data.py --phone 你的手机号`（需先登录一次）。

### 开发者：命令行

```powershell
# 1) 环境变量：复制模板并按需填写（至少填 AI_COMPANION_MASTER_KEY 与 DeepSeek Key）
Copy-Item .env.example .env

# 2) 一键准备并起服务
./scripts/dev.ps1

# 或者手动：
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e "backend[dev]"
docker compose -f docker/docker-compose.yml up -d postgres redis
Push-Location backend; .venv/Scripts/python.exe -m alembic upgrade head; Pop-Location
Push-Location backend; .venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000; Pop-Location
```

打开 `http://127.0.0.1:8000/docs` 可看接口文档；前端生产构建由后端在 `http://127.0.0.1:8000/` 直接托管。

## 前端

生产/日常使用：双击 `启动AI伴侣.bat`，由后端托管构建产物（`http://127.0.0.1:8000/`）。

开发调试（热更新）：

```powershell
./scripts/dev-web.ps1
# 或手动
cd frontend
pnpm install --registry=https://registry.npmmirror.com
pnpm dev
```

打开 `http://127.0.0.1:5273`。开发期登录态默认用 `X-User-Id`（`dev-user`），也可用「登录」页走验证码；管理员手机号在 `.env` 的 `AI_COMPANION_ADMIN_PHONES` 配置。

## 配置

所有配置走环境变量，前缀 `AI_COMPANION_`，见 [.env.example](.env.example)。

| 变量 | 作用 | 默认 |
|---|---|---|
| `AI_COMPANION_MASTER_KEY` | 供应商 Key 的信封加密主密钥（32 字节 base64） | 空（生产必须填） |
| `AI_COMPANION_DEEPSEEK_API_KEY` | 默认模型的官方 Key | 空 |
| `AI_COMPANION_ALLOW_PRIVATE_MODEL_ENDPOINTS` | 是否允许本地模型地址（Ollama 等） | `false` |
| `AI_COMPANION_TURN_COST_CAP_CNY` | 单轮成本上限，用于倒推上下文预算 | `0.02` |

## 验证

```powershell
./scripts/test.ps1
# 等价于：
Push-Location backend; .venv/Scripts/python.exe -m pytest -q; Pop-Location
```

测试覆盖：定价/预算公式、token 估算与裁剪、消息裁剪、SSE 解析与错误映射、路由降级与中断语义、
注册表预设、密钥加密、SSRF 防护、调用记账、HTTP 接口。

## 查询用量（真实调用落库后）

```powershell
# 启动服务后：
Invoke-RestMethod "http://127.0.0.1:8000/v1/me/usage/models?days=7" -Headers @{ "X-User-Id" = "dev-user" }
```

返回按模型的调用次数、输入/输出 token、缓存命中率、成本（元）与首字延迟均值，以及按天汇总。
`X-User-Id` 只是开发期占位，生产必须关闭 `AI_COMPANION_DEBUG_AUTH` 并接真实登录。

## 关键约定

- **模型网关统一接口**：业务只调 `ModelRouter.stream(task, messages)`，换供应商不改业务代码。
- **首 token 后不降级**：断流只允许续写/重新生成；内容拦截不换供应商（否则等于绕过审核）。
- **Key 永不回明文**：接口只回掩码，日志不含 Key，密文带防篡改校验。
- **上下文预算由成本倒推**：1M 窗口不等于默认塞满；默认经济档 16K。
