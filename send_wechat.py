#!/usr/bin/env python3
"""推送游戏日报到微信（Server酱）"""
import requests
import sys
import os

SENDKEY = os.environ.get("SERVERCHAN_SENDKEY", "")
API = "https://sctapi.ftqq.com"

def send(subject, body_file):
    if not SENDKEY:
        print("❌ 未配置 SERVERCHAN_SENDKEY 环境变量")
        sys.exit(1)

    with open(body_file, "r", encoding="utf-8") as f:
        body = f.read()

    # 取第一行作为标题
    title_line = body.strip().split("\n")[0].lstrip("# ")

    url = f"{API}/{SENDKEY}.send"
    resp = requests.post(url, data={
        "title": subject,
        "desp": body,
    }, timeout=15)
    result = resp.json()
    if result.get("code") == 0:
        print(f"✅ 微信已推送: {subject}")
    else:
        print(f"❌ 推送失败: {result}")
    return result

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: send_wechat.py <subject> <body_file>")
        sys.exit(1)
    send(sys.argv[1], sys.argv[2])
