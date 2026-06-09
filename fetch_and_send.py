#!/usr/bin/env python3
"""
游戏行业日报 — GitHub Actions 版
v4: Bing News RSS + 国内直链 + 游戏陀螺/机核
"""
import requests
import feedparser
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote
import re
import time
import os
from collections import Counter

TODAY = datetime.now().strftime("%Y-%m-%d")
OUTPUT = f"{TODAY}.md"
CUTOFF_HOURS = 168  # 7天窗口（Bing索引更新较慢）
MONETIZATION_CUTOFF_HOURS = 720  # 商业化深度扫描放宽到30天

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

# ==== 新闻源 ====
# Bing News RSS（国内可访问，链接为真实URL）
BING_BASE = "https://www.bing.com/news/search"
BING_SOURCES = [
    ("新游 公测 上线 开服 测试", "new_game"),
    ("手游 限定皮肤 返场 累充 活动", "monetization"),
    ("游戏公司 投融资 收购 腾讯 网易 米哈游", "industry"),
    ("Steam 热门游戏 PS5 Switch 主机 新作", "steam"),
    ("电竞 赛事 俱乐部 战队", "esports"),
    ("游戏出海 海外收入 全球化 本地化", "overseas"),
]

# 商业化扩展（7天）
MONETIZATION_QUERIES = [
    "游戏 付费 变现 商业模式",
    "手游 活动 限定 返场",
    "游戏 商业化",
    "游戏 玩家行为 社区运营 用户",
]

# 垂直媒体 RSS（直链）
DIRECT_FEEDS = [
    ("https://www.youxituoluo.com/feed", "industry"),
    ("https://www.gcores.com/rss", "steam"),
]

# ==== 关键词 ====
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

BOOST_KEYWORDS = {
    "公测": 3, "上线": 2, "收入": 2, "流水": 2, "收购": 3,
    "融资": 2, "出海": 2, "BattlePass": 3, "通行证": 3,
    "Steam": 2, "腾讯": 2, "网易": 2, "米哈游": 2,
}

TREND_CATEGORIES = {
    "BattlePass/通行证": ["通行证", "BattlePass", "battle pass", "战令"],
    "抽卡/Gacha": ["抽卡", "Gacha", "卡池", "保底", "概率"],
    "皮肤/外观付费": ["皮肤", "时装", "外观", "坐骑", "特效"],
    "付费模式创新": ["买断制", "免费", "订阅", "月卡", "通行证"],
    "出海/全球化": ["出海", "海外", "全球化", "全球", "国际"],
    "新游密集上线": ["公测", "上线", "开服", "定档"],
    "AI+游戏": ["AI", "人工智能", "AIGC", "大模型"],
    "跨平台": ["主机", "PS5", "Xbox", "Switch", "PC", "手机"],
    "电竞/赛事": ["电竞", "赛事", "战队", "冠军", "联赛"],
    "停运/关服": ["停运", "关服", "停服", "下架"],
    "收购/投融资": ["收购", "融资", "投资", "IPO", "上市"],
    "玩家行为/社区": ["玩家", "社区", "社群", "用户", "反馈"],
}


def extract_real_url(bing_url):
    """从Bing News的apiclick.aspx链接中提取真实文章URL"""
    parsed = urlparse(bing_url)
    params = parse_qs(parsed.query)
    real = unquote(params.get("url", [""])[0])
    if real and "bing.com" not in real:
        return real
    return bing_url


def is_gaming_relevant(title):
    score = 0
    for kw in CORE_KEYWORDS:
        if kw.lower() in title.lower():
            score += 1
    for kw, boost in BOOST_KEYWORDS.items():
        if kw.lower() in title.lower():
            score += boost
    return score >= 1, score


def fetch_bing_news(query, max_results=12, cutoff_hours=None):
    """从Bing News RSS获取新闻，提取真实直链"""
    if cutoff_hours is None:
        cutoff_hours = CUTOFF_HOURS
    url = f"{BING_BASE}?q={requests.utils.quote(query)}&format=rss"
    now = datetime.now()
    cutoff = now - timedelta(hours=cutoff_hours)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(resp.content)
        items = []
        for entry in feed.entries[:max_results]:
            published = entry.get("published_parsed")
            if published:
                pub_dt = datetime(*published[:6])
                if pub_dt < cutoff:
                    continue

            title = re.sub(r'\s*[-—|]\s*\S+$', '', entry.title).strip()
            raw_link = entry.link
            link = extract_real_url(raw_link)

            relevant, score = is_gaming_relevant(title)
            if relevant:
                items.append({
                    "title": title, "link": link, "score": score,
                    "published": published or None
                })
        return items
    except Exception as e:
        print(f"  ⚠️ {query[:20]}... 获取失败: {e}")
        return []


def fetch_direct_feed(feed_url, category, max_results=15):
    """从垂直媒体RSS获取新闻（直链）"""
    now = datetime.now()
    cutoff = now - timedelta(hours=CUTOFF_HOURS)

    try:
        resp = requests.get(feed_url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(resp.content)
        items = []
        for entry in feed.entries[:max_results]:
            published = entry.get("published_parsed")
            if published:
                pub_dt = datetime(*published[:6])
                if pub_dt < cutoff:
                    continue

            title = re.sub(r'\s*[-—|]\s*\S+$', '', entry.title).strip()
            link = entry.link

            relevant, score = is_gaming_relevant(title)
            if relevant:
                items.append({
                    "title": title, "link": link, "score": score,
                    "category": category, "published": published or None
                })
        return items
    except Exception as e:
        print(f"  ⚠️ RSS {feed_url[:30]}... 获取失败: {e}")
        return []


def deduplicate(items):
    """去重，按时间降序（新的在前）+ 相关性降序"""
    seen = set()
    result = []
    now = datetime.now()

    def sort_key(item):
        pub = item.get("published")
        if pub is None:
            return (1, 0, -item.get("score", 0))
        if isinstance(pub, time.struct_time):
            pub = datetime(*pub[:6])
        return (0, -pub.timestamp(), -item.get("score", 0))

    for item in sorted(items, key=sort_key):
        key = item["title"][:35]
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def analyze_trends(all_items, deep_items):
    all_titles = " ".join([i["title"] for i in all_items])
    deep_titles = " ".join([i["title"] for i in deep_items])

    trends = []
    for category, keywords in TREND_CATEGORIES.items():
        hits = sum(1 for kw in keywords if kw.lower() in all_titles.lower())
        deep_hits = sum(1 for kw in keywords if kw.lower() in deep_titles.lower())
        if hits > 0:
            trends.append({
                "category": category,
                "hits": hits + deep_hits * 2,
                "day_hits": hits,
            })

    trends.sort(key=lambda x: x["hits"], reverse=True)
    return trends[:5]


def generate_wechat_message(all_items, new_game, monetization, industry,
                             steam, esports, overseas, trends, deep_items):
    top = all_items[:8]

    msg = f"## 🎮 游戏日报 {TODAY}\n\n"

    msg += "**今日速览**\n\n"
    for idx, item in enumerate(top, 1):
        title = item["title"][:60]
        msg += f"{idx}. [{title}]({item['link']})\n"

    if new_game:
        msg += f"\n**🆕 新游 & 测试**\n\n"
        for idx, item in enumerate(new_game[:5], 1):
            title = item["title"][:55]
            msg += f"{idx}. [{title}]({item['link']})\n"

    all_monetization = deduplicate(monetization + deep_items)
    if all_monetization:
        msg += f"\n**💰 商业化 & 活动**\n\n"
        for idx, item in enumerate(all_monetization[:5], 1):
            title = item["title"][:55]
            msg += f"{idx}. [{title}]({item['link']})\n"

    if steam:
        msg += f"\n**🎮 Steam & 主机**\n\n"
        for idx, item in enumerate(steam[:4], 1):
            title = item["title"][:55]
            msg += f"{idx}. [{title}]({item['link']})\n"

    if industry:
        msg += f"\n**📊 行业动态**\n\n"
        for idx, item in enumerate(industry[:4], 1):
            title = item["title"][:55]
            msg += f"{idx}. [{title}]({item['link']})\n"

    if trends:
        msg += f"\n---\n**🌬️ 今日风向**\n\n"
        trend_labels = {
            "BattlePass/通行证": "战令/通行证话题活跃，关注付费分层和奖励设计",
            "抽卡/Gacha": "抽卡/Gacha讨论增多，留意概率公示和保底机制走向",
            "皮肤/外观付费": "外观付费持续升温，皮肤经济和限定策略值得关注",
            "付费模式创新": "付费模式有新探索，订阅/买断/混合变现值得研究",
            "出海/全球化": "出海动态密集，关注本地化运营和支付基建",
            "新游密集上线": "新游密集上线期，首日留存和付费设计是观察重点",
            "AI+游戏": "AI与游戏结合话题出现，关注AIGC落地进展",
            "跨平台": "跨平台趋势明显，PC+主机+手机多端互通成标配",
            "电竞/赛事": "电竞话题活跃，赛事商业化和战队运营值得关注",
            "停运/关服": "有产品关停消息，分析失败原因比看成功更有价值",
            "收购/投融资": "资本动作频繁，关注收并购背后的战略布局",
            "玩家行为/社区": "玩家行为讨论增加，社区运营和用户研究有新动向",
        }
        for t in trends[:3]:
            label = trend_labels.get(t["category"], t["category"])
            msg += f"- **{t['category']}**：{label}\n"

    msg += f"\n[📋 查看完整日报](https://github.com/yaozi123456/gaming-news/blob/master/{TODAY}.md)"

    return msg


def generate_report():
    print(f"=== 生成 {TODAY} 游戏行业日报 ===\n")

    all_news = {}

    # Bing News RSS
    for query, category in BING_SOURCES:
        print(f"  Bing: {query[:30]}")
        results = fetch_bing_news(query)
        all_news[category] = results
        time.sleep(1.0)

    # 垂直媒体 RSS
    for feed_url, category in DIRECT_FEEDS:
        print(f"  直连: {feed_url[:40]}")
        results = fetch_direct_feed(feed_url, category)
        existing = all_news.get(category, [])
        all_news[category] = existing + results
        time.sleep(0.5)

    # 商业化扩展（7天深度扫描）
    deep_items = []
    for query in MONETIZATION_QUERIES:
        print(f"  深度: {query[:30]}")
        results = fetch_bing_news(query, max_results=10, cutoff_hours=MONETIZATION_CUTOFF_HOURS)
        deep_items.extend(results)
        time.sleep(0.8)

    # 合并
    all_items = []
    for cat, items in all_news.items():
        for item in items:
            item["category"] = cat
            all_items.append(item)

    all_items = deduplicate(all_items)
    deep_items = deduplicate(deep_items)

    # 分类
    new_game = [i for i in all_items if i["category"] == "new_game"]
    monetization = [i for i in all_items if i["category"] == "monetization"]
    industry = [i for i in all_items if i["category"] == "industry"]
    steam = [i for i in all_items if i["category"] == "steam"]
    esports = [i for i in all_items if i["category"] == "esports"]
    overseas = [i for i in all_items if i["category"] == "overseas"]

    trends = analyze_trends(all_items, deep_items)

    # ==== Markdown 报告 ====
    md = f"""# 游戏行业日报 — {TODAY}

> 🤖 自动生成 · 来源：Bing News + 游戏陀螺 + 机核 · [查看往期](./index.md)

---

## 今日速览

"""
    top_items = all_items[:10]
    for idx, item in enumerate(top_items, 1):
        md += f"{idx}. [{item['title']}]({item['link']})\n"

    sections = [
        ("新游 & 测试动态", new_game, 6),
        ("商业化 & 活动", deduplicate(monetization + deep_items), 6),
        ("行业动态", industry, 5),
        ("Steam & 主机", steam, 6),
        ("出海 & 全球化", overseas, 5),
        ("电竞 & 赛事", esports, 5),
    ]

    for title, items, count in sections:
        if not items:
            continue
        md += f"""
---

## {title}

"""
        for idx, item in enumerate(items[:count], 1):
            md += f"{idx}. [{item['title']}]({item['link']})\n"

    if trends:
        md += f"""
---

## 风向总结

> 基于今日新闻关键词聚类 + 近7天商业化深度扫描

"""
        md += "| 趋势方向 | 热度 | 解读 |\n"
        md += "|----------|------|------|\n"
        trend_insights = {
            "BattlePass/通行证": "通行证/战令话题活跃，关注付费分层设计",
            "抽卡/Gacha": "抽卡讨论增多，概率公示和保底机制成焦点",
            "皮肤/外观付费": "外观付费持续升温，限定策略值得研究",
            "付费模式创新": "付费模式有新探索，混合变现成趋势",
            "出海/全球化": "出海动态密集，本地化运营和支付是关键",
            "新游密集上线": "新游密集上线，首日留存和付费转化是观察窗口",
            "AI+游戏": "AI与游戏结合加速，AIGC落地值得关注",
            "跨平台": "多端互通成标配，跨平台策略值得研究",
            "电竞/赛事": "赛事商业化持续推进",
            "停运/关服": "产品关停值得复盘：失败比成功更有学习价值",
            "收购/投融资": "资本动作频繁，背后战略布局值得关注",
            "玩家行为/社区": "玩家行为讨论增加，社区运营有新动向",
        }
        for t in trends[:5]:
            heat = "🔥" * min(3, t["hits"])
            insight = trend_insights.get(t["category"], "")
            md += f"| {t['category']} | {heat} | {insight} |\n"

    md += f"""
---

## 学习启发

- 留意今日**新游上线/测试动态**中的玩法和付费设计，想想能否借鉴到自己的项目中
- 关注**商业化板块**的活动机制、定价策略、BattlePass设计
- 行业投融资动态反映资本方向，可判断哪些赛道在升温
- 风向总结中的趋势可作为周报/月报分析的切入点

---

*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC · 共 {len(all_items)} 条（含7天商业化深度扫描）*
"""

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\n✅ 报告已生成: {OUTPUT} ({len(all_items)} 条新闻)")

    wechat_msg = generate_wechat_message(
        all_items, new_game, monetization, industry,
        steam, esports, overseas, trends, deep_items
    )
    return len(all_items), wechat_msg


def send_to_serverchan(sendkey, title, content):
    if not sendkey:
        print("  跳过Server酱推送（未配置SENDKEY）")
        return
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    try:
        resp = requests.post(url, data={
            "title": title,
            "desp": content
        }, timeout=10)
        result = resp.json()
        print(f"  Server酱推送: {result}")
        return result
    except Exception as e:
        print(f"  Server酱推送失败: {e}")
        return None


if __name__ == "__main__":
    count, wechat_msg = generate_report()

    sendkey = os.environ.get("SERVERCHAN_SENDKEY", "")
    if sendkey:
        send_to_serverchan(sendkey, f"游戏行业日报 {TODAY}", wechat_msg)
