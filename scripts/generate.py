"""每日前沿速览：找论文 -> 打分选题 -> 写短评 -> 渲染成 Hugo 文章。

目标：一天内容 10 分钟内扫完。输出 content/posts/前沿速览-YYYY-MM-DD.md，
按方向分组，每篇 2～3 句短评 + 原文链接（只用摘要，不抓全文）。
用法：
    DEEPSEEK_API_KEY=xxx python scripts/generate.py
"""

import datetime
import json
import os
import re

import yaml
from openai import OpenAI

import papers

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)                        # blog_KISS 根目录
POSTS_DIR = os.path.join(REPO, "content", "posts")
STATE_FILE = os.path.join(HERE, "state", "seen.json")
SCORES_DIR = os.path.join(HERE, "state", "scores")


def load_seen():
    if os.path.exists(STATE_FILE):
        return set(json.load(open(STATE_FILE)))
    return set()


def save_seen(seen):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    json.dump(sorted(seen), open(STATE_FILE, "w"), ensure_ascii=False, indent=2)


def save_scores(date, scored, picked_ids):
    """把当天全部打分结果存一个文件，周报和月报直接读它，不用重新打分。"""
    os.makedirs(SCORES_DIR, exist_ok=True)
    records = [
        {
            "id": p["id"],
            "title": p["title"],
            "score": p["score"],
            "group": p["group"],
            "abstract": p["abstract"][:500],
            "upvotes": p["upvotes"],
            "comment": p["comment"],
            "has_code": p["has_code"],
            "picked": p["id"] in picked_ids,   # 是否进了当天日报，周报靠它挂「详细解读」链接
        }
        for p in scored
    ]
    path = os.path.join(SCORES_DIR, f"{date}.json")
    json.dump(records, open(path, "w"), ensure_ascii=False, indent=2)


def write_summary(client, model, summary_prompt, paper, body):
    """让 DeepSeek 基于摘要写 2～3 句短评（快扫用，不需要全文）。"""
    prompt = (
        f"{summary_prompt}\n\n"
        f"标题：{paper['title']}\n\n"
        f"摘要：\n{body}"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=200,
    )
    text = resp.choices[0].message.content.strip()
    # 压成一段：去掉多余换行和开场白
    text = " ".join(line.strip() for line in text.splitlines() if line.strip())
    text = re.sub(r"^(好的|以下是|下面是|我将|我会|遵照|按照您|当然)[^。！？]*[。！？]\s*", "", text)
    return text.strip()


def meta_line(paper):
    """把打分和硬信号拼成文章里的一行小字。"""
    bits = [f"评分{paper['score']}"]
    if paper["upvotes"]:
        bits.append(f"HF {paper['upvotes']}赞")
    if paper["comment"]:
        bits.append(paper["comment"][:60])
    if paper["has_code"]:
        bits.append("有代码")
    return " · ".join(bits)


def render_post(date, groups, picked_by_group):
    """按分组拼出整篇 Markdown 文章内容（短评版，10 分钟内可扫完）。"""
    group_titles = {"LLM": "大模型 LLM", "RL": "强化学习 RL", "AI+生物": "AI + 生物", "其他": "其他"}
    total = sum(len(v) for v in picked_by_group.values())
    lines = [
        "---",
        f'title: "前沿速览 {date}"',
        f"date: {date}",
        'tags: ["前沿速览"]',
        "---",
        "",
        f"今日热点 {total} 篇，每篇两三句短评，约 10 分钟内可扫完。只留评分 ≥4 的重点；点标题进原文。",
        "",
    ]
    for g in groups:
        items = picked_by_group.get(g, [])
        if not items:
            continue
        lines.append(f"## {group_titles.get(g, g)}")
        lines.append("")
        for p in items:
            url = f"https://arxiv.org/abs/{p['id']}"
            lines.append(f"### [{p['title']}]({url})")
            lines.append(f"`{meta_line(p)}`")
            lines.append("")
            lines.append(p["summary"])
            lines.append("")
    return "\n".join(lines)


def main():
    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    deepseek = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    model = cfg["script"]["model"]
    groups = cfg["groups"]

    seen = load_seen()
    date = datetime.date.today().isoformat()

    print("1. 抓候选论文...")
    pool = papers.build_pool(cfg, seen)
    print(f"   候选池 {len(pool)} 篇")
    if not pool:
        print("   没有新论文，今天不出。")
        return

    print("2. DeepSeek 打分选题...")
    scored = papers.score_papers(deepseek, model, cfg["interests"], cfg["rubric"], groups, pool)
    picked = [p for p in scored if p["score"] >= cfg["score_threshold"]][: cfg["max_papers"]]
    save_scores(date, scored, {p["id"] for p in picked})
    print(f"   打分 {len(scored)} 篇，选中 {len(picked)} 篇（阈值 {cfg['score_threshold']}）")
    if not picked:
        print("   今天没有达到阈值的论文，不出。")
        return

    print("3. 逐篇写短评（只用摘要）...")
    picked_by_group = {g: [] for g in groups}
    for p in picked:
        print(f"   [{p['score']}分/{p['group']}] {p['title'][:55]}")
        p["summary"] = write_summary(
            deepseek, model, cfg["script"]["summary_prompt"], p, p["abstract"]
        )
        picked_by_group[p["group"]].append(p)
        seen.add(p["id"])

    print("4. 渲染文章...")
    os.makedirs(POSTS_DIR, exist_ok=True)
    out_md = os.path.join(POSTS_DIR, f"前沿速览-{date}.md")
    with open(out_md, "w") as f:
        f.write(render_post(date, groups, picked_by_group))
    save_seen(seen)
    print(f"完成：{out_md}")


if __name__ == "__main__":
    main()
