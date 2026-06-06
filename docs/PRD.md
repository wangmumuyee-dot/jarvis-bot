# 个人 Jarvis 机器人 MVP PRD

## 1. 文档信息

- 产品名称：个人 Jarvis 机器人
- 版本：MVP v0.1
- 目标周期：7 天完成第一个可试用版本
- 主要入口：飞书应用机器人私聊
- 第一版服务端：旧笔记本常驻运行
- 长期方向：迁移到云服务器，扩展为个人信息操作系统

## 2. 产品愿景

构建一个以飞书为入口的个人 Jarvis。用户只需要用自然语言发送消息，机器人就能把零散输入转化为结构化账本、待办提醒和 Obsidian 知识笔记。

产品长期目标是成为用户的个人信息输入中枢：

- 低摩擦输入
- 自动分类和沉淀
- 可靠提醒
- 可查询、可复盘、可迁移
- 数据长期掌握在用户自己手里

## 3. MVP 目标

在 7 天内实现一个真实可用的 MVP：

> 用户可以通过飞书私聊机器人完成记账、待办、提醒、文本或链接总结入 Obsidian。机器人使用 SQLite 作为唯一真实数据源，使用通用 LLM API 做自然语言理解，并在调用 AI 前进行敏感信息检测。

MVP 成功不以功能数量衡量，而以真实使用验证衡量：

- 用户愿意连续 7 天使用
- 30 条真实输入中至少 27 条正确处理
- 提醒不漏发
- 数据可查看、可导出、可备份

## 4. 用户和场景

### 4.1 用户

用户本人。

### 4.2 高频场景

#### 场景 1：快速记账

用户不想打开记账软件，只想发一句话：

```text
今天午饭 38
```

机器人识别为支出，写入 SQLite，并回复确认。

#### 场景 2：创建提醒

用户想到一个之后要做的事：

```text
明天下午 3 点提醒我交房租
```

机器人创建待办和提醒，到点通过飞书提醒。

#### 场景 3：记录无时间待办

用户只想先记下来：

```text
记一下：买空气炸锅
```

机器人创建无时间待办。

#### 场景 4：简单重复提醒

用户需要周期性提醒：

```text
每周一上午 10 点提醒我写周报
```

机器人创建重复提醒。

#### 场景 5：总结文本入库

用户发一段想法或摘录：

```text
把这段话整理进知识库：...
```

机器人整理为 Markdown，并写入 Obsidian PARA 目录。

#### 场景 6：总结链接入库

用户发送链接：

```text
总结这个链接 https://example.com
```

机器人抓取正文、总结、打标签、写入 Obsidian。

## 5. 产品范围

### 5.1 MVP 范围内

- 飞书应用机器人私聊
- 用户白名单
- FastAPI webhook
- SQLite 数据库
- 通用 LLM API 意图识别
- 高敏信息本地检测
- 账本流水记录
- 简单账本查询
- Excel 导出
- 待办创建、查询、完成
- 一次性提醒
- 简单重复提醒
- 提醒重试和状态记录
- Obsidian PARA 知识库写入
- 文本总结
- 链接总结
- 基础日志

### 5.2 MVP 范围外

- 微信、企业微信、Telegram 等其他入口
- 群聊支持
- 多用户支持
- 多 agent 协作
- Web 前端
- 手机 App
- 项目管理看板
- 子任务
- 多账户财务系统
- 自动资产负债统计
- Obsidian 全库自动重构
- 语音输入
- 本地大模型部署

## 6. 功能设计

### 6.1 飞书入口

#### 描述

机器人通过飞书应用机器人接收用户私聊消息，并通过飞书 API 回复。

#### 规则

- 只处理私聊
- 只处理白名单 user_id
- 忽略群聊
- 忽略非文本消息，或回复暂不支持
- 需要事件去重

#### 用户反馈

每次处理必须给出清晰反馈：

- 成功：说明已做什么
- 失败：说明失败原因
- 不确定：向用户提出一个澄清问题

### 6.2 消息处理流程

```text
飞书消息
  -> webhook 校验
  -> 用户白名单校验
  -> 消息去重
  -> 敏感信息检测
  -> 意图识别
  -> 工具路由
  -> 写入 SQLite / Obsidian / Excel
  -> 飞书回复
```

### 6.3 意图识别

#### 支持意图

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

#### 输出要求

模型必须输出结构化 JSON，并包含：

- intent
- confidence
- extracted fields
- missing fields
- user-facing confirmation text

低置信度时必须反问。

### 6.4 账本流水

#### 支持类型

```text
expense
income
refund
transfer
reimbursement
```

#### 分类

第一版分类可以简单：

```text
餐饮
交通
购物
娱乐
学习
健康
居住
收入
退款
转账
报销
其他
```

#### 修改能力

第一版建议支持：

```text
撤销上一条
修改上一条金额
修改上一条分类
```

如果实现成本过高，可以延后到 MVP 后半段。

### 6.5 待办提醒

#### 待办类型

- 无时间待办
- 一次性定时待办
- 简单重复待办

#### 状态

```text
pending
done
cancelled
```

#### 提醒状态

```text
pending
sent
failed
acknowledged
cancelled
```

#### 关键提醒

关键提醒需要备用机制。MVP 可以先提醒用户手动创建备用提醒，后续再接入飞书日历。

### 6.6 Obsidian 知识库

#### 目录结构

```text
00_Inbox/
01_Projects/
02_Areas/
03_Resources/
04_Archive/
```

#### 写入原则

- 内容属于当前项目时写入 `01_Projects`
- 内容属于长期领域时写入 `02_Areas`
- 外部资料写入 `03_Resources`
- 无法判断时写入 `00_Inbox`
- 不自动改动已有笔记

#### Markdown frontmatter

```yaml
type: resource
source_type: link
source_url: ""
created_at: "2026-06-02 21:30"
tags: []
related: []
```

#### 正文结构

```markdown
# 标题

## 摘要

## 核心要点

## 和我的关系

## 可行动项

## 原始来源
```

### 6.7 安全保护

#### 敏感信息检测

调用 LLM 前检测：

- 身份证号
- 银行卡号
- 密码关键词
- CVV
- 验证码
- API key
- private key
- secret
- token
- 助记词

命中后不调用 LLM，不保存原文。

#### 密钥管理

所有密钥通过 `.env` 管理：

```text
LLM_API_KEY
LLM_MODEL
LLM_BASE_URL
LLM_RESPONSES_PATH
FEISHU_APP_ID
FEISHU_APP_SECRET
FEISHU_VERIFICATION_TOKEN
FEISHU_ENCRYPT_KEY
ALLOWED_FEISHU_USER_IDS
DATABASE_URL
OBSIDIAN_VAULT_PATH
```

## 7. 技术架构

### 7.1 推荐架构

```text
Feishu App Bot
  -> FastAPI webhook
  -> security filter
  -> LLM intent parser
  -> tool router
      -> ledger service -> SQLite -> Excel export
      -> todo service -> SQLite
      -> reminder service -> scheduler -> Feishu message
      -> knowledge service -> Markdown -> Obsidian vault
```

### 7.2 项目结构建议

```text
app/
  main.py
  config.py
  logging.py

  feishu/
    client.py
    webhook.py
    schemas.py

  ai/
    intent.py
    summarize.py
    prompts/

  security/
    sensitive.py
    auth.py

  storage/
    db.py
    models.py
    migrations/

  services/
    ledger.py
    todo.py
    reminder.py
    knowledge.py
    export.py

  scheduler/
    jobs.py

  utils/
    time_parse.py
    markdown.py
    links.py

tests/
  fixtures/
  test_intent.py
  test_sensitive.py
  test_ledger.py
  test_todo.py
```

## 8. 数据模型

### 8.1 ledger_entries

```text
id
entry_type
amount
currency
category
note
occurred_at
reimbursable
reimbursement_status
source_text
created_at
updated_at
```

### 8.2 todos

```text
id
title
status
due_at
recurrence_rule
priority
source_text
created_at
completed_at
updated_at
```

### 8.3 reminders

```text
id
todo_id
remind_at
recurrence_rule
priority
backup_required
backup_created
status
retry_count
last_error
sent_at
created_at
updated_at
```

### 8.4 knowledge_notes

```text
id
title
source_type
source_url
obsidian_path
tags
related
summary
created_at
updated_at
```

### 8.5 processed_messages

用于飞书消息去重。

```text
id
feishu_message_id
event_id
processed_at
status
```

## 9. 交付计划

### Day 1：飞书收发消息

交付：

- FastAPI 服务
- 飞书 webhook
- 私聊消息接收
- 飞书回复
- 白名单校验
- 消息去重

验收：

- 用户发一条消息，机器人能回复

### Day 2：SQLite 和记账

交付：

- SQLite 初始化
- ledger_entries 表
- 记账写入
- 简单查询

验收：

- `今天午饭 38` 可以写入数据库并回复确认

### Day 3：待办和提醒

交付：

- todos 表
- reminders 表
- 创建提醒
- 定时扫描
- 飞书主动提醒
- 重试记录

验收：

- 创建一个 5 分钟后的提醒，到点收到飞书消息

### Day 4：Obsidian Markdown

交付：

- vault 路径配置
- PARA 目录初始化
- 文本总结 Markdown 写入
- 分类不确定时反问

验收：

- 文本能生成一篇 Markdown 笔记并出现在 Obsidian vault

### Day 5：LLM 意图识别

交付：

- JSON schema
- prompt
- intent router
- 敏感信息检测
- 30 条测试样例初稿

验收：

- 30 条输入至少 27 条意图识别正确

### Day 6：链接总结和 Excel 导出

交付：

- 链接正文抓取
- 链接总结入库
- 账本 Excel 导出

验收：

- 一个公开链接能被总结并写入 Obsidian
- 账本能导出 Excel

### Day 7：稳定性验收

交付：

- 错误处理优化
- 日志检查
- 真实输入测试
- README 初稿
- 进入 7 天试用

验收：

- 全链路可用
- 开始真实使用

## 10. MVP 验收清单

- [ ] 飞书机器人私聊可用
- [ ] 只响应白名单用户
- [ ] webhook 校验可用
- [ ] 消息去重可用
- [ ] 高敏信息不会发送给 LLM
- [ ] LLM 意图识别可用
- [ ] 30 条真实输入至少 27 条正确
- [ ] 账本流水可写入 SQLite
- [ ] 账本流水可查询
- [ ] Excel 可导出
- [ ] 待办可创建
- [ ] 待办可完成
- [ ] 一次性提醒可触发
- [ ] 简单重复提醒可触发
- [ ] 提醒失败可重试
- [ ] Obsidian PARA 目录可初始化
- [ ] 文本可总结成 Markdown
- [ ] 链接可总结成 Markdown
- [ ] 日志可排查错误
- [ ] 旧笔记本可常驻运行

## 11. 后续路线

### v0.2

- 飞书日历备用提醒
- 更好的时间解析
- 修改和撤销记录
- 日报和晚间复盘
- 自动 Excel 定时导出

### v0.3

- 迁移云服务器
- Obsidian 同步方案
- 知识库检索
- 消费分析
- 周报和月报

### v1.0

- 多 agent 协作
- 项目管理能力
- 语音输入
- 主动建议
- 长期记忆和个性化偏好
