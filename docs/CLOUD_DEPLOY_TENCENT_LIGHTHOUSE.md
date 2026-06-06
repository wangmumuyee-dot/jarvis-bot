# 腾讯云 Lighthouse 部署指南

## 1. 当前目标

把个人 Jarvis 机器人部署到已有腾讯云 Lighthouse 实例：

- 实例：`lhins-2cigy0y7`
- IP：`43.156.64.102`
- 系统：OpenCloudOS 9
- 已有服务：OpenClaw 面板一键部署
- 域名：暂无
- Obsidian 同步：写入 Git 仓库

第一版云部署采用：

```text
Feishu
  -> cloudflared quick tunnel HTTPS
  -> 127.0.0.1:8000 Jarvis FastAPI
  -> SQLite /opt/jarvis-data/jarvis.db
  -> Obsidian Git repo /opt/jarvis-data/obsidian-vault
```

Jarvis 作为独立 systemd 服务运行，不改 OpenClaw 的面板部署。

## 2. 重要限制

当前没有域名，所以飞书 webhook 先使用 cloudflared quick tunnel。

这能快速上线，但有一个限制：

- 服务器或 cloudflared 重启后，`*.trycloudflare.com` 地址可能变化
- 地址变化后，需要重新填飞书开放平台事件订阅地址

长期稳定方案：

- 绑定域名 + Nginx + HTTPS
- 或 Cloudflare named tunnel

## 3. 推荐目录

```text
/opt/jarvis-bot
  app/
  scripts/
  deploy/
  .venv/
  .env

/opt/jarvis-data
  jarvis.db
  exports/
  backups/
  obsidian-vault/
```

其中 `/opt/jarvis-data/obsidian-vault` 是 Obsidian vault 的 Git 仓库。

## 4. 服务器初始化

用 root 登录服务器后执行：

```bash
dnf update -y
dnf install -y git python3 python3-pip python3-devel gcc curl
useradd --system --create-home --home-dir /opt/jarvis jarvis || true
mkdir -p /opt/jarvis-bot /opt/jarvis-data
chown -R jarvis:jarvis /opt/jarvis-bot /opt/jarvis-data
```

建议给 `jarvis` 用户配置 SSH key，用它拉取代码仓库和 Obsidian vault 仓库：

```bash
mkdir -p /opt/jarvis/.ssh
chown -R jarvis:jarvis /opt/jarvis/.ssh
sudo -u jarvis ssh-keygen -t ed25519 -C "jarvis-lighthouse" -f /opt/jarvis/.ssh/id_ed25519
sudo -u jarvis cat /opt/jarvis/.ssh/id_ed25519.pub
```

把公钥添加到代码仓库和 Obsidian vault 仓库。MVP 阶段可以添加为账号 SSH key；更严格的做法是给两个仓库分别配置 deploy key。

## 5. 拉取项目代码

先把本地项目推到一个私有 Git 仓库，然后在服务器执行：

```bash
sudo -u jarvis git clone <JARVIS_BOT_GIT_URL> /opt/jarvis-bot
cd /opt/jarvis-bot
sudo -u jarvis python3 -m venv .venv
sudo -u jarvis .venv/bin/pip install -r requirements.txt
sudo -u jarvis cp .env.example .env
```

编辑 `/opt/jarvis-bot/.env`：

```text
APP_ENV=production
APP_HOST=127.0.0.1
APP_PORT=8000
LOG_LEVEL=INFO
REMINDER_SCAN_INTERVAL_SECONDS=60

DATABASE_PATH=/opt/jarvis-data/jarvis.db
EXPORT_DIR=/opt/jarvis-data/exports
OBSIDIAN_VAULT_PATH=/opt/jarvis-data/obsidian-vault
OBSIDIAN_GIT_SYNC_ENABLED=true
OBSIDIAN_GIT_PUSH_ENABLED=true

FEISHU_APP_ID=你的飞书 App ID
FEISHU_APP_SECRET=你的飞书 App Secret
FEISHU_VERIFICATION_TOKEN=你的飞书 Verification Token
FEISHU_ENCRYPT_KEY=
ALLOWED_FEISHU_USER_IDS=你的飞书 user_id 或 open_id

LLM_PROVIDER=openai-compatible
LLM_API_KEY=
LLM_MODEL=gpt-4.1-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_RESPONSES_PATH=/responses
LLM_TIMEOUT_SECONDS=20
```

不要把 `.env` 提交到 Git 仓库。

## 6. 配置 Obsidian Git 仓库

在服务器上把 Obsidian vault clone 到数据目录：

```bash
sudo -u jarvis git clone <OBSIDIAN_VAULT_GIT_URL> /opt/jarvis-data/obsidian-vault
sudo -u jarvis git -C /opt/jarvis-data/obsidian-vault config user.name "Jarvis Bot"
sudo -u jarvis git -C /opt/jarvis-data/obsidian-vault config user.email "jarvis-bot@example.local"
```

确认 `jarvis` 用户可以 push：

```bash
sudo -u jarvis git -C /opt/jarvis-data/obsidian-vault status
sudo -u jarvis git -C /opt/jarvis-data/obsidian-vault push
```

如果 push 失败，优先检查：

- SSH key 是否加到仓库
- remote 是否使用 SSH URL
- 仓库是否授予写权限

## 7. 初始化和预检

```bash
cd /opt/jarvis-bot
sudo -u jarvis .venv/bin/python scripts/init_db.py
sudo -u jarvis .venv/bin/python scripts/preflight_check.py
```

预期：

- SQLite: PASS
- Obsidian: PASS
- Obsidian Git: PASS
- Feishu env: PASS
- LLM env: PASS 或 WARN

LLM 没配置时会显示 WARN，但机器人会使用本地规则 fallback。

## 8. 安装 cloudflared

如果服务器是 x86_64：

```bash
curl -L -o /tmp/cloudflared.rpm https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-x86_64.rpm
dnf install -y /tmp/cloudflared.rpm
cloudflared --version
```

如果不是 x86_64，先执行：

```bash
uname -m
```

再下载对应架构的 cloudflared。

## 9. 安装 systemd 服务

```bash
cp /opt/jarvis-bot/deploy/jarvis-bot.service /etc/systemd/system/jarvis-bot.service
cp /opt/jarvis-bot/deploy/cloudflared-jarvis-quick.service /etc/systemd/system/cloudflared-jarvis-quick.service
systemctl daemon-reload
systemctl enable --now jarvis-bot
systemctl enable --now cloudflared-jarvis-quick
```

检查服务：

```bash
systemctl status jarvis-bot --no-pager
systemctl status cloudflared-jarvis-quick --no-pager
curl http://127.0.0.1:8000/health
```

查看 cloudflared 生成的公网地址：

```bash
journalctl -u cloudflared-jarvis-quick -n 100 --no-pager
```

日志里会出现类似：

```text
https://xxx.trycloudflare.com
```

飞书开放平台事件订阅地址填写：

```text
https://xxx.trycloudflare.com/webhook/feishu
```

## 10. Obsidian Git 同步验证

通过飞书发送：

```text
整理进知识库：个人机器人应该先支持飞书入口，并用 AI 辅助 PARA 分类。
```

预期机器人回复包含：

```text
已写入 Obsidian 笔记
Git 同步：Obsidian 笔记已提交并 push 到 Git 仓库
```

然后在 Mac 上进入 Obsidian vault：

```bash
git pull
```

应能看到服务器生成的新 Markdown。

## 11. 常用运维命令

重启服务：

```bash
systemctl restart jarvis-bot
systemctl restart cloudflared-jarvis-quick
```

看日志：

```bash
journalctl -u jarvis-bot -f
journalctl -u cloudflared-jarvis-quick -f
```

备份 SQLite：

```bash
cd /opt/jarvis-bot
sudo -u jarvis .venv/bin/python scripts/backup_db.py
```

手动同步 Obsidian Git：

```bash
cd /opt/jarvis-bot
sudo -u jarvis .venv/bin/python scripts/sync_obsidian_git.py
```

更新代码：

```bash
cd /opt/jarvis-bot
sudo -u jarvis git pull
sudo -u jarvis .venv/bin/pip install -r requirements.txt
systemctl restart jarvis-bot
```

## 12. 安全建议

- 不要把 root 密码、飞书密钥、LLM key 写进仓库
- `.env` 只放服务器本地
- 代码仓库和 Obsidian vault 仓库建议使用私有仓库
- 部署成功后，建议改成 SSH key 登录，并逐步关闭 root 密码登录
- 服务器防火墙无需开放 8000，Jarvis 只监听 `127.0.0.1`
- 没有域名前，飞书 webhook 依赖 cloudflared quick tunnel；服务重启后要检查 URL 是否变化
