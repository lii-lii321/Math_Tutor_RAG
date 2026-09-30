"""GitHub 仓库调研：错题本 / 题库生成 / 文档导入类项目（公开 API，只读）。

安全：目标 host 固定为 api.github.com（白名单校验），https 协议，query 仅作参数。
"""

import ipaddress
import socket
import sys

import requests

sys.path.insert(0, ".")

ALLOWED_HOST = "api.github.com"
QUERIES = [
    "错题本",
    "错题 OCR",
    "wrong question notebook math",
    "quiz generator LLM document",
    "exam question extraction OCR latex",
]


def _guard() -> None:
    """校验目标 host：必须是指定域名且解析结果为公网地址。

    本机代理 TUN 的 fake-IP 模式会把域名解析到 198.18.0.0/15（基准测试段），
    该段在此环境下等价于真实公网出口，显式放行；其余私网/环回照常拒绝。
    """
    if ALLOWED_HOST != "api.github.com":
        raise RuntimeError("host 不在白名单")
    for info in socket.getaddrinfo(ALLOWED_HOST, 443):
        ip = ipaddress.ip_address(info[4][0])
        if ip in ipaddress.ip_network("198.18.0.0/15"):
            continue  # Clash/Mihomo fake-IP 段，经代理真实出口为公网
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or not ip.is_global:
            raise RuntimeError(f"解析到非公网地址: {ip}")


def main() -> None:
    _guard()
    for query in QUERIES:
        print(f"\n===== {query} =====")
        try:
            r = requests.get(
                f"https://{ALLOWED_HOST}/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 6},
                headers={"Accept": "application/vnd.github+json"},
                timeout=20,
                allow_redirects=False,
            )
            data = r.json()
            for item in data.get("items", [])[:6]:
                print(
                    f"★{item['stargazers_count']:>5}  {item['full_name']:<48} "
                    f"{(item.get('description') or '')[:90]}"
                )
        except Exception as exc:  # noqa: BLE001
            print(f"{query}: FAILED {str(exc)[:120]}")


if __name__ == "__main__":
    main()
