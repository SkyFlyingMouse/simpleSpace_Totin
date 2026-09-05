# simpleSpace

一个小小的个人博客。Hugo + PaperMod 主题，部署在 GitHub Pages 上：<https://skyflyingmouse.github.io/simpleSpace_Totin/>

除了手写的入门科普文章，博客的主体是一套自动生成的论文简报：每天从 arXiv 和 HuggingFace 抓前沿论文，用 DeepSeek 打分筛选、写中文解读，再按周、按月汇总。

## 文件树

```
blog_KISS/
├── hugo.toml           Hugo 配置（站点信息、菜单、搜索）
├── content/
│   ├── posts/          文章：手写科普 + 自动生成的日报/周报/月报
│   ├── about.md        关于
│   ├── archives.md     归档
│   └── search.md       搜索
├── layouts/            自定义模板
├── assets/css/         自定义样式
├── themes/PaperMod/    主题（git submodule）
├── scripts/            论文简报生成器（详见 scripts/README.md）
└── .github/workflows/
    ├── 前沿速览.yml     每天凌晨生成简报 + 构建部署
    └── deploy.yml      手动改文章后的构建部署
```

## 主要功能

- **前沿速览（日报）**：每天精选 AI / LLM / RL / 计算生物学论文，每篇 3 段中文深度解读
- **前沿周报**：每周一出，一周里最值得读的 Top 10，一句话点评 + 回链当天日报
- **前沿月报**：每月 1 号出，按方向讲这个月的研究走向
- **入门科普**：手写的 AI、大模型、计算生物学入门文章
- 标签、归档、全站搜索、深浅色自动切换

## 快速开始

```bash
git clone --recursive <仓库地址>       # 主题是 submodule，别漏了 --recursive
cd blog_KISS
hugo server -D                        # 本地预览 http://localhost:1313
```

写新文章：在 `content/posts/` 下建 md 文件，照着 `content/posts/文章模板/index.md` 的格式写就行。推到 main 分支会自动构建部署。

自动简报怎么跑、怎么改口味，看 [scripts/README.md](scripts/README.md)。
