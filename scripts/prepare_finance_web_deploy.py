from __future__ import annotations

import argparse
import secrets
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "deploy" / "generated"


@dataclass(frozen=True)
class GeneratedDeployFiles:
    output_dir: Path
    domain: str
    proxy: str
    web_auth_token: str
    files: tuple[Path, ...]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate finance web domain deployment files.")
    parser.add_argument("domain", help="Finance web domain, for example finance.example.com")
    parser.add_argument("--proxy", choices=["caddy", "nginx", "both"], default="caddy")
    parser.add_argument("--upstream", default="127.0.0.1:8000", help="Jarvis FastAPI upstream host:port")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--web-auth-token", default="", help="Use an existing WEB_AUTH_TOKEN instead of generating one")
    args = parser.parse_args()

    result = generate_deploy_files(
        domain=args.domain,
        proxy=args.proxy,
        upstream=args.upstream,
        output_dir=args.output_dir,
        web_auth_token=args.web_auth_token or None,
    )

    print(f"已生成财务网页部署文件：{result.output_dir}")
    for path in result.files:
        print(f"- {path}")
    print("")
    print("把下面这行加入服务器 /opt/jarvis-bot/.env：")
    print(f"WEB_AUTH_TOKEN={result.web_auth_token}")


def generate_deploy_files(
    *,
    domain: str,
    proxy: str,
    upstream: str,
    output_dir: Path,
    web_auth_token: str | None = None,
) -> GeneratedDeployFiles:
    normalized_domain = _normalize_domain(domain)
    normalized_proxy = proxy.lower()
    if normalized_proxy not in {"caddy", "nginx", "both"}:
        raise ValueError("proxy must be caddy, nginx, or both")

    token = web_auth_token or secrets.token_urlsafe(32)
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []

    env_path = output_dir / "finance-web.env.snippet"
    env_path.write_text(render_env_snippet(token), encoding="utf-8")
    files.append(env_path)

    if normalized_proxy in {"caddy", "both"}:
        caddy_path = output_dir / "Caddyfile.finance"
        caddy_path.write_text(render_caddyfile(normalized_domain, upstream), encoding="utf-8")
        files.append(caddy_path)

    if normalized_proxy in {"nginx", "both"}:
        nginx_path = output_dir / "nginx-jarvis-finance.conf"
        nginx_path.write_text(render_nginx_conf(normalized_domain, upstream), encoding="utf-8")
        files.append(nginx_path)

    commands_path = output_dir / "deploy-commands.txt"
    commands_path.write_text(render_commands(normalized_domain, normalized_proxy), encoding="utf-8")
    files.append(commands_path)

    return GeneratedDeployFiles(
        output_dir=output_dir,
        domain=normalized_domain,
        proxy=normalized_proxy,
        web_auth_token=token,
        files=tuple(files),
    )


def render_env_snippet(web_auth_token: str) -> str:
    return (
        "# Add this to /opt/jarvis-bot/.env on the server.\n"
        "APP_ENV=production\n"
        f"WEB_AUTH_TOKEN={web_auth_token}\n"
    )


def render_caddyfile(domain: str, upstream: str) -> str:
    return (
        f"{domain} {{\n"
        "    encode gzip\n"
        "    redir / /finance 302\n"
        f"    reverse_proxy {upstream}\n"
        "}\n"
    )


def render_nginx_conf(domain: str, upstream: str) -> str:
    return (
        "server {\n"
        "    listen 80;\n"
        f"    server_name {domain};\n"
        "\n"
        "    location / {\n"
        f"        proxy_pass http://{upstream};\n"
        "        proxy_http_version 1.1;\n"
        "        proxy_set_header Host $host;\n"
        "        proxy_set_header X-Real-IP $remote_addr;\n"
        "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
        "        proxy_set_header X-Forwarded-Proto $scheme;\n"
        "    }\n"
        "}\n"
    )


def render_commands(domain: str, proxy: str) -> str:
    lines = [
        "# Run on the server after copying generated files.",
        "cd /opt/jarvis-bot",
        "# Merge deploy/generated/finance-web.env.snippet into .env before restarting.",
        "systemctl restart jarvis-bot",
    ]
    if proxy in {"caddy", "both"}:
        lines.extend(
            [
                "cp deploy/generated/Caddyfile.finance /etc/caddy/Caddyfile",
                "systemctl reload caddy",
                f"curl -I https://{domain}/finance",
            ]
        )
    if proxy in {"nginx", "both"}:
        lines.extend(
            [
                "cp deploy/generated/nginx-jarvis-finance.conf /etc/nginx/conf.d/jarvis-finance.conf",
                "nginx -t",
                "systemctl reload nginx",
                f"certbot --nginx -d {domain}",
                f"curl -I https://{domain}/finance",
            ]
        )
    return "\n".join(lines) + "\n"


def _normalize_domain(domain: str) -> str:
    normalized = domain.strip().removeprefix("https://").removeprefix("http://").strip("/")
    if not normalized or "/" in normalized or " " in normalized:
        raise ValueError("domain must be a hostname such as finance.example.com")
    return normalized


if __name__ == "__main__":
    main()
