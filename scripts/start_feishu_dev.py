from __future__ import annotations

import re
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
UVICORN = PROJECT_ROOT / ".venv" / "bin" / "uvicorn"


def main() -> None:
    if not UVICORN.exists():
        raise SystemExit("未找到 .venv/bin/uvicorn，请先安装依赖：pip install -r requirements-dev.txt")

    print("Initializing database...")
    subprocess.check_call([str(PYTHON), "scripts/init_db.py"], cwd=PROJECT_ROOT)

    uvicorn = subprocess.Popen(
        [str(UVICORN), "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    print("Starting FastAPI on http://127.0.0.1:8000 ...")
    time.sleep(2)

    cloudflared = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://127.0.0.1:8000"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    print("Starting cloudflared tunnel...")
    print("Press Ctrl+C to stop both FastAPI and cloudflared.\n")

    processes = [uvicorn, cloudflared]
    try:
        tunnel_url = _read_until_tunnel_url(cloudflared)
        if tunnel_url:
            print("\nFeishu event subscription request URL:")
            print(f"{tunnel_url}/webhook/feishu\n")
        else:
            print("未能自动识别 cloudflared URL，请查看 cloudflared 输出。")

        _stream_processes(processes)
    except KeyboardInterrupt:
        print("\nStopping services...")
    finally:
        for process in processes:
            _terminate(process)


def _read_until_tunnel_url(process: subprocess.Popen[str], timeout_seconds: int = 30) -> str | None:
    deadline = time.time() + timeout_seconds
    url_re = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    while time.time() < deadline and process.poll() is None:
        line = process.stdout.readline() if process.stdout else ""
        if line:
            print(f"[cloudflared] {line}", end="")
            match = url_re.search(line)
            if match:
                return match.group(0)
        else:
            time.sleep(0.1)
    return None


def _stream_processes(processes: list[subprocess.Popen[str]]) -> None:
    while all(process.poll() is None for process in processes):
        for name, process in [("uvicorn", processes[0]), ("cloudflared", processes[1])]:
            if not process.stdout:
                continue
            line = process.stdout.readline()
            if line:
                print(f"[{name}] {line}", end="")
        time.sleep(0.1)


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()


if __name__ == "__main__":
    main()

