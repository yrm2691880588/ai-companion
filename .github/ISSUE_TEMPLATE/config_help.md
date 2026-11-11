---
name: 配置问题 / 启动失败
about: 按 README 走不通、docker 起不来、接口报错
title: "[Setup] "
labels: question
---

## 哪一步卡住了

<!--
例如：「双击 启动AI伴侣.bat 后窗口闪一下就没了」
不要只说「跑不起来」，说清卡在哪个动作。
-->

## 完整的错误信息

<!-- 把终端里的报错原样贴上来，不要自己总结 -->

```
在这里粘贴
```

## 已经试过什么

- [ ] 确认 Docker Desktop 已启动
- [ ] 确认 `.env` 里 `AI_COMPANION_MASTER_KEY` 已填（32 字节 base64）
- [ ] 确认 `companion-postgres` 容器在运行（`docker ps`）
- [ ] 删掉 `backend/.venv` 重新装过依赖

## 环境

| 项 | 值 |
|---|---|
| 系统 | Windows 10 / 11（具体版本） |
| Docker 版本 | |
| Python 版本 | `python --version` |
| Node 版本 | `node --version` |
| 访问地址 | `http://127.0.0.1:8000` 还是别的 |

<!--
贴 `.env` 里的报错时，务必先删掉 AI_COMPANION_MASTER_KEY 和各供应商的 API Key 值。
那些是真密钥，公开出来会被别人用掉。
-->
