# 前沿速览：每日论文简报

每天自动从 arXiv 和 HuggingFace Daily Papers 里挑出 AI / LLM / 强化学习 / 计算生物学方向**值得看的**论文，用 DeepSeek 打分筛选、写成中文摘要，生成一篇博客文章。你早上打开博客就能扫全局，感兴趣的点标题看原文。

解决的痛点：论文太多看不过来、arXiv 上不知道哪些值得看。

## 它怎么工作

```
HF Daily Papers（带点赞）┐
                          ├─> 候选池 ─> DeepSeek 逐篇打1-5分+分组 ─> 保留≥阈值 ─> 抓全文
arXiv（cs + q-bio 分类）  ┘   (各来源分别限量)                              │
                                                                          v
  content/posts/前沿速览-日期.md  <──  按分组渲染  <──  DeepSeek 写3-4句中文摘要
```

三层选择标准，保证既不漏又精准：

1. **候选池不按赞截断**：HF 取最热的若干篇，每个 arXiv 分类各取最近若干篇，分别限量再去重。这样 0 赞但重要的生物论文不会被 LLM 高赞论文挤掉。
2. **喂硬信号**：HF 点赞数、arXiv 的 comment（常含「Accepted to NeurIPS」等中稿信息）、是否放出代码（含 github 链接），都拼进打分依据。
3. **打分 + 阈值**：DeepSeek 给每篇打 1-5 分并分组，只保留 `≥ score_threshold`（默认 3）的，数量随当天质量浮动，上限 25 篇。

跨天去重靠 `state/seen.json`，讲过的不再重复。

## 文件树

```
scripts/
├── README.md          本文件
├── requirements.txt   依赖（requests / beautifulsoup4 / openai / PyYAML）
├── config.yaml        配置：来源、兴趣、打分标准、阈值（改这里）
├── papers.py          抓论文 + 打分选题 + 抓全文
├── generate.py        主流程，跑这个
└── state/seen.json    记录处理过的论文，避免重复
```

生成的文章写到仓库的 `content/posts/前沿速览-日期.md`。

## 主要功能

- 每天自动抓取、打分、筛选前沿论文
- 按 大模型 LLM / 强化学习 RL / AI+生物 / 其他 分组
- 每篇 3-4 句中文摘要（基于全文，抓不到退回摘要）+ 原文链接
- 每篇标题下亮出 `评分 · HF赞数 · 中稿信息 · 有代码` 方便一眼判断
- 跨天去重
- GitHub Actions 每天凌晨自动跑并部署上线

## 运行指南

### 本地手动跑（先看产出对不对）

```bash
cd /home/huawei/wshare/blog_KISS
pip install -r scripts/requirements.txt          # 首次装依赖
DEEPSEEK_API_KEY=你的key python scripts/generate.py
```

跑完看 `content/posts/前沿速览-<今天>.md`。

### 自动跑（GitHub Actions）

`.github/workflows/前沿速览.yml` 每天北京时间凌晨 3 点自动跑（也可在 Actions 页面手动 `Run workflow`）：生成文章 → 提交 → Hugo 构建 → 部署到 GitHub Pages。

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

## 成本

只用 DeepSeek：一次批量打分 + 每篇一次摘要，一天几毛钱。
