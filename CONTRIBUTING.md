# 贡献指南

感谢愿意帮忙。本项目是**面向成年人的虚构陪伴工具**，开源自部署，不收费。

## 开始之前

请先读这三份，避免重复讨论已有决定：

| 文件 | 内容 |
|---|---|
| [README.md](README.md) | 项目定位、能力清单、快速开始 |
| [GLOSSARY.md](GLOSSARY.md) | 术语真源；新概念必须先在此登记 |
| [docs/adr/](docs/adr/) | 架构决策；已被决策过的事不要重开辩论 |

## 环境准备

### 后端

```powershell
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

### 数据库

需要 PostgreSQL 16 + pgvector。最快方式是：

```powershell
docker compose -f docker/docker-compose.yml up -d
```

### 前端

```powershell
cd frontend
pnpm install
```

## 提交前必须自测

**四项都要跑，缺一不可**（CI 也会跑，但本地先过能省时间）：

| 目的 | 命令 | 通过标准 |
|---|---|---|
| 后端单测 | `cd backend; .venv/Scripts/python.exe -m pytest -p no:cacheprovider` | 全绿 |
| 后端静态检查 | `cd backend; .venv/Scripts/python.exe -m ruff check app tests` | 无 error |
| 前端类型与构建 | `cd frontend; pnpm build` | tsc 无错 + 构建成功 |
| 前端页面验收 | `cd frontend; pnpm test:page` | 28 项全过 |

改动涉及语音、弹窗、菜单、模型配置时，再跑对应的专项脚本（见 `frontend/tests/`）。

## 代码规范

### 分层职责（硬约束）

| 层 | 路径 | 能做 | 不能做 |
|---|---|---|---|
| 业务语义 | `backend/app/domain/` | 所有业务规则、校验、状态流转 | — |
| 协议映射 | `backend/app/api/v1/` | 请求/响应映射 | 写业务判断、直接读数据库 |
| 技术实现 | `backend/app/infra/` | 仓储、外部调用、加密 | 判断业务合法性 |
| 表结构 | `backend/app/models/` | 声明字段 | 写逻辑 |

### 其他约定

- Python：`ruff` 格式化与检查，行宽 100；
- TypeScript：strict 模式，不用 `any` 绕过；
- 新概念先写 `GLOSSARY.md`；
- 用户可见文案不要硬编码在组件里；
- 不提交 `console.log`、调试开关、注释掉的旧代码。

## Pull Request

1. **一次只解决一个问题**，不要把重构和功能混在一起；
2. PR 描述里说明：改了什么、为什么、怎么验证的（贴命令输出或截图）；
3. 涉及以下改动请先开 issue 讨论：
   - 数据库 schema 或迁移
   - 公开 API 形状
   - 权限模型、内容边界规则
   - 新增第三方依赖
4. 破坏性改动必须说明迁移路径。

## 不要做的事

| 禁止 | 原因 |
|---|---|
| 提交 `.env` 或任何真实密钥 | 密钥泄露不可撤回 |
| 提交 `AGENTS.md`、`.agent-rules/` 等私人规则文件 | 那是维护者的私人工作偏好，不是项目资料 |
| 用 `git add .` 一把梭 | 会带走未跟踪的临时文件 |
| 提交 `frontend/dist/`、`node_modules/`、`__pycache__/` | 构建产物与依赖不入库 |
| 擅自改内容边界底线 | 见 `docs/adr/0006`，这是产品红线 |
| 在同一 PR 里顺手重构无关文件 | 评审成本会爆掉 |

## 提交信息

用中文或英文都可以，但要说清「做了什么」：

```
feat(voice): 接入火山语音识别与合成
fix(chat): 修正墓碑消息在流式接口中泄露
docs(adr): 补充跨端同步范围的决策
```

前缀参考：`feat` / `fix` / `docs` / `refactor` / `test` / `chore`。

## 关于规则文件

如果你在自己的分支里看到 `AGENTS.md` 或 `.agent-rules/`，**那是维护者本机的私人规则**，已通过 `.git/info/exclude` 排除。

- 不要把它们加进版本库；
- 不要为了"规范收纳"去改 `.gitignore`；
- 提交 PR 前用 `git status --short` 确认它们没出现在暂存区。

## 许可

提交贡献即表示你同意以本项目的 [MIT 许可证](LICENSE) 授权你的贡献。
