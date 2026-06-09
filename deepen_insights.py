#!/usr/bin/env python3
"""用 Anthropic API 为 insight 页面补充深度分析"""
import os, re, json, requests, sys
from datetime import datetime

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """你是游戏行业资深分析师。你的读者是一名刚被裁员的游戏活动/商业化策划（前网易永劫无间网吧渠道活动），正在找工作和提升自己。

你需要为一个insight页面补充"为什么这很重要"部分。要求：
1. 从中国游戏行业从业者视角出发，具体、有数据感、可操作
2. 用表格对比、案例拆解等方式呈现，不是空泛的趋势描述
3. 落到"对求职/技能提升/职业发展意味着什么"
4. 300-500字，用中文，Markdown格式
5. 不要重复已有的"最新信号"和"建议行动"内容"""

def call_claude(system, prompt):
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 1500,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=90,
    )
    data = resp.json()
    if "error" in data:
        print(f"  API error: {data['error'].get('message', str(data))}")
        return None
    return data["content"][0]["text"]


def deepen_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "Claude Code 每日定时任务会在此补充" not in content:
        return False

    today = datetime.now().strftime("%Y-%m-%d")

    # 提取已有信息
    topic = re.search(r"^# (.+)", content)
    topic_name = topic.group(1) if topic else "游戏行业趋势"

    signal_match = re.search(r"\*\*" + today + r"\*\*：(.+?)(?:\n|$)", content)
    signal_text = signal_match.group(1).strip() if signal_match else ""

    takeaway_match = re.search(r"\n\n(.+?)\n\n### 建议行动", content, re.DOTALL)
    takeaway_text = takeaway_match.group(1).strip() if takeaway_match else ""

    sources = re.findall(r"^- \[([^\]]+)\]\(([^)]+)\)", content)
    source_text = "\n".join([f"- {s[0]}" for s in sources[:5]])

    prompt = f"""主题：{topic_name}

今日信号：{signal_text}

已有洞察：{takeaway_text[:300]}

来源文章：
{source_text}

请为这个页面的"为什么这很重要"部分写深度分析。要求用表格对比、案例拆解等方式呈现，落到对游戏行业从业者的职业启示。"""

    print(f"  正在深化: {topic_name}...")
    analysis = call_claude(SYSTEM_PROMPT, prompt)
    if not analysis:
        return False

    # 替换占位符
    replacement = f"""## 为什么这很重要

{analysis}"""
    new_content = content.replace(
        "## 为什么这很重要\n\n> 💡 Claude Code 每日定时任务会在此补充深度分析、案例拆解和行业背景。",
        replacement,
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"  ✅ {topic_name} 已深化")
    return True


if __name__ == "__main__":
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("⚠️ 未设置 ANTHROPIC_API_KEY，跳过深度分析")
        sys.exit(0)

    deepened = 0
    for f in sorted(os.listdir("insights")):
        path = f"insights/{f}"
        if deepen_file(path):
            deepened += 1

    print(f"\n共深化 {deepened} 个 insight 页面")
