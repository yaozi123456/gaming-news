#!/usr/bin/env python3
"""
游戏行业日报 — GitHub Actions 版
v3: 微信可点击链接 + 风向总结 + 扩大商业化时间范围 + 链接解析
"""
import requests
import feedparser
from datetime import datetime, timedelta
import re
import time
import os
import json
from collections import Counter

TODAY = datetime.now().strftime("%Y-%m-%d")
OUTPUT = f"{TODAY}.md"
CUTOFF_HOURS = 48
GNEWS_BASE = "https://news.google.com/rss/search"

# ==== 数据源 ====
SOURCES = [
    ("新游 公测 上线 开服 测试", "new_game"),
    ("手游 商业化 BattlePass 通行证 皮肤 抽卡", "monetization"),
    ("游戏公司 网易 腾讯 米哈游 投融资 收购", "industry"),
    ("Steam 热门游戏 新作 主机 PS5 Switch", "steam"),
    ("电竞 赛事 俱乐部 网吧", "esports"),
    ("游戏出海 海外收入 全球化", "overseas"),
]

# 商业化/活动扩展查询：扩大到7天，用于风向总结
MONETIZATION_DEEP = ("手游 商业化 BattlePass 通行证 活动策划 付费设计 玩家行为 用户趋势", "monetization_deep")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) GameDaily/3.0"
}

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

# 风向总结关键词聚类
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


def is_gaming_relevant(title):
    score = 0
    for kw in CORE_KEYWORDS:
        if kw.lower() in title.lower():
            score += 1
    for kw, boost in BOOST_KEYWORDS.items():
        if kw.lower() in title.lower():
            score += boost
    return score >= 1, score


def fetch_google_news(query, max_results=12, when="24h"):
    """从Google News RSS获取标题和链接，支持自定义时间范围"""
    full_query = f"{query} when:{when}"
    url = f"{GNEWS_BASE}?q={requests.utils.quote(full_query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    now = datetime.now()
    cutoff = now - timedelta(hours=CUTOFF_HOURS)

    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_results]:
            published = entry.get("published_parsed")
            if published:
                pub_dt = datetime(*published[:6])
                if pub_dt < cutoff:
                    continue

            title = re.sub(r'\s*-\s*\S+$', '', entry.title).strip()
            link = entry.link
            relevant, score = is_gaming_relevant(title)
            if relevant:
                items.append({"title": title, "link": link, "score": score})
        return items
    except Exception as e:
        print(f"  ⚠️ {query[:20]}... 获取失败: {e}")
        return []


def resolve_url(url, timeout=3):
    """尝试解析Google News跳转链接到最终URL"""
    try:
        resp = requests.head(url, allow_redirects=True, timeout=timeout, headers=HEADERS)
        final = resp.url
        if final != url and "news.google.com" not in final:
            return final
    except Exception:
        pass
    return url


def deduplicate(items):
    seen = set()
    result = []
    for item in sorted(items, key=lambda x: x.get("score", 0), reverse=True):
        key = item["title"][:35]
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def analyze_trends(all_items, deep_items):
    """分析趋势：关键词聚类 + 热度统计"""
    all_titles = " ".join([i["title"] for i in all_items])
    deep_titles = " ".join([i["title"] for i in deep_items])

    trends = []
    for category, keywords in TREND_CATEGORIES.items():
        hits = sum(1 for kw in keywords if kw.lower() in all_titles.lower())
        deep_hits = sum(1 for kw in keywords if kw.lower() in deep_titles.lower())
        if hits > 0:
            trends.append({
                "category": category,
                "hits": hits + deep_hits * 2,  # 商业化深度新闻加权
                "day_hits": hits,
            })

    trends.sort(key=lambda x: x["hits"], reverse=True)
    return trends[:5]


def generate_wechat_message(all_items, new_game, monetization, industry, steam, esports, overseas, trends, deep_items):
    """生成微信推送用的markdown消息（带可点击链接）"""
    top = all_items[:8]

    msg = f"## 🎮 游戏日报 {TODAY}\n\n"

    # 今日速览
    msg += "**今日速览**\n\n"
    for idx, item in enumerate(top, 1):
        title = item["title"][:60]
        msg += f"{idx}. [{title}]({item['link']})\n"

    # 新游
    if new_game:
        msg += f"\n**🆕 新游 & 测试**\n\n"
        for idx, item in enumerate(new_game[:5], 1):
            title = item["title"][:55]
            msg += f"{idx}. [{title}]({item['link']})\n"

    # 商业化（含扩展查询结果）
    all_monetization = deduplicate(monetization + deep_items)
    if all_monetization:
        msg += f"\n**💰 商业化 & 活动**\n\n"
        for idx, item in enumerate(all_monetization[:5], 1):
            title = item["title"][:55]
            msg += f"{idx}. [{title}]({item['link']})\n"

    # Steam
    if steam:
        msg += f"\n**🎮 Steam & 主机**\n\n"
        for idx, item in enumerate(steam[:4], 1):
            title = item["title"][:55]
            msg += f"{idx}. [{title}]({item['link']})\n"

    # 行业
    if industry:
        msg += f"\n**📊 行业动态**\n\n"
        for idx, item in enumerate(industry[:4], 1):
            title = item["title"][:55]
            msg += f"{idx}. [{title}]({item['link']})\n"

    # 风向总结
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
    for query, category in SOURCES:
        print(f"  搜索(24h): {query}")
        results = fetch_google_news(query)
        all_news[category] = results
        time.sleep(1.2)

    # 商业化扩展查询（7天）
    print(f"  搜索(7d): {MONETIZATION_DEEP[0]}")
    deep_results = fetch_google_news(MONETIZATION_DEEP[0], max_results=15, when="7d")
    time.sleep(1.2)

    # 合并
    all_items = []
    for cat, items in all_news.items():
        for item in items:
            item["category"] = cat
            all_items.append(item)

    all_items = deduplicate(all_items)
    deep_items = deduplicate(deep_results)

    # 分类
    new_game = [i for i in all_items if i["category"] == "new_game"]
    monetization = [i for i in all_items if i["category"] == "monetization"]
    industry = [i for i in all_items if i["category"] == "industry"]
    steam = [i for i in all_items if i["category"] == "steam"]
    esports = [i for i in all_items if i["category"] == "esports"]
    overseas = [i for i in all_items if i["category"] == "overseas"]

    # 风向分析
    trends = analyze_trends(all_items, deep_items)

    # ==== Markdown 报告 ====
    md = f"""# 游戏行业日报 — {TODAY}

> 🤖 自动生成 · 来源：Google News · [查看往期](./index.md)

---

## 今日速览

"""
    top_items = all_items[:10]
    for idx, item in enumerate(top_items, 1):
        md += f"{idx}. [{item['title']}]({item['link']})\n"

    def write_section(md, title, items, count=6):
        if not items:
            return md
        md += f"""
---

## {title}

"""
        for idx, item in enumerate(items[:count], 1):
            md += f"{idx}. [{item['title']}]({item['link']})\n"
        return md

    md = write_section(md, "新游 & 测试动态", new_game)
    md = write_section(md, "商业化 & 活动", deduplicate(monetization + deep_items))
    md = write_section(md, "行业动态", industry)
    md = write_section(md, "Steam & 主机", steam)
    md = write_section(md, "出海 & 全球化", overseas)
    md = write_section(md, "电竞 & 赛事", esports)

    # 风向总结
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
            "收购/投融资": "资本动作频繁，背后的战略布局值得关注",
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

    # 生成微信推送消息
    wechat_msg = generate_wechat_message(
        all_items, new_game, monetization, industry,
        steam, esports, overseas, trends, deep_items
    )
    return len(all_items), wechat_msg


def send_to_serverchan(sendkey, title, content):
    """推送到Server酱微信，content为markdown格式"""
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
