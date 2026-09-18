# AI Brie News Agent

AI Brie News Agent 会从 arXiv、GitHub 和主要 AI 实验室 / 技术博客采集候选内容，通过来源专项预筛选与 Final Analyzer，生成面向 AI 学生和早期研究者的高价值 Daily Brief。

它不是简单的新闻聚合器。项目优先考虑学生价值、技术深度、证据质量、可复现性和行动价值，并用轻量兴趣偏好改善相关性、用 recent-output cooldown 减少近期重复内容。

## Features

- 采集 arXiv 论文，并为预筛选后的候选补充正文证据
- 发现多个技术方向的 GitHub 项目
- 聚合主要 AI 实验室、技术博客与少量高质量媒体
- 对 arXiv、GitHub、编辑来源分别进行 source-specific prefilter
- 观测主题分布并限制最终输出的主题坍缩
- 使用个人偏好做 soft boost，而不是硬过滤
- 使用本地 cooldown history 避免近期重复推送
- 通过 DeepSeek Final Analyzer 生成结构化日报
- 输出 Today's Top 3、AI News、Papers & Blogs、GitHub / Open Source、Skills & Workflows 和 Trend Summary

## Requirements

- Python 3.11 或更高版本
- 可访问 arXiv、GitHub、RSS/网站和 DeepSeek API 的网络环境
- DeepSeek API Key（必需）
- GitHub Token（可选但推荐；未配置时会受到较低的匿名 API rate limit）

项目当前使用 DeepSeek Chat Completions API。依赖列在 `requirements.txt` 中。

## Quick Start

### Windows PowerShell

```powershell
git clone https://github.com/CamilleQAQ/ai-brie-news-agent.git
cd ai-brie-news-agent

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Copy-Item .env.example .env
Copy-Item preferences.example.json preferences.json
```

编辑 `.env`，填入自己的 `DEEPSEEK_API_KEY`。随后运行：

```powershell
python main.py
```

如果 PowerShell 禁止激活脚本，也可以不激活虚拟环境，直接运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

### Linux / macOS

```bash
git clone https://github.com/CamilleQAQ/ai-brie-news-agent.git
cd ai-brie-news-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
cp preferences.example.json preferences.json
python main.py
```

## Configuration

### `.env`

```dotenv
DEEPSEEK_API_KEY=your_deepseek_api_key_here
GITHUB_TOKEN=your_github_token_here
```

- `DEEPSEEK_API_KEY`：必需，供来源预筛选、Final Analyzer 和 Trend Summary 调用 DeepSeek。
- `GITHUB_TOKEN`：可选但推荐，供 GitHub Search API 使用。不要把真实 Token 提交到 Git。

### `preferences.json`

从 `preferences.example.json` 复制后按需修改：

```json
{
  "preferred_tracks": [
    "Reasoning & Model Architecture",
    "Efficient AI & AI Infrastructure"
  ],
  "current_focus": [
    "reasoning evaluation",
    "inference optimization"
  ]
}
```

- `preferred_tracks`：长期关注的宽技术方向。
- `current_focus`：近期正在学习或开发的具体主题。

两者都只是同等质量候选之间的 soft preference，不会覆盖客观质量判断，也不会阻止兴趣之外的高价值内容进入日报。`preferences.json` 不存在时，程序会使用空偏好并正常运行。

### Tuning Reference

共享的非敏感行为参数集中在 `settings.py`。修改前先确认参数所处阶段；增加 raw pool 只会提高召回和 API 成本，不代表最终日报会增加条目。

| 参数 | 默认值 | 阶段 | 含义 |
|---|---:|---|---|
| `ARXIV_ITEMS_PER_CATEGORY` | 10 | Collector | 每个 arXiv RSS 分类读取的 raw items 上限 |
| `GITHUB_RECENT_DAYS` | 90 天 | Collector | 新仓库候选的创建时间窗口 |
| `GITHUB_ACTIVE_DAYS` | 14 天 | Collector | 活跃仓库候选的最近 Push 窗口 |
| `GITHUB_RECENT_MIN_STARS` | 20 | Collector | 新仓库搜索的最低 Stars，仅用于控制候选池 |
| `GITHUB_ACTIVE_MIN_STARS` | 100 | Collector | 活跃仓库搜索的最低 Stars，仅用于控制候选池 |
| `EDITORIAL_LOOKBACK_DAYS` | 7 天 | Collector | 博客和媒体的回看窗口 |
| `PREFILTER_CANDIDATE_LIMIT` | 10 / 来源 | Prefilter | 每类来源进入 Final Analyzer 的最大候选数 |
| `PREFILTER_TOPIC_FAMILY_LIMIT` | 4 | Prefilter | 防止某个宽主题占满单个来源候选池 |
| `FINAL_SECTION_LIMITS` | 5 / 5 / 5 / 3 | Final | News、Papers、Open Source、Skills 的栏目上限 |
| `FINAL_SUBTOPIC_LIMIT` | 3 | Final | 同一细分主题的最终上限 |
| `FINAL_TOPIC_FAMILY_LIMIT` | 4 | Final | 同一宽主题家族的最终上限 |
| `COOLDOWN_DAYS` | arXiv 30、GitHub 7 | Cooldown | 不同来源近期重复输出的抑制时间 |
| `DEFAULT_COOLDOWN_DAYS` | 14 天 | Cooldown | 博客、媒体等其他来源的默认抑制时间 |
| `HISTORY_RETENTION_DAYS` | 60 天 | Local state | cooldown 历史的保留期限 |

`PREFILTER_MAX_TOKENS`、`FINAL_ANALYZER_MAX_TOKENS`、`TREND_MAX_TOKENS`、arXiv evidence 长度和 history 数量上限也在同一文件中。API Key 和个人偏好不属于 tuning 参数，仍分别放在 `.env` 与 `preferences.json`。

## Pipeline

```text
arXiv / GitHub / Blogs & Media Collectors
                    ↓
         Recent-output Cooldown
                    ↓
       Source-specific Prefilters
                    ↓
             Candidate Pool
                    ↓
   Final Analyzer + Soft Preferences
                    ↓
              Daily Brief
```

Cooldown 在预筛选前过滤近期已经输出过的内容，历史保存在本机 `.state/recent_outputs.json`。该文件有保留期限和数量上限，不会被提交。兴趣配置仅在最终选择时提供轻度优先级。

## Output Example

```text
========================================================================
AI BRIE NEWS AGENT · DAILY BRIEF
本期共 3 条高价值内容
========================================================================

TODAY'S TOP 3
今天最值得投入时间的内容，不代表今天刚发布
------------------------------------------------------------------------
1. 面向推理系统的可复现实验框架
栏目：Papers & Blogs
价值：学习如何把推理质量、延迟与计算预算放进同一评测设计。
建议：阅读实验设计并尝试复现一个最小对照实验。

AI NEWS
------------------------------------------------------------------------
今日暂无

PAPERS & BLOGS
------------------------------------------------------------------------
1. 面向推理系统的可复现实验框架
方向：Evaluation
为什么读：可以学习更严谨的模型与系统评测方法。

GITHUB / OPEN SOURCE
------------------------------------------------------------------------
1. 轻量推理服务工具
建议行动：先阅读核心调度模块，再用小模型做最小实验。

SKILLS & WORKFLOWS
------------------------------------------------------------------------
今日暂无

TREND SUMMARY
------------------------------------------------------------------------
1. 多个入选条目共同关注推理质量与系统成本的联合评测。
```

完整的公开示例见 `examples/sample_daily_brief.txt`。

## Project Structure

```text
ai-brie-news-agent/
├── agent/
│   ├── analyzer.py          # Final Analyzer、结构化结果与最终约束
│   ├── prefilter.py         # 三类来源的专项预筛选
│   ├── recent_outputs.py    # cooldown 历史、URL 规范化与持久化
│   ├── reporter.py          # 终端 Daily Brief 渲染
│   └── topic_observer.py    # 粗粒度主题观测
├── collectors/
│   ├── github.py            # GitHub Search API collector
│   ├── news.py              # 官方博客与媒体 collector
│   └── rss.py               # arXiv RSS 与正文证据提取
├── examples/
│   └── sample_daily_brief.txt
├── tests/                   # 不依赖私人 Token 的单元测试
├── main.py                  # Pipeline orchestration
├── settings.py              # 共享的非敏感行为参数与调参说明
├── preferences.example.json
└── requirements.txt
```

## Tests

单元测试不需要真实 API Key：

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions 会在 Python 3.11 和 3.12 的 Windows clean environment 中执行相同测试。

## Local State and Privacy

以下文件只保留在用户本机，并已通过 `.gitignore` 排除：

- `.env`：API Key 和 Token
- `preferences.json`：个人兴趣配置
- `.state/`：recent-output cooldown 历史
- 本地日志与生成的日报输出
- 虚拟环境、IDE 配置和 Python cache

程序不会要求使用项目作者的 Token、偏好或历史记录。首次运行没有 `.state` 文件时，会从空历史开始并自动创建本地状态。

## Limitations

- 外部 API、RSS 或网页不可用时，当天可能缺少部分来源。
- arXiv 内容可能尚未经过同行评审；正文证据仍属于作者自述。
- LLM 筛选和归纳不等价于人工同行评审，也可能出现遗漏或判断错误。
- GitHub README、论文和博客中的性能 claim 不代表经过独立验证。
- topic family 主要用于启发式观测和多样性控制，不是严格学科分类。
- v0.1.0 是命令行版本，暂不包含桌面通知、自动调度或桌宠 UI。

## Disclaimer

本项目用于技术信息整理与学习辅助，不构成对任何论文、项目、模型或商业声明的独立验证。使用者应阅读原始来源，并自行核实 README、论文和博客中的作者 claim。

## License

本项目代码采用 [MIT License](LICENSE)。第三方内容及链接仍归各自权利人所有。
