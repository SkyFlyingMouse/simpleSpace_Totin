"""前沿月报：读一个月的打分记录，按方向各写一段趋势综述。

月尺度才看得出走向，所以月报不做排行榜（那和周报重复），只讲「这个月这个方向在往哪走」。
每个方向一次 DeepSeek 调用。正文里的论文链接不让模型写——模型只输出编号 [12]，
代码再换成真实标题和 arXiv 链接，物理上编不出死链。
用法：
    DEEPSEEK_API_KEY=xxx python scripts/monthly.py          # 上个月
    DEEPSEEK_API_KEY=xxx python scripts/monthly.py 2026-08  # 指定月份
"""

import datetime
import glob
import json
import os
import re
import sys

import yaml
from openai import OpenAI

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
POSTS_DIR = os.path.join(REPO, "content", "posts")
SCORES_DIR = os.path.join(HERE, "state", "scores")

MIN_SCORE = 4        # 只有 >=4 分的才进月报
MAX_PER_GROUP = 120  # 每个方向最多喂多少篇给模型，防止 prompt 撑爆上下文
GROUP_TITLES = {"LLM": "大模型 LLM", "RL": "强化学习 RL", "AI+生物": "AI + 生物", "其他": "其他"}


def load_month(ym):
    """读这个月所有分数文件。同一篇论文按最高分去重。"""
    best = {}
    for path in sorted(glob.glob(os.path.join(SCORES_DIR, f"{ym}-*.json"))):
        date = os.path.basename(path)[: -len(".json")]
        for r in json.load(open(path)):
            r["date"] = date
            if r["id"] not in best or r["score"] > best[r["id"]]["score"]:
                best[r["id"]] = r
    return list(best.values())


def write_trend(client, model, ym, group_title, items):
    """让 DeepSeek 给一个方向写趋势综述。提到论文时只准写编号。"""
    listing = "\n".join(
        f"[{i}] {p['title']}\n    摘要: {p['abstract'][:300]}"
        for i, p in enumerate(items)
    )
    prompt = (
        f"这是 {ym} 这个月「{group_title}」方向筛出来的高分论文（编号从 0 开始）：\n{listing}\n\n"
        f"请写一段中文趋势综述，2-3 个自然段，段落之间用一个空行隔开。"
        f"讲清楚这个月这个方向的研究重心在往哪走：哪几类问题被反复攻、出现了哪些新思路、"
        f"有没有明显的转折或共识。面向懂一些 AI 基础的读者，用连贯叙述，"
        f"不要分点罗列、不要 markdown 标记、不要任何开场白。\n"
        f"提到具体论文时，只写它的编号方括号（例如 [12]），"
        f"绝对不要写论文标题、不要写任何网址或链接。"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )
    text = resp.choices[0].message.content.strip()
    text = "\n".join(line.strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def link_refs(text, items):
    """把模型写的 [12] 换成真实的 [标题](arXiv 链接)。编号越界的原样留着。"""
    def repl(m):
        i = int(m.group(1))
        if 0 <= i < len(items):
            p = items[i]
            return f"[{p['title']}](https://arxiv.org/abs/{p['id']})"
        return m.group(0)
    return re.sub(r"\[(\d+)\]", repl, text)


def main():
    if len(sys.argv) > 1:
        ym = sys.argv[1]
    else:
        first = datetime.date.today().replace(day=1)
        ym = (first - datetime.timedelta(days=1)).strftime("%Y-%m")
    print(f"月报范围：{ym}")

    records = load_month(ym)
    highs = [r for r in records if r["score"] >= MIN_SCORE]
    print(f"这个月共 {len(records)} 篇打过分，其中 {len(highs)} 篇 >={MIN_SCORE} 分")
    if not highs:
        print("这个月没有高分论文，不出月报。")
        return

    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    model = cfg["script"]["model"]

    year, month = ym.split("-")
    # 月报是次月 1 号发的，日期得写发布日，否则文章会沉到一个月前
    publish = (datetime.date(int(year), int(month), 1) + datetime.timedelta(days=32)).replace(day=1)
    lines = [
        "---",
        f'title: "前沿月报 {ym}"',
        f"date: {publish.isoformat()}",
        'tags: ["前沿月报"]',
        "---",
        "",
        f"{year} 年 {int(month)} 月共扫过 {len(records)} 篇论文，其中 {len(highs)} 篇达到 "
        f"{MIN_SCORE} 分及以上。下面按方向说说这个月的走向，文中论文都可以点开看原文。",
        "",
    ]
    for g, g_title in GROUP_TITLES.items():
        items = sorted([r for r in highs if r["group"] == g],
                       key=lambda r: r["score"], reverse=True)[:MAX_PER_GROUP]
        if not items:
            continue
        print(f"   写 {g_title}（{len(items)} 篇）...")
        trend = write_trend(client, model, ym, g_title, items)
        lines += [f"## {g_title}", "", link_refs(trend, items), ""]

    os.makedirs(POSTS_DIR, exist_ok=True)
    out_md = os.path.join(POSTS_DIR, f"前沿月报-{ym}.md")
    with open(out_md, "w") as f:
        f.write("\n".join(lines))
    print(f"完成：{out_md}")


if __name__ == "__main__":
    main()
