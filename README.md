# 个人 Jarvis 机器人

这是一个以飞书私聊为入口的个人 Jarvis MVP。当前实现覆盖 `docs/TASKS.md` 中 Day 1 和 Day 2 的本地代码骨架：

- FastAPI 服务和 `/health`
- 飞书 webhook challenge、消息解析、私聊过滤、白名单过滤
- 飞书消息去重
- 飞书文本回复客户端
- SQLite 初始化
- `processed_messages` 和 `ledger_entries` 表
- 基础记账流水解析和查询

## 快速开始

### 1. 创建环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

如果旧笔记本的 pip 不支持 editable pyproject 安装，可以使用：

```bash
pip install -r requirements-dev.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

至少需要配置：

```text
DATABASE_PATH=data/jarvis.db
EXPORT_DIR=data/exports
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
ALLOWED_FEISHU_USER_IDS=
OBSIDIAN_VAULT_PATH=
LLM_PROVIDER=openai-compatible
LLM_API_KEY=
LLM_MODEL=gpt-4.1-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_RESPONSES_PATH=/responses
LLM_TIMEOUT_SECONDS=20
```

`ALLOWED_FEISHU_USER_IDS` 可以先留空用于本地调试；正式接飞书时建议填入你自己的飞书 user_id。

如果要测试 Day 4 Obsidian 写入，请配置：

```text
OBSIDIAN_VAULT_PATH=/你的/Obsidian/Vault/路径
```

### 3. 初始化数据库

```bash
python scripts/init_db.py
```

### 4. 启动飞书本地联调

```bash
python scripts/start_feishu_dev.py
```

脚本会自动：

- 初始化数据库
- 启动 FastAPI
- 启动 cloudflared
- 打印飞书事件订阅地址

输出中会出现类似：

```text
Feishu event subscription request URL:
https://xxx.trycloudflare.com/webhook/feishu
```

把这个地址复制到飞书开放平台的事件订阅请求地址。

### 5. 手动启动服务

也可以手动启动 FastAPI：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

### 6. 飞书 webhook 地址

本地服务启动后，需要用 cloudflared 或 ngrok 暴露 HTTPS 地址，然后在飞书应用事件订阅里配置：

```text
https://你的公网地址/webhook/feishu
```

MVP 当前建议使用飞书 verification token 回调，不启用 encrypted callback。

### 7. cloudflared 暴露本地服务

如果已经安装 cloudflared：

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

复制输出中的 `https://xxx.trycloudflare.com`，飞书事件订阅的请求地址填写：

```text
https://xxx.trycloudflare.com/webhook/feishu
```

## 当前支持的文本

### ping

```text
ping
```

回复：

```text
pong
```

### 记账

```text
今天午饭 38
打车花了 26
买书 89
工资到账 12000
昨天买鞋退款 199
给小王转账 200
打车 48，待报销
打车报销到账 48
```

### 记账 P0 增强

```text
今天午饭 38，用招行信用卡，记到旅行账本 #出差
设置招行信用卡初始余额 1000
招行信用卡余额多少
新增分类 宠物 属于生活
有哪些分类
设置本月餐饮预算 2000
这个月餐饮还剩多少预算？
搜索出差
每月1号自动记账房租 3000
生成本月周期账单
```

当前支持：

- 多账本：通过“记到旅行账本”自动创建和记录
- 多账户：通过“用招行信用卡”“用支付宝”自动创建和记录
- 二级分类：如午饭归入餐饮/午餐，咖啡归入餐饮/咖啡
- 标签：通过 `#出差`、`#618` 等标签记录
- 月度预算：设置分类预算并查询剩余
- 预算提醒：记账后超过 80% 或超支时提醒
- 账单搜索：按备注、分类、原始输入和标签搜索
- 账户余额：基于初始余额和流水实时计算
- 分类管理：新增、隐藏、查看分类
- 周期账单模板：记录每月固定账单模板，并可生成本月流水

### 查询

```text
这个月餐饮花了多少？
今天花了多少钱？
有哪些待报销？
```

## 本地测试

```bash
python -m unittest discover
```

## Day 3 当前支持的待办和提醒

### 无时间待办

```text
记一下：买空气炸锅
```

### 一次性提醒

```text
明天下午 3 点提醒我交房租
下周五晚上 8 点提醒我买礼物
5 分钟后提醒我喝水
```

### 简单重复提醒

```text
每天早上 9 点提醒我看计划
每周一上午 10 点提醒我写周报
```

### 查询和完成

```text
今天有哪些待办？
全部未完成待办
完成买空气炸锅
```

### 关键提醒

消息里包含 `关键`、`重要` 或 `紧急` 时会标记为关键提醒，并提示你设置备用提醒：

```text
明天下午 3 点关键提醒我交房租
```

提醒调度器随 FastAPI 启动，默认每 60 秒扫描一次。可以通过 `.env` 调整：

```text
REMINDER_SCAN_INTERVAL_SECONDS=60
```

## Day 4 当前支持的 Obsidian 知识库

如果配置了 `OBSIDIAN_VAULT_PATH`，服务启动时会自动初始化 PARA 目录：

```text
00_Inbox/
01_Projects/
  个人机器人/
02_Areas/
  AI/
  个人成长/
  健康/
  财务/
  工作/
03_Resources/
  文章/
  工具/
  书籍/
  教程/
04_Archive/
```

可以发送：

```text
整理进知识库：个人机器人应该先支持飞书入口，并用 AI 辅助 PARA 分类。
帮我总结这段话：人工智能正在改变个人知识管理。
```

生成的 Markdown 包含 frontmatter、摘要、核心要点、和我的关系、可行动项、原始来源。分类不确定时，机器人会反问，不会乱放。

## Day 5 当前支持的安全和意图识别

敏感信息会在调用 AI 前被本地拦截：

```text
身份证号
银行卡号
密码
验证码
API key / token / secret
私钥
助记词
```

LLM 意图识别使用 OpenAI-compatible Responses API + JSON schema。未配置 `LLM_API_KEY` 时，会自动使用本地规则分类，确保机器人仍可用。旧的 `OPENAI_API_KEY`、`OPENAI_MODEL`、`OPENAI_BASE_URL`、`OPENAI_TIMEOUT_SECONDS` 仍会作为兼容 fallback 读取。

通用大模型配置：

```text
LLM_PROVIDER=openai-compatible
LLM_API_KEY=
LLM_MODEL=gpt-4.1-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_RESPONSES_PATH=/responses
LLM_TIMEOUT_SECONDS=20
```

如果切换到其他厂商，优先选择兼容 OpenAI Responses API 的 endpoint；否则后续需要为该厂商补一个适配器。

已覆盖的 intent：

```text
ledger.create
ledger.query
todo.create
todo.complete
todo.query
knowledge.capture_text
knowledge.capture_link
export.ledger_excel
clarify
unknown
```

30 条样例测试位于：

```text
tests/fixtures/intent_samples.json
```

## Day 6 当前支持的链接总结和 Excel 导出

### 链接总结

```text
总结这个链接 https://example.com
```

当前支持公开网页抓取：

- 检测 URL
- 抓取公开网页 HTML
- 提取标题和正文
- 生成摘要、要点、标签、相关双链和可行动项
- 写入 Obsidian Markdown
- 抓取失败时给出明确错误

需要先配置：

```text
OBSIDIAN_VAULT_PATH=/你的/Obsidian/Vault/路径
```

### Excel 导出

```text
导出本月账单
导出全部账本
导出待报销记录
```

导出字段包含账本、账户和标签。代码层也支持从 Excel 导入账单：

```python
from pathlib import Path
from app.services.export import LedgerExportService

LedgerExportService(db, Path("data/exports")).import_xlsx(Path("账单.xlsx"))
```

默认导出到：

```text
data/exports/
```

可以通过 `.env` 修改：

```text
EXPORT_DIR=data/exports
```

## Day 7 验收和试用

### 本地全链路验收

```bash
python scripts/day7_check.py
```

通过后会输出：

```text
Day 7 local acceptance check passed.
```

### 试用前检查

```bash
python scripts/preflight_check.py
```

它会检查：

- `.env`
- SQLite 表结构
- Obsidian vault 路径
- Excel 导出目录
- 日志目录
- cloudflared
- 飞书配置
- LLM 配置
- macOS 自动休眠设置

完整旧笔记本试用指南见：

```text
docs/OLD_LAPTOP_TRIAL.md
```

### 创建今日试用日志

```bash
python scripts/start_trial_day.py
```

日志会生成在：

```text
docs/trial/YYYY-MM-DD.md
```

汇总模板见：

```text
docs/TRIAL_LOG.md
```

### 备份 SQLite

```bash
python scripts/backup_db.py
```

备份文件会生成在：

```text
data/backups/
```

### 日志

运行服务后日志会同时输出到控制台和文件：

```text
logs/jarvis.log
```

### 旧笔记本试用检查

开始 7 天试用前建议确认：

- 旧笔记本接电源
- 关闭自动休眠
- 运行 `python scripts/preflight_check.py`
- 运行 `python scripts/start_trial_day.py`
- FastAPI 可重启
- cloudflared 可重新启动并更新飞书 webhook
- SQLite 可以通过 `scripts/backup_db.py` 备份
- 每天记录失败样例
- 每天检查提醒是否漏发
- 每天检查 Obsidian 输出质量

## 云部署

腾讯云 Lighthouse / OpenCloudOS 9 部署指南见：

```text
docs/CLOUD_DEPLOY_TENCENT_LIGHTHOUSE.md
```

云端 Obsidian 推荐使用 Git 仓库同步。开启后，每次写入知识库笔记会尝试 `git add`、`git commit`、`git push`：

```text
OBSIDIAN_GIT_SYNC_ENABLED=true
OBSIDIAN_GIT_PUSH_ENABLED=true
```
