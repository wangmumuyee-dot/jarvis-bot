# 财务网页域名部署指南

本文档说明如何把当前财务网页部署到自己的域名下。目标是：

```text
https://finance.example.com/
https://finance.example.com/finance
  -> Caddy 或 Nginx HTTPS
  -> 127.0.0.1:8000 Jarvis FastAPI
  -> SQLite / Obsidian / Excel
```

如果你的域名已经托管在 Cloudflare，也可以用 Cloudflare Tunnel 替代 Caddy/Nginx 直连。

## 1. 已有网页入口

当前项目已提供这些 Web 路由：

```text
GET  /
GET  /finance
GET  /finance-sw.js
GET  /finance-static/*
GET  /api/finance/dashboard
GET  /api/finance/options
GET  /api/finance/entries
POST /api/finance/entries
POST /api/finance/command
GET  /api/finance/export
POST /api/finance/import
```

网页能力：

- 快速结构化记账
- 最近流水查看
- 本月收入、支出、净额、待报销概览
- 分类支出、预算、愿望储蓄、欠款概览
- 命令面板复用飞书文本指令
- Excel 上传导入和浏览器下载导出
- 导出、导入、预算、欠款、周期账单、愿望、模板、月报、消费分析等现有财务功能
- PWA 安装支持：manifest、iPhone 主屏幕图标、独立窗口模式、页面壳子缓存

## 2. 必须先配置访问口令

财务数据不建议裸露在公网。服务器 `.env` 里建议配置：

```text
WEB_AUTH_TOKEN=一串足够长的随机口令
```

生成示例：

```bash
openssl rand -base64 32
```

说明：

- `WEB_AUTH_TOKEN` 留空时，财务 API 不校验口令，适合本地开发。
- 配置后，网页第一次加载财务数据会显示访问口令面板。
- 口令会保存在浏览器本地存储中，并通过 `X-Jarvis-Web-Token` 请求头发送。
- 如果你要换口令，改 `.env` 后重启 `jarvis-bot` 服务。

## 3. FastAPI 服务保持内网监听

systemd 服务建议继续只监听本机：

```text
127.0.0.1:8000
```

不要直接开放 8000 端口到公网。让 Caddy、Nginx 或 Cloudflare Tunnel 负责 HTTPS 和域名入口。

检查本机服务：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/finance
```

## 3.1 生成部署文件

可以用脚本按你的域名生成反代配置、`.env` 片段和服务器命令：

```bash
python scripts/prepare_finance_web_deploy.py finance.example.com --proxy caddy
```

同时生成 Caddy 和 Nginx：

```bash
python scripts/prepare_finance_web_deploy.py finance.example.com --proxy both
```

输出目录：

```text
deploy/generated/
```

生成内容：

- `finance-web.env.snippet`：包含 `APP_ENV=production` 和随机 `WEB_AUTH_TOKEN`
- `Caddyfile.finance`
- `nginx-jarvis-finance.conf`
- `deploy-commands.txt`

## 4. 方案 A：Caddy 推荐

Caddy 会自动申请和续期 HTTPS 证书，适合个人项目。

### 4.1 安装 Caddy

OpenCloudOS/RHEL 系：

```bash
dnf install -y 'dnf-command(copr)'
dnf copr enable @caddy/caddy -y
dnf install -y caddy
```

### 4.2 DNS 解析

在域名 DNS 控制台添加：

```text
类型：A
主机记录：finance
记录值：你的服务器公网 IP
```

例如：

```text
finance.example.com -> 43.156.64.102
```

### 4.3 Caddyfile

编辑：

```bash
vim /etc/caddy/Caddyfile
```

写入：

```text
finance.example.com {
    encode gzip

    reverse_proxy 127.0.0.1:8000
}
```

仓库里也提供了模板：

```text
deploy/Caddyfile.finance.example
```

如果你想让根路径也直接打开财务网页：

```text
finance.example.com {
    encode gzip

    redir / /finance 302
    reverse_proxy 127.0.0.1:8000
}
```

### 4.4 启动 Caddy

```bash
systemctl enable --now caddy
systemctl reload caddy
systemctl status caddy --no-pager
```

验证：

```bash
curl -I https://finance.example.com/finance
```

浏览器打开：

```text
https://finance.example.com/finance
```

### 4.5 安装到 iPhone 主屏幕

HTTPS 生效后，在 iPhone Safari 打开：

```text
https://finance.example.com/finance
```

点击分享按钮，选择“添加到主屏幕”。添加后会出现 `Jarvis 财务` 图标，打开时使用独立窗口模式。

## 5. 方案 B：Nginx

如果服务器已经使用 Nginx，可以新增一个 server。

### 5.1 安装

```bash
dnf install -y nginx certbot python3-certbot-nginx
systemctl enable --now nginx
```

### 5.2 Nginx 配置

创建：

```bash
vim /etc/nginx/conf.d/jarvis-finance.conf
```

写入：

```nginx
server {
    listen 80;
    server_name finance.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

仓库里也提供了模板：

```text
deploy/nginx-jarvis-finance.conf.example
```

申请 HTTPS：

```bash
nginx -t
systemctl reload nginx
certbot --nginx -d finance.example.com
```

### 5.3 安装到 iPhone 主屏幕

HTTPS 生效后，在 iPhone Safari 打开：

```text
https://finance.example.com/finance
```

点击分享按钮，选择“添加到主屏幕”。添加后会出现 `Jarvis 财务` 图标，打开时使用独立窗口模式。

## 6. 方案 C：Cloudflare Tunnel

如果域名已经接入 Cloudflare，Tunnel 可以不开放服务器入站 80/443。

### 6.1 登录 Cloudflare

```bash
cloudflared tunnel login
```

### 6.2 创建 named tunnel

```bash
cloudflared tunnel create jarvis-finance
cloudflared tunnel route dns jarvis-finance finance.example.com
```

### 6.3 配置 tunnel

创建：

```bash
mkdir -p /etc/cloudflared
vim /etc/cloudflared/config.yml
```

示例：

```yaml
tunnel: jarvis-finance
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: finance.example.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

安装服务：

```bash
cloudflared service install
systemctl enable --now cloudflared
systemctl status cloudflared --no-pager
```

## 7. 飞书 webhook 与财务网页共用服务

同一个 FastAPI 服务可以同时处理：

```text
https://finance.example.com/finance
https://finance.example.com/webhook/feishu
```

如果你希望飞书 webhook 使用另一个子域名，也可以在反代层绑定：

```text
jarvis.example.com -> 127.0.0.1:8000
finance.example.com -> 127.0.0.1:8000
```

飞书事件订阅地址填写：

```text
https://finance.example.com/webhook/feishu
```

## 8. 部署后检查清单

```bash
systemctl status jarvis-bot --no-pager
curl http://127.0.0.1:8000/health
curl -I https://finance.example.com/finance
```

浏览器检查：

- 打开 `/finance`
- 输入 `WEB_AUTH_TOKEN`
- 查看本月概览是否出现
- 新增一条小额测试流水
- 确认最近流水出现
- 删除测试流水或用 SQLite 手动清理
- 执行命令：`本月分类统计`

## 9. 安全建议

- 域名必须使用 HTTPS。
- 必须设置 `WEB_AUTH_TOKEN`。
- 不要开放 `127.0.0.1:8000` 到公网。
- 服务器安全组只开放 80/443 和 SSH。
- `.env` 不要提交到仓库。
- 如果使用 Cloudflare，可以额外开启 Cloudflare Access。
- 如果后续多人使用，再增加真正的用户登录和权限隔离。
