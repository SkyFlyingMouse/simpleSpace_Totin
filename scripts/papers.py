"""找论文：从 HuggingFace Daily Papers 和 arXiv 抓候选，用 DeepSeek 逐篇打分选题。

改自 MyRadio/papers.py，主要区别：
1. build_pool 不再按点赞全局截断（那样会饿死 0 赞的 arXiv 生物论文），改成按来源/分类分别限量。
2. fetch_arxiv 额外解析 comment（常含中稿信息）和是否放出代码。
3. score_papers 改成逐篇 1-5 打分 + 分组，全部返回（阈值过滤交给调用方）。
"""

import json
import re
import time
import datetime
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


HF_API = "https://huggingface.co/api/daily_papers"
ARXIV_API = "https://export.arxiv.org/api/query"
UA = {"User-Agent": "Mozilla/5.0 (knowledgeHub daily paper digest)"}


def _arxiv_id(raw):
    """把各种形式的 id 统一成不带版本号的裸 id，比如 2608.23283。"""
    raw = raw.strip()
    raw = raw.split("/")[-1]          # 去掉 http://arxiv.org/abs/ 前缀
    raw = re.sub(r"v\d+$", "", raw)   # 去掉 v1/v2 版本号
    return raw


def _has_code(text):
    """摘要或 comment 里出现代码仓库链接，视为放出代码。"""
    return bool(re.search(r"github\.com|gitlab\.com", text or "", re.I))


def fetch_huggingface(min_upvotes, max_papers):
    """抓 HF Daily Papers。取昨天和今天两天，凑够量。返回候选 dict 列表。"""
    papers = []
    today = datetime.date.today()
    for delta in (0, 1):
        date = (today - datetime.timedelta(days=delta)).isoformat()
        r = requests.get(HF_API, params={"date": date}, headers=UA, timeout=30)
        if r.status_code != 200:
            continue
        for item in r.json():
            p = item.get("paper", {})
            upvotes = p.get("upvotes", 0) or 0
            if upvotes < min_upvotes:
                continue
            abstract = (p.get("summary") or "").strip()
            papers.append({
                "id": _arxiv_id(p.get("id", "")),
                "title": (p.get("title") or "").strip(),
                "abstract": abstract,
                "upvotes": upvotes,
                "comment": "",
                "has_code": _has_code(abstract),
                "source": "huggingface",
            })
    # HF 自带点赞，取最热的前 max_papers 篇
    papers.sort(key=lambda x: x["upvotes"], reverse=True)
    return papers[:max_papers]


def fetch_arxiv(categories, max_per_cat):
    """抓 arXiv 每个分类最近的论文，解析 comment 和代码信号。返回候选 dict 列表。"""
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    papers = []
    for cat in categories:
        params = {
            "search_query": f"cat:{cat}",
            "start": 0,
            "max_results": max_per_cat,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        r = requests.get(ARXIV_API, params=params, headers=UA, timeout=30)
        if r.status_code != 200:
            continue
        root = ET.fromstring(r.text)
        for entry in root.findall("a:entry", ns):
            arx_id = _arxiv_id(entry.find("a:id", ns).text)
            title = " ".join(entry.find("a:title", ns).text.split())
            abstract = " ".join(entry.find("a:summary", ns).text.split())
            comment_el = entry.find("arxiv:comment", ns)
            comment = " ".join(comment_el.text.split()) if comment_el is not None and comment_el.text else ""
            papers.append({
                "id": arx_id,
                "title": title,
                "abstract": abstract,
                "upvotes": 0,          # arXiv 没有点赞数
                "comment": comment,
                "has_code": _has_code(abstract + " " + comment),
                "source": f"arxiv:{cat}",
            })
        time.sleep(3)  # arXiv 要求请求间隔，别太快
    return papers


def build_pool(config, seen_ids):
    """汇总所有来源，去掉已处理过的和重复的，返回候选池。

    注意：不再按点赞全局截断。各来源在自己的 fetch 里已经限过量，
    这里只做去重，保证 arXiv 的生物论文不会被 HF 的高赞论文挤掉。
    """
    src = config["sources"]
    pool = []
    if src.get("huggingface"):
        pool += fetch_huggingface(src.get("hf_min_upvotes", 5), src.get("hf_max_papers", 25))
    if src.get("arxiv"):
        pool += fetch_arxiv(src["arxiv_categories"], src.get("arxiv_max_per_cat", 15))

    # 去重（同一篇论文可能同时出现在 HF 和 arXiv），保留点赞数高的那条
    dedup = {}
    for p in pool:
        pid = p["id"]
        if not pid or pid in seen_ids:
            continue
        if pid not in dedup or p["upvotes"] > dedup[pid]["upvotes"]:
            dedup[pid] = p
    return list(dedup.values())


def _signal_line(p):
    """把一篇论文的硬信号拼成一行，喂给打分 prompt。"""
    bits = []
    if p["upvotes"]:
        bits.append(f"HF{p['upvotes']}赞")
    if p["comment"]:
        bits.append(f"comment: {p['comment'][:120]}")
    if p["has_code"]:
        bits.append("有代码")
    return " | ".join(bits) if bits else "无额外信号"


def score_papers(client, model, interests, rubric, groups, pool):
    """一次 DeepSeek 调用给候选池每篇打分（1-5）并分组。

    返回全部打过分的论文，每个 dict 额外带 score 和 group 字段，按分数降序。
    不在这里按阈值过滤：低分的也要存下来，周报月报要用。
    """
    if not pool:
        return []
    listing = "\n".join(
        f"[{i}] {p['title']}\n"
        f"    信号: {_signal_line(p)}\n"
        f"    摘要: {p['abstract'][:300]}"
        for i, p in enumerate(pool)
    )
    group_list = " / ".join(groups)
    prompt = (
        f"这是我的兴趣：\n{interests}\n\n"
        f"评分标准（1-5 分）：\n{rubric}\n\n"
        f"下面是今天的候选论文列表（编号从 0 开始）：\n{listing}\n\n"
        f"请根据我的兴趣、评分标准和每篇的信号，给每篇论文打 1-5 分，并归到这些分组之一：{group_list}。\n"
        f"只返回一个 JSON 数组，元素形如 {{\"i\": 编号, \"score\": 分数, \"group\": \"分组名\"}}，"
        f"不要任何解释、不要 markdown 代码块标记。"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = resp.choices[0].message.content.strip()
    # 去掉可能包裹的 ```json ``` 标记
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    items = json.loads(text)

    scored = []
    for it in items:
        i = it.get("i")
        group = it.get("group", "其他")
        if not isinstance(i, int) or not (0 <= i < len(pool)):
            continue
        p = dict(pool[i])
        p["score"] = it.get("score", 0)
        p["group"] = group if group in groups else "其他"
        scored.append(p)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def fetch_fulltext(arxiv_id):
    """抓 arxiv.org/html 全文正文。抓不到返回 None（上层退回用摘要）。"""
    url = f"https://arxiv.org/html/{arxiv_id}"
    try:
        r = requests.get(url, headers=UA, timeout=30)
    except requests.RequestException:
        return None
    if r.status_code != 200 or "<html" not in r.text.lower():
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    # 去掉参考文献、公式图表等噪声
    for tag in soup.select("script, style, .ltx_bibliography, .ltx_appendix, figure, table"):
        tag.decompose()
    body = soup.find("article") or soup.body
    if not body:
        return None
    text = body.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)
    # 全文可能很长，截断到大约 2 万字，够写摘要也省 token
    return text[:20000] if len(text) > 200 else None
