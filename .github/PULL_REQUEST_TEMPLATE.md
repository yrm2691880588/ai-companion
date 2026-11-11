## 这个 PR 做了什么

<!-- 一句话说清。如果修的是 Issue，写 Closes #123 -->

## 为什么这样做

<!-- 说明取舍。如果推翻既有设计，请先看 architecture/ 里有没有相关 ADR -->

## 怎么验证的

<!-- 贴命令与输出，不要只写「已测试」 -->

```powershell
# 后端
cd backend; .venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check app tests
.venv/Scripts/python.exe -m ruff format --check app tests

# 前端
cd frontend; pnpm build; pnpm lint
```

## 检查清单

- [ ] 一次只解决一个问题（没有把重构和新功能混在一起）
- [ ] 新增/修改的行为有对应测试
- [ ] 未提交 `.env`、密钥、日志、`node_modules/`、`dist/`
- [ ] 改动涉及 API 契约时，同步更新了调用方与测试
- [ ] 没有留下 `TODO`、调试输出、注释掉的代码
