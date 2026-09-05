# 前沿速览：日报 + 周报 + 月报

每天自动从 arXiv 和 HuggingFace Daily Papers 里挑出 AI / LLM / 强化学习 / 计算生物学方向**值得看的**论文，用 DeepSeek 打分筛选、写成中文摘要，生成一篇博客文章。你早上打开博客就能扫全局，感兴趣的点标题看原文。

在日报之上还有两层：

- **周报**（每周一）：一周里 ≥4 分的论文重新排个先后，取 Top 10，每篇一句话点评，链回当天日报看详解。
- **月报**（每月 1 号）：按 LLM / RL / AI+生物 三个方向各写一段趋势综述，讲这个月的走向。

解决的痛点：论文太多看不过来、arXiv 上不知道哪些值得看；每天扫又容易只见树木不见森林。

## 它怎么工作

```
HF Daily Papers（带点赞）┐
                          ├─> 候选池 ─> DeepSeek 逐篇打1-5分+分组 ─> 保留≥阈值 ─> 抓全文
arXiv（cs + q-bio 分类）  ┘   (各来源分别限量)                              │
                                                                          v
  content/posts/前沿速览-日期.md  <──  按分组渲染  <──  DeepSeek 写3-4句中文摘要
```

周报和月报**不重新打分**，直接吃日报每天存下来的分数文件：

```
                          ┌─> 周报：筛≥4分 ─> 1次调用排名次+写点评 ─> 前沿周报-2026-W36.md
state/scores/日期.json ───┤
（当天全部候选的分数）     └─> 月报：筛≥4分按方向分桶 ─> 每桶1次调用写趋势 ─> 前沿月报-2026-08.md
```

月报正文里的论文链接**不让模型写**：喂给它的列表带编号，它只能写 `[12]`，代码再把 `[12]` 换成真实的标题和 arXiv 链接。模型全程碰不到 URL，物理上编不出死链。

三层选择标准，保证既不漏又精准：

1. **候选池不按赞截断**：HF 取最热的若干篇，每个 arXiv 分类各取最近若干篇，分别限量再去重。这样 0 赞但重要的生物论文不会被 LLM 高赞论文挤掉。
2. **喂硬信号**：HF 点赞数、arXiv 的 comment（常含「Accepted to NeurIPS」等中稿信息）、是否放出代码（含 github 链接），都拼进打分依据。
3. **打分 + 阈值**：DeepSeek 给每篇打 1-5 分并分组，只保留 `≥ score_threshold`（默认 3）的，数量随当天质量浮动，上限 25 篇。

跨天去重靠 `state/seen.json`，讲过的不再重复。

## 文件树

```
scripts/
├── README.md            本文件
├── requirements.txt     依赖（requests / beautifulsoup4 / openai / PyYAML）
├── config.yaml          配置：来源、兴趣、打分标准、阈值（改这里）
├── papers.py            抓论文 + 打分选题 + 抓全文
├── generate.py          日报主流程
├── weekly.py            周报：一周 Top 10
├── monthly.py           月报：按方向写趋势
└── state/
    ├── seen.json        记录处理过的论文，避免重复
    └── scores/日期.json  当天全部候选的分数，周报月报的原料
```

生成的文章分别写到 `content/posts/` 下的 `前沿速览-日期.md`、`前沿周报-2026-W36.md`、`前沿月报-2026-08.md`。

## 主要功能

- 每天自动抓取、打分、筛选前沿论文
- 按 大模型 LLM / 强化学习 RL / AI+生物 / 其他 分组
- 每篇 3-4 句中文摘要（基于全文，抓不到退回摘要）+ 原文链接
- 每篇标题下亮出 `评分 · HF赞数 · 中稿信息 · 有代码` 方便一眼判断
- 跨天去重
- 每周一出周报（全周 Top 10 + 一句话点评 + 回链当天日报）
- 每月 1 号出月报（分方向趋势综述，论文链接由代码生成不会编）
- GitHub Actions 每天凌晨自动跑并部署上线

## 运行指南

### 本地手动跑（先看产出对不对）

```bash
cd /home/huawei/wshare/blog_KISS
pip install -r scripts/requirements.txt          # 首次装依赖
export DEEPSEEK_API_KEY=你的key

python scripts/generate.py             # 日报（今天）
python scripts/weekly.py               # 周报（上一周）
python scripts/weekly.py 2026-09-03    # 周报（那天所在那一周）
python scripts/monthly.py              # 月报（上个月）
python scripts/monthly.py 2026-08      # 月报（指定月份）
```

周报月报要有 `state/scores/` 里的数据才跑得出东西，所以得先攒几天日报。

### 自动跑（GitHub Actions）

`.github/workflows/前沿速览.yml` 每天北京时间凌晨 3 点自动跑（也可在 Actions 页面手动 `Run workflow`）：生成日报 →（周一顺手出周报、1 号顺手出月报）→ 提交 → Hugo 构建 → 部署到 GitHub Pages。

周报月报是同一个 workflow 里加的两个 step，用 `date` 判断今天是不是周一 / 1 号。拆成三个 workflow 的话周一凌晨会互相抢 GitHub Pages 的部署锁。

一次性配置（已完成）：

- 仓库 Settings → Secrets 里加 `DEEPSEEK_API_KEY`
- Settings → Actions → General → Workflow permissions 选 **Read and write**

## 常改的配置（config.yaml）

- `score_threshold`：保留分数的阈值。想只看精华调到 4，想看全一点调到 3（当前 3）
- `max_papers`：一天最多收多少篇（当前 25）
- `interests`：你的兴趣，大白话写，DeepSeek 按这个打分
- `rubric`：1-5 分各代表什么，想改选择口味就改这里
- `sources.hf_min_upvotes`：HF 论文至少多少赞才进候选（当前 5）
- `sources.arxiv_categories`：抓哪些 arXiv 分类
- `sources.arxiv_max_per_cat` / `hf_max_papers`：各来源限量

周报月报的两个常数直接写在脚本头部：`weekly.py` 的 `MIN_SCORE`（进候选的最低分，默认 4）和 `TOP_N`（取几篇，默认 10）；`monthly.py` 的 `MIN_SCORE` 和 `MAX_PER_GROUP`（每个方向最多喂多少篇给模型，防止 prompt 撑爆上下文）。

## 成本

只用 DeepSeek：日报一次批量打分 + 每篇一次摘要，一天几毛钱。周报一周多一次调用、月报一月多几次调用，可以忽略。
