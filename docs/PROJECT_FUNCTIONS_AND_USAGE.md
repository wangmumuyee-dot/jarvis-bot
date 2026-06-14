# 个人 Jarvis 机器人功能与使用手册

本文档基于当前代码实现整理，覆盖项目已有功能、配置方法、启动方式、飞书接入、可用文本指令、数据存储、运维脚本和已知限制。

## 1. 项目概览

个人 Jarvis 机器人是一个以飞书私聊为入口的个人信息输入中枢。用户通过自然语言给飞书机器人发消息，服务端会把消息路由到记账、待办提醒、知识库、Excel 导出、财务分析等功能。

当前技术栈：

- 服务框架：FastAPI
- 入口：飞书机器人 webhook
- 数据库：SQLite
- 知识库输出：Obsidian Markdown
- Excel 导入导出：openpyxl
- AI 能力：OpenAI-compatible Responses API，可留空使用本地规则 fallback
- 后台任务：提醒扫描线程

核心入口文件：

- `app/main.py`：FastAPI 应用、飞书 webhook、文本路由
- `app/config.py`：环境变量配置
- `app/storage/db.py`：SQLite 表结构和初始化
- `app/services/ledger.py`：记账、预算、账户、分类、欠款、统计
- `app/services/todo.py`：待办和提醒
- `app/services/knowledge.py`：Obsidian 知识库写入
- `app/services/export.py`：账本 Excel 导入导出
- `app/services/finance_p2.py`：愿望储蓄、模板、导入、月报、消费分析、同步检查
- `app/services/finance_web.py`：财务网页仪表盘、最近流水和结构化记账
- `app/web/static/`：财务网页前端和 PWA 静态资源

## 2. 当前实现的功能

### 2.1 服务与飞书入口

已实现：

- FastAPI 服务
- `/health` 健康检查
- `/webhook/feishu` 飞书事件回调
- 飞书 URL challenge 校验
- 飞书 verification token 校验
- 私聊过滤：只处理 `p2p` 私聊
- 文本消息过滤：非文本消息会回复暂不支持
- 用户白名单：通过 `ALLOWED_FEISHU_USER_IDS` 限制 user_id 或 open_id
- 事件去重：通过 `processed_messages` 防止重复入库
- 飞书文本回复

暂不支持：

- 飞书 encrypted callback
- 群聊处理
- 非文本消息处理
- 多用户隔离

### 2.2 敏感信息保护

所有消息进入 AI 或业务处理前，会先做本地敏感信息检测。

会拦截：

- 身份证号
- 银行卡号
- 验证码
- API key、token、secret
- 私钥
- 明显密码类文本

命中后机器人会回复隐私保护提示，不会调用 AI，也不会保存原文。

Excel 脱敏导出会对身份证、银行卡、验证码、密钥、密码字段进行替换。

### 2.3 意图识别与路由

文本路由顺序：

1. 敏感信息检测
2. `ping` 调试命令
3. 快捷模板展开
4. 财务 P2 功能
5. Excel 导出
6. Obsidian 知识库
7. 待办提醒
8. 记账功能
9. LLM 意图识别 fallback
10. 本地规则 fallback

支持的 LLM 意图包括：

- `ledger.create`
- `ledger.query`
- `todo.create`
- `todo.complete`
- `todo.query`
- `knowledge.capture_text`
- `knowledge.capture_link`
- `export.ledger_excel`
- `clarify`
- `unknown`

如果没有配置 `LLM_API_KEY`，系统会使用本地规则识别常见输入。

### 2.4 财务网页工作台

访问地址：

```text
http://127.0.0.1:8000/finance
```

公网域名部署示例：

```text
https://finance.example.com/finance
```

网页支持：

- 快速结构化记账：类型、金额、币种、分类、日期、账户、账本、备注、标签、待报销
- 本月概览：收入、支出、净额、待报销
- 最近流水列表
- 分类支出排行
- 预算进度
- 愿望储蓄进度
- 欠款概览
- 预算表单：设置分类月度预算
- 欠款表单：我借出、我借入、对方还我、我还对方
- 愿望表单：创建目标、存入、查询进度
- 模板表单：保存快捷模板
- 周期表单：创建每月固定账单
- 账户表单：查询余额、设置初始余额
- 分类表单：新增分类、隐藏分类
- 信用卡表单：设置账单日和还款日
- 周期设置表单：设置财务月起始日和财务周起始日
- 搜索表单：按关键词搜索账单
- Excel 上传：从网页选择 `.xlsx` 并导入账单
- Excel 下载：本月、全部、待报销、脱敏账单
- 批处理按钮：财务月报、消费分析、同步状态
- 命令面板
- PWA 安装：部署到 HTTPS 后，可从 iPhone Safari 添加到主屏幕，以独立窗口打开

命令面板复用原飞书文本路由，因此现有财务指令都可以从网页执行：

```text
设置本月餐饮预算 2000
本月分类统计
有哪些欠款
生成本月周期账单
查看愿望清单
分析本月消费
导出本月账单
同步状态
```

财务网页 API：

```text
GET  /api/finance/dashboard
GET  /api/finance/options
GET  /api/finance/entries
POST /api/finance/entries
POST /api/finance/command
GET  /api/finance/export
POST /api/finance/import
```

公网部署时建议设置：

```text
WEB_AUTH_TOKEN=一串足够长的随机口令
```

设置后，财务 API 需要请求头：

```text
X-Jarvis-Web-Token: 你的口令
```

网页会在第一次访问受保护 API 时显示访问口令面板。保存后，口令会存入浏览器本地，并自动附加到后续请求。

### 2.5 记账流水

支持流水类型：

- 支出：`expense`
- 收入：`income`
- 退款：`refund`
- 转账：`transfer`
- 报销到账：`reimbursement`

支持字段：

- 金额
- 币种
- 分类和子分类
- 备注
- 发生时间
- 账本
- 账户
- 转入账户
- 标签
- 是否待报销
- 报销状态
- 原始输入

支持币种：

- CNY
- USD
- HKD
- JPY
- EUR

注意：当前只识别币种，不做汇率换算。

记账示例：

```text
今天午饭 38
昨天打车 26
买书花了 89
工资到账 12000
昨天买鞋退款 199
给小王转账 200
打车 48，待报销
打车报销到账 48
买资料 12美元
今天午饭 38，用招行信用卡，记到旅行账本 #出差
从招行卡转到支付宝 500
```

系统会自动识别：

- 日期：今天、昨天、前天
- 分类：餐饮、交通、购物、学习、健康、居住、娱乐、收入、退款、转账、报销、其他
- 餐饮子分类：早餐、午餐、晚餐、咖啡
- 账户：`用招行信用卡`、`从支付宝`
- 账本：`记到旅行账本`
- 标签：`#出差`、`#618`

### 2.6 账本查询与搜索

支持查询：

```text
今天花了多少钱？
这个月餐饮花了多少？
本月收入多少？
有哪些待报销？
```

支持账单搜索：

```text
搜索出差
查找午饭
账单里找咖啡
```

搜索范围包括：

- 备注
- 分类
- 原始输入
- 标签

### 2.7 预算管理

支持设置月度分类预算：

```text
设置本月餐饮预算 2000
餐饮预算设置为 2000
```

支持查询预算：

```text
这个月餐饮还剩多少预算？
本月餐饮预算用了多少？
```

记账后如果分类预算已使用超过 80% 或超支，会在回复中附带预算提醒。

### 2.8 分类管理

支持查看、新增、隐藏分类：

```text
有哪些分类
分类列表
新增分类 宠物 属于生活
隐藏分类 宠物
停用分类 宠物
```

### 2.9 账户和余额

支持账户自动创建和余额计算：

```text
设置招行信用卡初始余额 1000
招行信用卡余额多少
支付宝余额多少
```

余额计算规则：

- 初始余额加收入、退款、报销
- 减支出、转出
- 加转入

账户类型会按名称推断：

- 含“信用卡”“花呗”“白条”：信用账户
- 含“支付宝”“微信”：钱包
- 含“现金”：现金
- 含“卡”：借记卡
- 其他：资产账户

### 2.10 信用卡账单日

支持设置和查询信用卡账单日、还款日：

```text
设置招行信用卡账单日5号还款日25号
招行信用卡还款日
信用卡账单日
```

### 2.11 欠款管理

支持记录我借出、我借入、还款抵扣和查询未结清欠款：

```text
借给小王 500
小王还我 200
我向小李借了 300
我还小李 100
有哪些欠款
查看欠款列表
```

还款会优先抵扣同一人、同一币种下最早的未结清欠款。

### 2.12 财务周期和统计

支持设置财务月和财务周起始日：

```text
设置每月从5号开始
设置每周从周一开始
财务周期设置
```

支持统计：

```text
本月分类统计
本月分类排行
本月账单日历
```

说明：

- `ledger.py` 中的分类统计和账单日历使用财务月设置。
- `finance_p2.py` 的财务月报和消费分析使用自然月。

### 2.13 周期账单

支持创建每月固定流水模板：

```text
每月1号自动记账房租 3000
每月15号周期账单工资 12000
```

支持生成本月到期周期账单：

```text
生成本月周期账单
执行周期账单
生成周期账单
```

生成规则：

- 每月只生成一次
- 如果设定日大于当月最后一天，会使用当月最后一天
- 只生成已到期的周期账单

### 2.14 待办和提醒

支持无时间待办：

```text
记一下：买空气炸锅
记下 预约体检
待办 整理发票
```

支持一次性提醒：

```text
明天下午 3 点提醒我交房租
下周五晚上 8 点提醒我买礼物
10分钟后提醒我休息
2小时后提醒我检查任务
```

支持重复提醒：

```text
每天早上 9 点提醒我看计划
每日晚上 10 点提醒我复盘
每周一上午 10 点提醒我写周报
```

支持关键提醒：

```text
明天下午 3 点重要提醒我交房租
后天上午 9 点关键提醒我体检
```

关键提醒会标记 `backup_required=1`，回复中会建议同步设置飞书日历或手机日历作为备用。

支持完成待办：

```text
完成买空气炸锅
做完整理发票
已完成预约体检
```

支持查询待办：

```text
今天待办
全部未完成待办
有哪些待办
查询待办
```

提醒发送机制：

- 服务启动后会开启后台提醒扫描线程。
- 默认每 60 秒扫描一次，可通过 `REMINDER_SCAN_INTERVAL_SECONDS` 配置。
- 到期提醒通过飞书主动消息发送给 `feishu_open_id`。
- 发送失败会重试，最多 3 次。
- 重复提醒发送成功后，会自动创建下一次提醒。

### 2.15 Obsidian 知识库写入

需要配置 `OBSIDIAN_VAULT_PATH`。

支持文本整理入库：

```text
整理进知识库：这里是一段想法
放进知识库：关于 AI agent 的一些思考
写入知识库：今天复盘内容
总结这段话：...
帮我整理：...
沉淀成笔记：...
```

支持链接总结入库：

```text
总结这个链接 https://example.com/article
整理链接 https://example.com/article
把这个链接放进知识库 https://example.com/article
```

写入内容包括：

- YAML frontmatter
- 标题
- 摘要
- 核心要点
- 和我的关系
- 可行动项
- 原始来源

默认 PARA 目录：

- `00_Inbox`
- `01_Projects`
- `01_Projects/个人机器人`
- `02_Areas/AI`
- `02_Areas/个人成长`
- `02_Areas/健康`
- `02_Areas/财务`
- `02_Areas/工作`
- `03_Resources/文章`
- `03_Resources/工具`
- `03_Resources/书籍`
- `03_Resources/教程`
- `04_Archive`

分类规则：

- 包含“个人机器人”“Jarvis”“飞书机器人”：`01_Projects/个人机器人`
- 包含 AI、agent、OpenAI、大模型、人工智能：`02_Areas/AI`
- 包含财务、记账、预算、报销、消费：`02_Areas/财务`
- 包含健康、运动、睡眠、饮食：`02_Areas/健康`
- 包含工作、会议、项目管理、OKR：`02_Areas/工作`
- 链接或文章类内容：`03_Resources/文章`
- 不确定时会反问放到哪个目录

如果配置了 LLM，会优先使用 LLM 生成摘要；否则使用本地摘要规则。

### 2.16 Obsidian Git 同步

可通过环境变量开启：

```text
OBSIDIAN_GIT_SYNC_ENABLED=true
OBSIDIAN_GIT_PUSH_ENABLED=true
```

开启后，写入 Obsidian 笔记或财务月报后会尝试：

1. `git add`
2. `git commit`
3. `git push`，如果 `OBSIDIAN_GIT_PUSH_ENABLED=true`

支持同步检查：

```text
同步状态
执行同步
多设备同步
同步 Obsidian
```

同步检查会在 Obsidian `00_Inbox/.jarvis-sync-check.md` 写入检查文件，并记录 `sync_events`。

### 2.17 Excel 导出

支持导出全部、本月、待报销账单：

```text
导出账单
导出本月账单
导出待报销账单
导出 Excel
导出脱敏账单
```

导出文件位于 `EXPORT_DIR`，默认 `data/exports`。

Excel 表头包括：

- ID
- 账本
- 账户
- 类型
- 金额
- 币种
- 分类
- 备注
- 标签
- 发生时间
- 是否待报销
- 报销状态
- 原始输入
- 创建时间

### 2.18 Excel 自动导入

支持把 `.xlsx` 放到：

```text
data/exports/imports/
```

然后发送：

```text
自动导入账单
导入账单
导入Excel
```

导入后：

- 逐行读取 Excel
- 根据“金额”“备注”“账户”“账本”“标签”等列拼成自然语言
- 调用记账解析创建流水
- 成功导入的文件移动到 `imports/imported/`
- 结果写入 `import_jobs`

### 2.19 愿望储蓄

支持设置、追加进度、查看进度、查看清单：

```text
创建愿望目标 相机 5000
设置储蓄目标 旅行 10000
为相机存钱 1200
相机储蓄进度
查看愿望清单
有哪些储蓄目标
```

达到目标金额后状态会变成 `completed`。

### 2.20 快捷模板

支持保存常用指令：

```text
新增模板 午饭 = 今天午饭 38
创建快捷模板 通勤 = 今天地铁 6
设置模板 咖啡 = 今天咖啡 18 #日常
```

支持使用模板：

```text
使用模板 午饭
执行模板 通勤
套用模板 咖啡
```

使用模板会展开为模板中的原始指令，再走完整路由。系统会防止模板指向自身造成循环。

支持查看模板：

```text
查看快捷模板列表
有哪些快捷模板
常用模板列表
```

### 2.21 财务月报和消费分析

支持消费分析：

```text
分析本月消费
消费分析
消费建议
省钱建议
```

分析内容包括：

- 本月支出最高分类
- 收入、支出、净额
- 预算超支或接近上限提醒
- 本地省钱建议
- 如配置 LLM，则基于账本事实生成更自然的中文建议

支持生成 Obsidian 财务月报：

```text
生成本月财务月报
生成消费月报
写入财务月报 Obsidian
```

月报会写入：

```text
OBSIDIAN_VAULT_PATH/02_Areas/财务/
```

内容包括：

- 总览
- 分类支出
- 消费分析

## 3. 环境配置

### 3.1 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

如果 editable 安装不可用：

```bash
pip install -r requirements-dev.txt
```

完整运行依赖也可用：

```bash
pip install -r requirements.txt
```

### 3.2 配置 `.env`

推荐使用交互脚本：

```bash
python scripts/configure_env.py
```

也可以复制示例文件：

```bash
cp .env.example .env
```

关键配置：

```text
DATABASE_PATH=data/jarvis.db
EXPORT_DIR=data/exports
OBSIDIAN_VAULT_PATH=
OBSIDIAN_GIT_SYNC_ENABLED=false
OBSIDIAN_GIT_PUSH_ENABLED=true
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
ALLOWED_FEISHU_USER_IDS=
LLM_PROVIDER=openai-compatible
LLM_API_KEY=
LLM_MODEL=gpt-4.1-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_RESPONSES_PATH=/responses
LLM_TIMEOUT_SECONDS=20
WEB_AUTH_TOKEN=
REMINDER_SCAN_INTERVAL_SECONDS=60
```

说明：

- `ALLOWED_FEISHU_USER_IDS` 可以填飞书 user_id 或 open_id，多个用英文逗号分隔。
- 本地调试可留空白名单，正式使用建议只填自己的 ID。
- `LLM_API_KEY` 可留空，系统会使用本地规则 fallback。
- 要使用知识库写入、链接总结、财务月报，需要配置 `OBSIDIAN_VAULT_PATH`。
- 要把财务网页部署到公网域名，建议设置 `WEB_AUTH_TOKEN`。

### 3.3 初始化数据库

```bash
python scripts/init_db.py
```

初始化会创建所有表，并写入默认账本、账户、分类和财务周期设置。

### 3.4 启动服务

手动启动：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

本地飞书联调启动：

```bash
python scripts/start_feishu_dev.py
```

该脚本会：

1. 初始化数据库
2. 启动 FastAPI
3. 启动 cloudflared
4. 打印飞书事件订阅地址

输出类似：

```text
https://xxx.trycloudflare.com/webhook/feishu
```

把该地址填入飞书开放平台事件订阅请求地址。

## 4. 飞书接入方式

1. 在飞书开放平台创建应用。
2. 配置机器人能力。
3. 配置事件订阅。
4. 请求地址填写：

```text
https://你的公网地址/webhook/feishu
```

5. 使用 verification token 回调方式。
6. `.env` 填入：

```text
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
ALLOWED_FEISHU_USER_IDS=
```

本地开发时可以使用 cloudflared：

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

当前不启用 encrypted callback。如果飞书 payload 包含 `encrypt`，服务会返回 501。

## 5. 运维和辅助脚本

### 5.1 环境检查

```bash
python scripts/preflight_check.py
```

检查内容：

- `.env`
- SQLite 数据库和必要表
- Obsidian 路径
- Obsidian Git 状态
- Excel 导出目录
- 日志目录
- cloudflared
- 飞书配置
- LLM 配置
- macOS 电源休眠设置

### 5.2 数据库备份

```bash
python scripts/backup_db.py
```

会备份当前 SQLite 数据库。

### 5.3 试用日记录

```bash
python scripts/start_trial_day.py
python scripts/day7_check.py
```

用于 7 天 MVP 试用记录和检查。

### 5.4 Obsidian Git 同步脚本

```bash
python scripts/sync_obsidian_git.py
```

用于手动同步 Obsidian Git 仓库。

### 5.5 云部署

云部署说明见：

```text
docs/CLOUD_DEPLOY_TENCENT_LIGHTHOUSE.md
```

systemd 服务文件：

```text
deploy/jarvis-bot.service
deploy/cloudflared-jarvis-quick.service
```

## 6. 数据存储说明

SQLite 默认位置：

```text
data/jarvis.db
```

主要表：

- `processed_messages`：飞书消息去重和处理状态
- `ledger_entries`：账本流水
- `ledger_books`：账本
- `ledger_accounts`：账户
- `ledger_categories`：分类
- `ledger_tags`：标签
- `ledger_entry_tags`：流水标签关系
- `budgets`：预算
- `recurring_ledger_entries`：周期账单模板
- `ledger_debts`：欠款
- `finance_settings`：财务周期设置
- `saving_goals`：愿望储蓄目标
- `quick_templates`：快捷模板
- `import_jobs`：账单导入记录
- `sync_events`：同步事件
- `todos`：待办
- `reminders`：提醒
- `knowledge_notes`：知识库笔记索引

导出文件默认位置：

```text
data/exports/
```

导入文件放置位置：

```text
data/exports/imports/
```

日志目录：

```text
logs/
```

## 7. 测试方法

运行全部测试：

```bash
pytest
```

当前测试覆盖：

- 记账解析、创建、查询、预算、账户、分类、信用卡、欠款、统计
- 待办创建、提醒、完成、查询
- 知识库文本和链接写入
- Excel 导出、脱敏导出、导入
- 财务 P2 功能
- 敏感信息检测
- 意图识别

## 8. 常用指令速查

```text
ping
今天午饭 38
这个月餐饮花了多少？
设置本月餐饮预算 2000
这个月餐饮还剩多少预算？
搜索出差
新增分类 宠物 属于生活
设置招行信用卡初始余额 1000
招行信用卡余额多少
设置招行信用卡账单日5号还款日25号
借给小王 500
小王还我 200
有哪些欠款
设置每月从5号开始
本月分类统计
本月账单日历
每月1号自动记账房租 3000
生成本月周期账单
记一下：买空气炸锅
明天下午 3 点提醒我交房租
每天早上 9 点提醒我看计划
完成买空气炸锅
全部未完成待办
整理进知识库：这里是一段想法
总结这个链接 https://example.com/article
导出本月账单
导出脱敏账单
自动导入账单
创建愿望目标 相机 5000
为相机存钱 1200
相机储蓄进度
新增模板 午饭 = 今天午饭 38
使用模板 午饭
查看快捷模板列表
分析本月消费
生成本月财务月报
同步状态
```

## 9. 已知限制

- 只支持飞书私聊，不支持群聊。
- 只支持文本消息，不支持图片、语音、文件。
- 飞书 encrypted callback 未启用。
- 当前是单用户 MVP，多用户数据隔离未实现。
- 记账解析主要依赖规则，复杂自然语言可能需要 LLM 或后续增强。
- 外币只记录币种，不进行汇率换算。
- Excel 导入依赖固定表头和规则解析，不是完整银行账单适配器。
- 提醒依赖服务常驻和飞书发送能力，关键提醒仍建议设置手机或日历备用。
- Obsidian Git 同步要求 vault 本身是 Git 仓库，并且运行环境已配置好 Git 凭据。
- 链接总结只能抓取公开网页，登录态、反爬或动态渲染页面可能失败。
