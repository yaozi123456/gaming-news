#!/usr/bin/env python3
"""
游戏行业日报 — GitHub Actions 版
v5: 重要性分级 + 标题提炼 + 精选速览 + 可操作风向总结
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
CUTOFF_HOURS = 168
MONETIZATION_CUTOFF_HOURS = 720

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

# ==== 新闻源 ====
BING_BASE = "https://www.bing.com/news/search"
BING_SOURCES = [
    ("新游 公测 上线 开服 测试", "new_game"),
    ("手游 限定皮肤 返场 累充 活动", "monetization"),
    ("游戏公司 投融资 收购 腾讯 网易 米哈游", "industry"),
    ("Steam 热门游戏 PS5 Switch 主机 新作", "steam"),
    ("电竞 赛事 俱乐部 战队", "esports"),
    ("游戏出海 海外收入 全球化 本地化", "overseas"),
]

MONETIZATION_QUERIES = [
    "游戏 付费 变现 商业模式",
    "手游 活动 限定 返场",
    "游戏 商业化",
    "游戏 玩家行为 社区运营 用户",
]

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

# ==== 重要性评分体系 ====
# 来源权威度加权
SOURCE_AUTHORITY = {
    "腾讯": 5, "网易": 5, "米哈游": 5, "莉莉丝": 4, "鹰角": 4,
    "叠纸": 4, "库洛": 4, "三七": 4, "完美世界": 4, "字节": 4,
    "gcores": 3, "youxituoluo": 3, "17173": 2, "sohu": 1,
    "sina": 1, "qq.com": 2, "msn": 1, "36kr": 3,
}

# 内容类型重要性加权
IMPORTANCE_MARKERS = {
    # 战略级（财报/收购/上市/政策）
    "财报": 5, "收购": 5, "IPO": 5, "上市": 5, "融资": 4,
    "裁员": 4, "组织架构": 4, "政策": 4, "监管": 4,
    # 产品级（公测/上线/定档）
    "公测": 4, "定档": 4, "首曝": 4, "正式上线": 3,
    # 数据级（收入/流水/用户数）
    "收入": 3, "流水": 3, "销量": 3, "用户": 2,
    # 趋势级（AI/出海/新玩法）
    "AI": 3, "AIGC": 3, "出海": 3, "混合变现": 3, "买断制": 3,
    # 活动级（皮肤/返场/活动）
    "皮肤": 2, "返场": 2, "活动": 1,
}


def extract_real_url(bing_url):
    parsed = urlparse(bing_url)
    params = parse_qs(parsed.query)
    real = unquote(params.get("url", [""])[0])
    if real and "bing.com" not in real:
        return real
    return bing_url


def clean_title(title):
    """提炼标题：去来源后缀、去多余标点、控制长度"""
    # 去掉常见的来源后缀
    title = re.sub(r'\s*[-—|–]\s*[^-—|–]+$', '', title)
    title = re.sub(r'\s*[-—|–]\s*$', '', title)
    # 去掉多余空格
    title = re.sub(r'\s+', ' ', title).strip()
    # 太长则截断（保留完整句子边界）
    if len(title) > 80:
        # 在最后一个标点处截断
        cut = max(title.rfind('，', 40, 80), title.rfind('。', 40, 80),
                  title.rfind('！', 40, 80), title.rfind('？', 40, 80))
        if cut > 40:
            title = title[:cut+1]
        else:
            title = title[:77] + "..."
    return title


def calc_importance(title, score):
    """计算新闻重要性：来源权威 + 内容类型 + 关键词基础分"""
    importance = score  # 基础分

    # 来源权威
    for source, weight in SOURCE_AUTHORITY.items():
        if source.lower() in title.lower():
            importance += weight
            break

    # 内容类型
    for marker, weight in IMPORTANCE_MARKERS.items():
        if marker.lower() in title.lower():
            importance += weight

    # 标题长度信号（太短可能是广告/水贴，太长可能是水文）
    if 15 <= len(title) <= 60:
        importance += 1

    return importance


def is_gaming_relevant(title):
    score = 0
    for kw in CORE_KEYWORDS:
        if kw.lower() in title.lower():
            score += 1
    return score >= 1, score


def fetch_bing_news(query, max_results=12, cutoff_hours=None):
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

            title = clean_title(entry.title)
            raw_link = entry.link
            link = extract_real_url(raw_link)
            relevant, score = is_gaming_relevant(title)
            if relevant:
                importance = calc_importance(title, score)
                items.append({
                    "title": title, "link": link,
                    "score": score, "importance": importance,
                    "published": published or None
                })
        return items
    except Exception as e:
        print(f"  ⚠️ {query[:20]}... 获取失败: {e}")
        return []


def fetch_direct_feed(feed_url, category, max_results=15):
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

            title = clean_title(entry.title)
            link = entry.link
            relevant, score = is_gaming_relevant(title)
            if relevant:
                importance = calc_importance(title, score)
                items.append({
                    "title": title, "link": link,
                    "score": score, "importance": importance,
                    "category": category, "published": published or None
                })
        return items
    except Exception as e:
        print(f"  ⚠️ RSS {feed_url[:30]}... 获取失败: {e}")
        return []


def fetch_gameres():
    """从游资网 GameRes 获取深度文章（JSON API）"""
    url = "https://www.gameres.com/newslistJson"
    now = datetime.now()
    cutoff = now - timedelta(hours=CUTOFF_HOURS)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        items = []
        for article in data.get("list", []):
            ts = article.get("dateline", 0)
            pub_dt = datetime.fromtimestamp(ts)
            if pub_dt < cutoff:
                continue

            title = clean_title(article.get("subject", ""))
            if not title:
                continue

            if article.get("is_wailian"):
                link = article.get("wailian", "")
            else:
                link = "https://www.gameres.com" + article.get("url", "")

            tags = [t.get("tname", "") for t in article.get("tags", [])]
            tag_str = ",".join(tags)

            if "产品分析" in tag_str or "拆解分析" in tag_str:
                category = "deep_analysis"
            elif "Steam" in tag_str:
                category = "steam"
            elif "电子竞技" in tag_str:
                category = "esports"
            elif "厂商" in tag_str or "观察" in tag_str:
                category = "industry"
            else:
                category = "industry"

            importance = 3
            if "推荐" in tag_str:
                importance += 2
            if "产品分析" in tag_str or "拆解分析" in tag_str:
                importance += 2
            if "原创" in tag_str:
                importance += 1
            if "专访" in tag_str:
                importance += 1
            if 15 <= len(title) <= 60:
                importance += 1

            summary = article.get("summary", "")
            if len(summary) > 50:
                importance += 1

            items.append({
                "title": title,
                "link": link,
                "score": 2,
                "importance": importance,
                "category": category,
                "published": pub_dt.timetuple() if pub_dt else None,
                "source": "gameres"
            })
        print(f"  GameRes: {len(items)}篇")
        return items
    except Exception as e:
        print(f"  ⚠️ GameRes 获取失败: {e}")
        return []


def deduplicate(items):
    """去重，按重要性降序 + 时间降序"""
    seen = set()
    result = []
    now = datetime.now()

    def sort_key(item):
        pub = item.get("published")
        has_date = 0 if pub else 1
        ts = 0
        if pub:
            if isinstance(pub, time.struct_time):
                pub = datetime(*pub[:6])
            ts = -pub.timestamp()
        return (has_date, -item.get("importance", 0), ts)

    for item in sorted(items, key=sort_key):
        key = item["title"][:35]
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def analyze_trends(all_items, deep_items):
    """趋势分析：不只是关键词计数，还提取具体信号"""
    all_titles = " ".join([i["title"] for i in all_items])
    deep_titles = " ".join([i["title"] for i in deep_items])

    # 检测具体信号
    signals = []
    signal_patterns = [
        ("大厂组织调整", ["裁员", "组织架构", "调整", "高管", "离职", "任命"],
         "多家大厂出现裁员/高管变动/创业潮，人才从小厂流向创业公司",
         "大厂内部在重组，招聘方向的转变会透露战略重心——你下一份工作可能不在大厂而在创业公司"),
        ("产品关停潮", ["停运", "关服", "停服", "下架"],
         "有产品宣布停运/关服",
         "复盘比看成功更有价值——失败的产品往往死在付费太激进或内容枯竭，做活动时引以为戒"),
        ("AI落地加速", ["AI", "AIGC", "大模型", "人工智能", "AI工具"],
         "AI+游戏从概念转向落地，多家公司开始实际应用AI工具",
         "AI不会替代策划，但会用AI的策划会替代不会的——建议开始上手体验AI素材生成工具"),
        ("出海支付基建", ["出海", "支付", "基建", "本地化", "海外"],
         "出海讨论升温，支付基建和本地化运营成焦点",
         "出海运营不只是翻译语言，支付/客服/社区的全链路本地化才是竞争力，建议补充相关知识"),
        ("混合变现探索", ["买断制", "混合变现", "订阅", "月卡", "BattlePass", "通行证"],
         "买断制+订阅+通行证的混合变现正成为新趋势",
         "纯IAP不再是唯一解——作为活动策划，需要理解不同付费模型下活动设计的逻辑差异"),
        ("新游密集上线", ["公测", "上线", "开服", "定档", "新游"],
         "本周多款新游密集上线/公测/定档，新品竞争白热化",
         "竞品分析黄金窗口——每个新游的首日活动设计、付费引导都是一堂免费的产品课"),
        ("大厂3A/单机布局", ["3A", "单机", "买断制", "主机"],
         "腾讯网易等大厂加码3A/单机，产业从F2P向多元化付费转型",
         "3A买断制和F2P手游的付费设计逻辑完全不同——理解这种差异能拓宽你做活动的思路"),
        ("电竞商业化", ["电竞", "赛事", "战队", "冠军", "联赛"],
         "电竞赛事品牌化和商业化加速，KPL转会冷静期信号显示行业趋于理性",
         "赛事活动策划与游戏内活动有相通之处——赞助招商、赛程设计、用户激励都值得借鉴"),
        ("玩家消费降级", ["性价比", "降价", "福利", "免费", "白嫖"],
         "玩家对价格更敏感，免费福利和感知价值成为留存关键",
         "设计活动时，确保有足够的'免费获得感'——强制付费会流失，让玩家觉得'赚了'才是好活动"),
    ]

    for name, keywords, signal_msg, takeaway in signal_patterns:
        hits = sum(1 for kw in keywords if kw.lower() in all_titles.lower())
        deep_hits = sum(1 for kw in keywords if kw.lower() in deep_titles.lower())
        total = hits + deep_hits * 2
        if total > 0:
            signals.append({"name": name, "hits": total, "signal": signal_msg, "takeaway": takeaway})

    signals.sort(key=lambda x: x["hits"], reverse=True)
    return signals[:5]


def generate_wechat_message(all_items, sections_data, top5, trends):
    """生成微信推送——精选版"""
    msg = f"## 🎮 游戏日报 {TODAY}\n\n"

    # 重磅速览（只放top5）
    msg += "**🔥 今日重磅**\n\n"
    for idx, item in enumerate(top5, 1):
        title = item["title"][:60]
        msg += f"{idx}. [{title}]({item['link']})\n"

    # 各板块（有间距）
    for section_title, items, limit in sections_data:
        if not items:
            continue
        msg += f"\n**{section_title}**\n\n"
        for idx, item in enumerate(items[:limit], 1):
            title = item["title"][:55]
            msg += f"{idx}. [{title}]({item['link']})\n"

    # 从业者启示
    if trends:
        insight_slugs = {
            "新游密集上线": "new-game-wave", "AI落地加速": "ai-in-gaming",
            "混合变现探索": "hybrid-monetization", "大厂3A/单机布局": "aaa-single-player",
            "大厂组织调整": "studio-restructuring", "产品关停潮": "game-shutdown-wave",
            "出海支付基建": "overseas-payment-infra", "电竞商业化": "esports-business",
            "玩家消费降级": "player-spending-shift",
        }
        msg += f"\n---\n**💡 从业者启示**\n\n"
        for t in trends[:4]:
            slug = insight_slugs.get(t['name'], '')
            insight_url = f"https://github.com/yaozi123456/gaming-news/blob/master/insights/{slug}.md" if slug else ""
            if insight_url:
                msg += f"▪ **[{t['name']}]({insight_url})**\n"
            else:
                msg += f"▪ **{t['name']}**\n"
            msg += f"  {t.get('signal', '')}\n"
            msg += f"  → {t['takeaway']}\n\n"

    msg += f"[📋 查看完整日报](https://github.com/yaozi123456/gaming-news/blob/master/{TODAY}.md)"

    return msg


def update_insight_page(path, trend, all_items, action):
    """创建/更新启示深度页面，追加来源链接"""
    slug = path.replace("insights/", "").replace(".md", "")
    today = datetime.now().strftime("%Y-%m-%d")

    # 找到触发此启示的来源文章
    signal_keywords = {
        "new-game-wave": ["公测", "上线", "开服", "定档", "新游"],
        "ai-in-gaming": ["AI", "AIGC", "大模型", "人工智能"],
        "hybrid-monetization": ["买断制", "混合变现", "订阅", "月卡", "通行证", "BattlePass"],
        "aaa-single-player": ["3A", "单机", "买断制", "主机"],
        "studio-restructuring": ["裁员", "组织架构", "调整", "高管", "离职", "任命"],
        "game-shutdown-wave": ["停运", "关服", "停服", "下架"],
        "overseas-payment-infra": ["出海", "支付", "基建", "本地化", "海外"],
        "esports-business": ["电竞", "赛事", "战队", "冠军", "联赛"],
        "player-spending-shift": ["性价比", "降价", "福利", "免费", "白嫖"],
    }

    keywords = signal_keywords.get(slug, [])
    sources = [i for i in all_items if any(kw in i["title"] for kw in keywords)][:8]

    # 检查文件是否存在
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
        # 避免同一天重复追加
        if f"## 📅 {today} 更新" in existing:
            return
        # 追加今日来源
        new_section = f"\n\n## 📅 {today} 更新\n\n"
        new_section += "**当日信号来源**：\n\n"
        for s in sources[:5]:
            new_section += f"- [{s['title']}]({s['link']})\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(new_section)
    else:
        # 新建文件：框架（Claude cron 会补充深度内容）
        content = f"""# {trend['name']}

> 游戏行业从业者深度参考 · 基于每日新闻持续更新

---

## 最新信号

**{today}**：{trend.get('signal', '')}

{trend['takeaway']}

### 建议行动

{action}

---

## 来源文章

"""
        for s in sources[:6]:
            content += f"- [{s['title']}]({s['link']})\n"

        content += f"""

---

## 为什么这很重要

> 💡 Claude Code 每日定时任务会在此补充深度分析、案例拆解和行业背景。

---

*页面创建于 {today} · 每日自动更新*
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def generate_report():
    print(f"=== 生成 {TODAY} 游戏行业日报 ===\n")

    all_news = {}

    for query, category in BING_SOURCES:
        print(f"  Bing: {query[:30]}")
        results = fetch_bing_news(query)
        all_news[category] = results
        time.sleep(1.0)

    for feed_url, category in DIRECT_FEEDS:
        print(f"  直连: {feed_url[:40]}")
        results = fetch_direct_feed(feed_url, category)
        existing = all_news.get(category, [])
        all_news[category] = existing + results
        time.sleep(0.5)

    print("  GameRes 游资网:")
    gameres_items = fetch_gameres()
    for item in gameres_items:
        cat = item.get("category", "industry")
        existing = all_news.get(cat, [])
        all_news[cat] = existing + [item]

    deep_items = []
    for query in MONETIZATION_QUERIES:
        print(f"  深度: {query[:30]}")
        results = fetch_bing_news(query, max_results=10, cutoff_hours=MONETIZATION_CUTOFF_HOURS)
        deep_items.extend(results)
        time.sleep(0.8)

    all_items = []
    for cat, items in all_news.items():
        for item in items:
            item["category"] = cat
            all_items.append(item)

    all_items = deduplicate(all_items)
    deep_items = deduplicate(deep_items)

    # Top5 重磅新闻（按importance排序）
    top5 = sorted(all_items, key=lambda x: -x.get("importance", 0))[:5]

    # 分类
    new_game = [i for i in all_items if i["category"] == "new_game"]
    monetization = [i for i in all_items if i["category"] == "monetization"]
    industry = [i for i in all_items if i["category"] == "industry"]
    steam = [i for i in all_items if i["category"] == "steam"]
    esports = [i for i in all_items if i["category"] == "esports"]
    overseas = [i for i in all_items if i["category"] == "overseas"]
    deep_analysis = [i for i in all_items if i["category"] == "deep_analysis"]

    all_monetization = deduplicate(monetization + deep_items)
    trends = analyze_trends(all_items, deep_items)

    # ==== Markdown 报告 ====
    md = f"""# 游戏行业日报 — {TODAY}

> 🤖 自动生成 · 来源：Bing News + 游戏陀螺 + 机核 + 游资网 · [查看往期](./index.md)

---

## 今日重磅

"""

    for idx, item in enumerate(top5, 1):
        md += f"{idx}. ⭐ [{item['title']}]({item['link']})\n"

    # 分类板块
    sections = [
        ("深度分析 · 游资网", deep_analysis, 5),
        ("新游 & 测试动态", new_game, 6),
        ("商业化 & 活动", all_monetization, 6),
        ("行业动态", industry, 5),
        ("Steam & 主机", steam, 6),
        ("出海 & 全球化", overseas, 5),
        ("电竞 & 赛事", esports, 5),
    ]

    for sec_title, items, count in sections:
        if not items:
            continue
        md += f"""

---

## {sec_title}

"""
        for idx, item in enumerate(items[:count], 1):
            md += f"{idx}. [{item['title']}]({item['link']})\n"

    # 从业者启示 - 生成深度页面并链接
    if trends:
        os.makedirs("insights", exist_ok=True)
        insight_slugs = {
            "新游密集上线": "new-game-wave",
            "AI落地加速": "ai-in-gaming",
            "混合变现探索": "hybrid-monetization",
            "大厂3A/单机布局": "aaa-single-player",
            "大厂组织调整": "studio-restructuring",
            "产品关停潮": "game-shutdown-wave",
            "出海支付基建": "overseas-payment-infra",
            "电竞商业化": "esports-business",
            "玩家消费降级": "player-spending-shift",
        }

        suggestions = {
            "大厂组织调整": "关注目标公司招聘官网和脉脉讨论，了解HC变化和团队动态",
            "产品关停潮": "选一个近期关停的产品，花1小时分析其生命周期和可能的失败原因",
            "AI落地加速": "本周抽2小时体验一款AI游戏工具（如Scenario/Cursor），思考能否用到活动素材生成中",
            "出海支付基建": "阅读一篇出海支付/本地化运营的深度文章，建立基础知识框架",
            "混合变现探索": "找一款混合变现做得好的产品（如Gossip Harbor），拆解其付费节点和奖励设计",
            "新游密集上线": "选1-2款本周上线的新游，记录其首日活动设计、付费引导和社交裂变玩法",
            "大厂3A/单机布局": "对比3A买断制和F2P手游的付费设计差异，思考不同付费模型的活动设计逻辑",
            "电竞商业化": "关注电竞赛事的赞助品牌和活动形式，思考游戏内活动如何借鉴赛事营销手法",
            "玩家消费降级": "回顾自己做过的活动，检查是否有足够的'免费获得感'而非纯付费压力",
        }

        for t in trends:
            slug = insight_slugs.get(t['name'], re.sub(r'[^\w]', '-', t['name']))
            insight_path = f"insights/{slug}.md"
            action = suggestions.get(t['name'], "将相关文章加入阅读清单，周末做一次专题学习")

            # 更新/创建深度页面
            update_insight_page(insight_path, t, all_items, action)

        md += f"""

---

## 从业者启示

> 不只是看新闻，更是你的行业雷达。点击标题查看深度分析：

"""
        for t in trends:
            slug = insight_slugs.get(t['name'], re.sub(r'[^\w]', '-', t['name']))
            insight_url = f"https://github.com/yaozi123456/gaming-news/blob/master/insights/{slug}.md"
            action = suggestions.get(t['name'], "")
            md += f"\n### [{t['name']}]({insight_url})\n\n"
            md += f"**信号**：{t.get('signal', '今日相关讨论热度高。')}\n\n"
            md += f"**对你意味着什么**：{t['takeaway']}\n\n"
            md += f"**建议行动**：{action}\n"

    md += f"""

---

## 学习资源线索

以下新闻标题中包含值得深挖的知识点，建议选择性搜索学习：

"""
    # 找3-5个有学习价值的标题
    learn_keywords = ["怎么", "为什么", "如何", "报告", "趋势", "分析", "复盘", "拆解", "指南", "盘点", "深度", "洞察"]
    learn_items = [i for i in all_items if any(
        kw in i["title"] for kw in learn_keywords
    )][:5]
    if learn_items:
        for idx, item in enumerate(learn_items, 1):
            md += f"{idx}. [{item['title']}]({item['link']})\n"
    else:
        md += "- 今日暂无特别推荐的学习向文章，可自行浏览各板块链接\n"

    md += f"""

---

*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC · 共 {len(all_items)} 条（含30天商业化深度扫描）*
"""

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\n✅ 报告已生成: {OUTPUT} ({len(all_items)} 条新闻)")

    # 微信推送
    wechat_sections = [
        ("🆕 新游 & 测试", new_game, 4),
        ("💰 商业化 & 活动", all_monetization, 4),
        ("📊 行业动态", industry, 4),
        ("🎮 Steam & 主机", steam, 4),
    ]
    wechat_msg = generate_wechat_message(all_items, wechat_sections, top5, trends)
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
