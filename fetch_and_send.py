#!/usr/bin/env python3
"""
游戏行业日报 — GitHub Actions 版
抓取多个RSS源和公开新闻API，生成日报markdown文件。
"""
import requests
import feedparser
from datetime import datetime, timedelta
import re
import time

TODAY = datetime.now().strftime("%Y-%m-%d")
OUTPUT = f"{TODAY}.md"

# ==== 数据源配置 ====

# Google News RSS（免费，无需API key）
GNEWS_BASE = "https://news.google.com/rss/search"
SOURCES = [
    ("游戏 新游 上线 公测", "新游上线"),
    ("手游 商业化 活动 通行证", "商业化"),
    ("游戏公司 投融资 人事 政策", "行业动态"),
    ("Steam 热门游戏 新作", "Steam"),
    ("电竞 赛事 网吧 游戏", "电竞/网吧"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) GameDaily/1.0"
}


def fetch_google_news(query, max_results=10):
    """从Google News RSS获取标题和链接"""
    url = f"{GNEWS_BASE}?q={requests.utils.quote(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_results]:
            title = re.sub(r'\s*-\s*\S+$', '', entry.title)  # 去掉来源后缀
            link = entry.link
            items.append({"title": title, "link": link})
        return items
    except Exception as e:
        print(f"  ⚠️ {query[:20]}... 获取失败: {e}")
        return []


def deduplicate(items):
    """简单去重"""
    seen = set()
    result = []
    for item in items:
        key = item["title"][:30]
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
        time.sleep(1.5)  # 避免被限流

    # 合并所有新闻
    all_items = []
    for cat, items in all_news.items():
        for item in items:
            item["category"] = cat
            all_items.append(item)

    all_items = deduplicate(all_items)

    # ==== 生成Markdown ====
    md = f"""# 游戏行业日报 — {TODAY}

> 🤖 由GitHub Actions自动生成，每天8:58 AM准时推送。
> 新闻来源：Google News RSS聚合，点击链接查看详情。

---

## 🔥 今日速览

"""
    # Top headlines
    for item in all_items[:8]:
        md += f"- [{item['title']}]({item['link']})\n"

    md += f"""
---

## 🆕 新游/测试动态

"""
    new_game_items = [i for i in all_items if i["category"] == "新游上线"]
    for item in new_game_items[:5]:
        md += f"- [{item['title']}]({item['link']})\n"

    md += f"""
---

## 💰 商业化与活动

"""
    biz_items = [i for i in all_items if i["category"] == "商业化"]
    for item in biz_items[:5]:
        md += f"- [{item['title']}]({item['link']})\n"

    md += f"""
---

## 📊 行业动态

"""
    industry_items = [i for i in all_items if i["category"] == "行业动态"]
    for item in industry_items[:5]:
        md += f"- [{item['title']}]({item['link']})\n"

    md += f"""
---

## 🎮 Steam/主机

"""
    steam_items = [i for i in all_items if i["category"] == "Steam"]
    for item in steam_items[:5]:
        md += f"- [{item['title']}]({item['link']})\n"

    md += f"""
---

## 💡 对你的启发

- 今日新闻较多关注**新游上线节奏**和**商业化模式创新**，留意哪些活动机制可以借鉴。
- 如果有招聘相关新闻，注意关注目标公司的动态。

---

*报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC*
*共计 {len(all_items)} 条新闻*
"""

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\n✅ 报告已生成: {OUTPUT} ({len(all_items)} 条新闻)")


if __name__ == "__main__":
    generate_report()
