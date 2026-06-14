from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.prepare_finance_web_deploy import (
    generate_deploy_files,
    render_caddyfile,
    render_env_snippet,
    render_nginx_conf,
)


class FinanceDeployScriptTest(unittest.TestCase):
    def test_render_proxy_configs(self) -> None:
        caddy = render_caddyfile("finance.example.com", "127.0.0.1:8000")
        self.assertIn("finance.example.com", caddy)
        self.assertIn("redir / /finance 302", caddy)
        self.assertIn("reverse_proxy 127.0.0.1:8000", caddy)

        nginx = render_nginx_conf("finance.example.com", "127.0.0.1:8000")
        self.assertIn("server_name finance.example.com;", nginx)
        self.assertIn("proxy_pass http://127.0.0.1:8000;", nginx)

    def test_render_env_snippet(self) -> None:
        snippet = render_env_snippet("secret")
        self.assertIn("APP_ENV=production", snippet)
        self.assertIn("WEB_AUTH_TOKEN=secret", snippet)

    def test_generate_deploy_files_for_both_proxies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_deploy_files(
                domain="https://finance.example.com/",
                proxy="both",
                upstream="127.0.0.1:8000",
                output_dir=Path(tmp),
                web_auth_token="fixed-token",
            )

            names = {path.name for path in result.files}
            self.assertEqual(result.domain, "finance.example.com")
            self.assertEqual(result.web_auth_token, "fixed-token")
            self.assertIn("finance-web.env.snippet", names)
            self.assertIn("Caddyfile.finance", names)
            self.assertIn("nginx-jarvis-finance.conf", names)
            self.assertIn("deploy-commands.txt", names)

    def test_reject_invalid_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                generate_deploy_files(
                    domain="finance.example.com/path",
                    proxy="caddy",
                    upstream="127.0.0.1:8000",
                    output_dir=Path(tmp),
                )


if __name__ == "__main__":
    unittest.main()

