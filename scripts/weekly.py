"""前沿周报：把一周里 >=4 分的论文重新排个先后，取 Top 10 写成一篇。

不重新打分——分数是日报当天就打好存下来的（state/scores/YYYY-MM-DD.json）。
这里只花一次 DeepSeek 调用，同时干两件事：排名次、每篇写一句话点评。
用法：
    DEEPSEEK_API_KEY=xxx python scripts/weekly.py             # 上一周（周一~周日）
    DEEPSEEK_API_KEY=xxx python scripts/weekly.py 2026-09-03  # 那天所在的那一周
"""

import datetime
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

MIN_SCORE = 4      # 只有 >=4 分的才进周报候选
TOP_N = 10         # 最终取多少篇
GROUP_TITLES = {"LLM": "大模型 LLM", "RL": "强化学习 RL", "AI+生物": "AI + 生物", "其他": "其他"}


def week_of(day):
    """给一天，返回它所在那周的周一和周日。"""
    monday = day - datetime.timedelta(days=day.weekday())
    return monday, monday + datetime.timedelta(days=6)


def load_week(monday, sunday):
    """读这一周的分数文件，缺哪天跳哪天。同一篇论文按最高分去重。"""
    best = {}
    day = monday
    while day <= sunday:
        path = os.path.join(SCORES_DIR, f"{day.isoformat()}.json")
        if os.path.exists(path):
            for r in json.load(open(path)):
                r["date"] = day.isoformat()
                if r["id"] not in best or r["score"] > best[r["id"]]["score"]:
                    best[r["id"]] = r
        day += datetime.timedelta(days=1)
    return list(best.values())


def signal_line(p):
    bits = [f"评分{p['score']}"]
    if p["upvotes"]:
        bits.append(f"HF {p['upvotes']}赞")
    if p["comment"]:
        bits.append(p["comment"][:60])
    if p["has_code"]:
        bits.append("有代码")
    return " · ".join(bits)


def rank_week(client, model, cands):
    """一次调用排出 Top N 并给每篇写一句话点评。返回按名次排好的论文列表。"""
    listing = "\n".join(
        f"[{i}] {c['title']}\n"
        f"    方向: {c['group']} | {signal_line(c)}\n"
        f"    摘要: {c['abstract'][:300]}"
        for i, c in enumerate(cands)
    )
    prompt = (
        f"下面是过去一周已经初筛出来的高分论文（编号从 0 开始）：\n{listing}\n\n"
        f"请从中挑出最值得读的 {TOP_N} 篇，按重要性从高到低排序，并给每篇写一句话点评，"
        f"说清楚它做了什么、为什么这周值得关注，不超过 60 字，不要客套话。\n"
        f"只返回一个 JSON 数组，按名次顺序排列，元素形如 "
        f'{{"i": 编号, "note": "一句话点评"}}，不要任何解释、不要 markdown 代码块标记。'
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()

    picked = []
    for rank, it in enumerate(json.loads(text)[:TOP_N], start=1):
        i = it.get("i")
        if not isinstance(i, int) or not (0 <= i < len(cands)):
            continue
        p = dict(cands[i])
        p["rank"] = rank
        p["note"] = (it.get("note") or "").strip()
        picked.append(p)
    return picked


def render_post(monday, sunday, total_cands, picked):
    title = f"前沿周报 {monday.isoformat()} ~ {sunday.strftime('%m-%d')}"
    lines = [
        "---",
        f'title: "{title}"',
        f"date: {(sunday + datetime.timedelta(days=1)).isoformat()}",
        'tags: ["前沿周报"]',
        "---",
        "",
        f"本周从 {total_cands} 篇高分论文里挑出最值得读的 {len(picked)} 篇，按重要性排序。"
        f"想看某篇的详细解读，点后面的链接回当天的日报。",
        "",
    ]
    for g, g_title in GROUP_TITLES.items():
        items = [p for p in picked if p["group"] == g]
        if not items:
            continue
        lines.append(f"## {g_title}")
        lines.append("")
        for p in items:
            url = f"https://arxiv.org/abs/{p['id']}"
            lines.append(f"### [{p['title']}]({url})")
            lines.append(f"`本周第 {p['rank']} · {signal_line(p)}`")
            lines.append("")
            if p["note"]:
                lines.append(p["note"])
                lines.append("")
            links = [f"[原文]({url})"]
            if p.get("picked"):
                # 用相对路径：站点部署在子路径下，写 /posts/... 会 404
                links.append(f"[当天详细解读](../前沿速览-{p['date']}/)")
            lines.append(" · ".join(links))
            lines.append("")
    return "\n".join(lines)


def main():
    day = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else \
        datetime.date.today() - datetime.timedelta(days=7)
    monday, sunday = week_of(day)
    print(f"周报范围：{monday} ~ {sunday}")

    records = load_week(monday, sunday)
    cands = sorted(
        [r for r in records if r["score"] >= MIN_SCORE],
        key=lambda r: r["score"], reverse=True,
    )
    print(f"这周共 {len(records)} 篇打过分，其中 {len(cands)} 篇 >={MIN_SCORE} 分")
    if not cands:
        print("这周没有高分论文，不出周报。")
        return

    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    picked = rank_week(client, cfg["script"]["model"], cands)
    print(f"选出 {len(picked)} 篇")

    os.makedirs(POSTS_DIR, exist_ok=True)
    iso_year, iso_week, _ = monday.isocalendar()
    out_md = os.path.join(POSTS_DIR, f"前沿周报-{iso_year}-W{iso_week:02d}.md")
    with open(out_md, "w") as f:
        f.write(render_post(monday, sunday, len(cands), picked))
    print(f"完成：{out_md}")


if __name__ == "__main__":
    main()
