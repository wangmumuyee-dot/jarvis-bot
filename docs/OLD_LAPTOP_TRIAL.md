# 旧笔记本 7 天试用指南

## 目标

让旧笔记本作为第一版个人 Jarvis 服务端，连续运行 7 天，用飞书真实测试记账、待办、提醒、Obsidian 入库、链接总结和 Excel 导出。

## 试用前准备

### 1. 接电源

旧笔记本必须全程接电源。提醒可靠性依赖服务持续运行。

### 2. 关闭自动休眠

macOS 可以在系统设置里关闭自动休眠：

- 系统设置
- 电池
- 选项
- 接入电源时防止自动睡眠

也可以手动检查：

```bash
pmset -g
```

如果你明确要用命令关闭接电源时系统休眠，可以运行：

```bash
sudo pmset -c sleep 0
```

这会修改系统电源设置，试用结束后可按需要恢复。

### 3. 配置 `.env`

推荐运行配置向导：

```bash
python scripts/configure_env.py
```

至少确认：

```text
FEISHU_APP_ID
FEISHU_APP_SECRET
OBSIDIAN_VAULT_PATH
```

可选：

```text
LLM_API_KEY
ALLOWED_FEISHU_USER_IDS
FEISHU_VERIFICATION_TOKEN
```

### 4. 试用前检查

```bash
python scripts/preflight_check.py
```

理想状态：

- SQLite: PASS
- Obsidian: PASS
- cloudflared: PASS
- Feishu env: PASS
- logs: PASS

LLM 如果没有配置，会显示 WARN，但机器人会使用本地规则 fallback。

## 启动服务

```bash
python scripts/start_feishu_dev.py
```

启动后脚本会打印：

```text
Feishu event subscription request URL:
https://xxx.trycloudflare.com/webhook/feishu
```

把这个地址填到飞书开放平台的事件订阅请求地址。

## 飞书真实测试消息

### 基础

```text
ping
```

### 记账

```text
今天午饭 38
这个月餐饮花了多少？
导出本月账单
```

### 待办提醒

```text
记一下：买空气炸锅
1 分钟后提醒我测试提醒
今天有哪些待办？
完成买空气炸锅
```

### Obsidian

```text
整理进知识库：个人机器人应该先支持飞书入口，并用 AI 辅助 PARA 分类。
总结这个链接 https://example.com
```

### 安全

```text
我的密码是 abc123，帮我存一下
```

预期：机器人拒绝处理，并提示不会发送给 AI。

## 每日记录

每天开始前生成日志：

```bash
python scripts/start_trial_day.py
```

日志位置：

```text
docs/trial/YYYY-MM-DD.md
```

每天至少记录：

- 实际输入
- 预期结果
- 实际结果
- 提醒是否漏发
- Obsidian 笔记是否可用
- 链接总结是否失败
- 明天优先修什么

## 每日备份

```bash
python scripts/backup_db.py
```

备份目录：

```text
data/backups/
```

## 第 7 天复盘

参考：

```text
docs/TRIAL_LOG.md
```

决定是否进入 v0.2：

- 是否连续使用 7 天
- 提醒是否漏发
- 记账是否愿意继续用
- 待办提醒是否愿意继续用
- Obsidian 入库是否愿意继续用
- 下一阶段最高优先级
