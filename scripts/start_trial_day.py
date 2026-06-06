from __future__ import annotations

from datetime import datetime
from pathlib import Path


TEMPLATE = """# 试用日志 - {date}

## 环境

- 服务启动时间：
- cloudflared 地址：
- 是否接电源：
- 是否关闭自动休眠：
- preflight 结果：

## 今日真实输入

| 时间 | 输入 | 预期 | 实际 | 是否成功 |
| --- | --- | --- | --- | --- |
| | | | | |

## 功能检查

- [ ] ping/pong
- [ ] 记账新增
- [ ] 账本查询
- [ ] 待办创建
- [ ] 一次性提醒
- [ ] 简单重复提醒
- [ ] 待办完成
- [ ] 文本总结入库
- [ ] 链接总结入库
- [ ] Excel 导出
- [ ] 敏感信息拒绝

## 提醒可靠性

- 今天设置的提醒数：
- 成功收到：
- 漏发：
- 延迟明显：
- 失败记录：

## Obsidian 输出

- 今日新增笔记数：
- 分类是否正确：
- Markdown 是否可读：
- 需要调整的模板：

## 失败样例

```text

```

## 明日修复优先级

1.
2.
3.
"""


def main() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path("docs/trial")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{today}.md"
    if not path.exists():
        path.write_text(TEMPLATE.format(date=today), encoding="utf-8")
        print(f"Created {path}")
    else:
        print(f"Already exists: {path}")


if __name__ == "__main__":
    main()

