#!/usr/bin/env python3
"""
游戏行业日报 — GitHub Actions 版
抓取多个RSS源和公开新闻API，生成日报markdown文件。
v2: 关键词过滤 + 优化排版 + Server酱推送
"""
import requests
import feedparser
from datetime import datetime, timedelta
import re
import time
import os
import json

TODAY = datetime.now().strftime("%Y-%m-%d")
OUTPUT = f"{TODAY}.md"

# ==== 数据源配置 ====
# 使用更精准的搜索词提高相关性
GNEWS_BASE = "https://news.google.com/rss/search"
SOURCES = [
    ("新游 公测 上线 开服 测试", "new_game"),
    ("手游 商业化 BattlePass 通行证 皮肤 抽卡", "monetization"),
    ("游戏公司 网易 腾讯 米哈游 投融资 收购", "industry"),
    ("Steam 热门游戏 新作 主机 PS5 Switch", "steam"),
    ("电竞 赛事 俱乐部 网吧", "esports"),
    ("游戏出海 海外收入 全球化", "overseas"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) GameDaily/2.0"
}

# ==== 关键词过滤 ====
# 标题必须命中至少1个核心关键词才算游戏相关
CORE_KEYWORDS = [
    "游戏", "手游", "端游", "主机", "电竞", "Steam", "steam",
    "腾讯", "网易", "米哈游", "莉莉丝", "鹰角", "叠纸", "库洛",
    "通行证", "BattlePass", "battle pass", "皮肤", "抽卡", "Gacha",
    "新游", "公测", "上线", "开服", "测试", "版本", "更新",
    "PS5", "Xbox", "Switch", "Nintendo", "PC游戏",
    "网吧", "收入", "流水", "出海", "发行", "开发商", "工作室",
    "融资", "收购", "上市", "IPO", "VR游戏", "AR游戏",
    "MMO", "RPG", "FPS", "MOBA", "肉鸽", "开放世界",
    "燕云", "异环", "鸣潮", "原神", "王者荣耀", "永劫无间",
    "卡厄思梦境", "绝区零", "明日方舟", "崩坏",
    "Palworld", "幻兽帕鲁", "DLSS", "虚幻引擎", "Unity",
    "GDC", "游戏节", "展会", "发布会",
]

# 标题命中以下任一关键词则排除（非游戏内容噪音）
BLOCK_KEYWORDS = [
    "体育游戏" if False else "",  # placeholder
]

# 标题命中以下关键词加权（高价值新闻）
BOOST_KEYWORDS = {
    "公测": 3, "上线": 2, "收入": 2, "流水": 2, "收购": 3,
    "融资": 2, "出海": 2, "BattlePass": 3, "通行证": 3,
    "Steam": 2, "腾讯": 2, "网易": 2, "米哈游": 2,
}


def is_gaming_relevant(title):
    """检查标题是否与游戏行业相关"""
    score = 0
    for kw in CORE_KEYWORDS:
        if kw.lower() in title.lower():
            score += 1
    # 加权
    for kw, boost in BOOST_KEYWORDS.items():
        if kw.lower() in title.lower():
            score += boost
    return score >= 1, score


def fetch_google_news(query, max_results=12):
    """从Google News RSS获取标题和链接"""
    url = f"{GNEWS_BASE}?q={requests.utils.quote(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_results]:
            title = re.sub(r'\s*-\s*\S+$', '', entry.title).strip()
            link = entry.link
            # 关键词过滤
            relevant, score = is_gaming_relevant(title)
            if relevant:
                items.append({"title": title, "link": link, "score": score})
        return items
    except Exception as e:
        print(f"  ⚠️ {query[:20]}... 获取失败: {e}")
        return []


def deduplicate(items):
    """去重 + 按相关性排序"""
    seen = set()
    result = []
    for item in sorted(items, key=lambda x: x.get("score", 0), reverse=True):
        key = item["title"][:35]
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def generate_report():
    print(f"=== 生成 {TODAY} 游戏行业日报 ===\n")

    all_news = {}
    for query, category in SOURCES:
        print(f"  搜索: {query}")
        results = fetch_google_news(query)
        all_news[category] = results
        time.sleep(1.2)

    # 合并 + 去重 + 排序
    all_items = []
    for cat, items in all_news.items():
        for item in items:
            item["category"] = cat
            all_items.append(item)

    all_items = deduplicate(all_items)

    # ==== 分类整理 ====
    new_game = [i for i in all_items if i["category"] == "new_game"]
    monetization = [i for i in all_items if i["category"] == "monetization"]
    industry = [i for i in all_items if i["category"] == "industry"]
    steam = [i for i in all_items if i["category"] == "steam"]
    esports = [i for i in all_items if i["category"] == "esports"]
    overseas = [i for i in all_items if i["category"] == "overseas"]

    # ==== 生成Markdown ====
    md = f"""# 游戏行业日报 — {TODAY}

> 🤖 自动生成 · 来源：Google News · [查看往期](./index.md)

---

## 今日速览

"""

    # Top 10 高价值新闻
    top_items = all_items[:10]
    for idx, item in enumerate(top_items, 1):
        md += f"{idx}. [{item['title']}]({item['link']})\n"

    # 新游/测试
    if new_game:
        md += f"""
---

## 新游 & 测试动态

"""
        for idx, item in enumerate(new_game[:6], 1):
            md += f"{idx}. [{item['title']}]({item['link']})\n"

    # 商业化
    if monetization:
        md += f"""
---

## 商业化 & 活动

"""
        for idx, item in enumerate(monetization[:6], 1):
            md += f"{idx}. [{item['title']}]({item['link']})\n"

    # 行业动态
    if industry:
        md += f"""
---

## 行业动态

"""
        for idx, item in enumerate(industry[:6], 1):
            md += f"{idx}. [{item['title']}]({item['link']})\n"

    # Steam/主机
    if steam:
        md += f"""
---

## Steam & 主机

"""
        for idx, item in enumerate(steam[:6], 1):
            md += f"{idx}. [{item['title']}]({item['link']})\n"

    # 出海
    if overseas:
        md += f"""
---

## 出海 & 全球化

"""
        for idx, item in enumerate(overseas[:5], 1):
            md += f"{idx}. [{item['title']}]({item['link']})\n"

    # 电竞
    if esports:
        md += f"""
---

## 电竞 & 赛事

"""
        for idx, item in enumerate(esports[:5], 1):
            md += f"{idx}. [{item['title']}]({item['link']})\n"

    md += f"""
---

## 启发

- 留意今日**新游上线/测试动态**中的玩法和付费设计，想想能否借鉴到自己的项目中
- 关注**商业化板块**的活动机制、定价策略、BattlePass设计
- 行业投融资动态反映资本方向，可判断哪些赛道在升温

---

*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC · 共 {len(all_items)} 条*
"""

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\n✅ 报告已生成: {OUTPUT} ({len(all_items)} 条新闻)")
    return len(all_items)


def send_to_serverchan(sendkey, title, content):
    """推送到Server酱（微信通知）"""
    if not sendkey:
        print("  跳过Server酱推送（未配置SENDKEY）")
        return
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    # 截取摘要作为微信消息
    summary = content[:800] + "..." if len(content) > 800 else content
    try:
        resp = requests.post(url, data={
            "title": title,
            "desp": summary
        }, timeout=10)
        print(f"  Server酱推送: {resp.json()}")
    except Exception as e:
        print(f"  Server酱推送失败: {e}")


if __name__ == "__main__":
    count = generate_report()

    # 读取生成的报告用于推送
    with open(OUTPUT, "r", encoding="utf-8") as f:
        report_content = f.read()

    # Server酱微信推送（可选，通过GitHub Secret配置）
    sendkey = os.environ.get("SERVERCHAN_SENDKEY", "")
    if sendkey:
        send_to_serverchan(sendkey, f"游戏行业日报 {TODAY}", report_content)
