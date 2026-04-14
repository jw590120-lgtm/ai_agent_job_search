# 🤖 AI-Native 求职助手 (Agentic Job Search System)

## 🎯 项目简介
本项目是一个基于 Agentic AI 架构的自动化求职助手，旨在替代传统静态爬虫，通过“感知-思考-行动”的自主循环，完成 AI Engineer（校招/实习）岗位的高精度收集、语义筛选与结构化输出。本项目不仅包含了底层核心 Agent 的实现，还提供了一个轻量级的 Streamlit 可视化数据大屏。

**核心交付物：**
- 自动化运行的 Agent 引擎 (`main.py`, `agent.py`)
- 高质量的结构化岗位数据 (`ai_jobs.csv`, `ai_jobs.json`)
- 动态数据可视化看板 (`app.py`)

---

## 🧠 核心架构设计：双引擎驱动

系统摒弃了传统爬虫易受 DOM 结构变化影响的弱点，采用 **LLM 大脑 + Search API** 的双引擎组合：

1. **感知器官 (Perception - Tavily API)：** - 接入专为 AI 设计的通用搜索引擎，突破单一招聘网站的结构与反爬限制，实现跨平台（牛客、BOSS直聘、企业官网等）的数据聚合。
2. **中枢大脑 (Cognition - DeepSeek-V2.5)：** - 承担双重职责：
     - **任务规划与重试：** 根据当前收集进度和历史状态，动态规划全新的搜索 Query（例如从“AI工程师实习”自动演进为“NLP 算法 校招”）。
     - **高精度语义清洗：** 接收杂乱的网页文本，利用大模型极强的上下文理解能力，精准剔除社招、非 AI 方向（如普通后端）的干扰数据，并结构化输出 8 大核心字段。

---

## 💡 Agent 核心能力与工程化亮点

### 1. 动态自我修正与任务迭代
- 系统维护了一个状态池（当前有效岗位数、已使用关键词列表）。
- 当单轮获取的有效数据不足或被完全过滤时，Agent 不会报错崩溃，而是自主复盘，生成未被使用过的全新关键词继续探索，展现了真实 Agent 的“韧性”。

### 2. 防御性编程与健壮性 (Robustness)
- **Token 爆炸截断：** 为防止冗长网页撑爆大模型上下文窗口并导致单轮耗时过长，在 Tools 层对传入 LLM 的文本实施了严格的截断（`MAX_LLM_INPUT_LENGTH`）与清洗。
- **异常熔断机制：** 实现了细粒度的异常捕获。针对 API 的 401 鉴权错误，直接实施 `RuntimeError` 熔断，防止陷入无意义的循环重试烧毁额度；针对网络超时，设置了 `LLM_TIMEOUT_SECONDS`。
- **严格的数据去重：** 采用优先校验 `job_url`，回退校验 `company + title` 的双重去重策略，确保落库数据 100% 独立。

### 3. 从单体到批处理 (Batch Processing)
- 优化了 Agent 的 Tool 编排，将“单条抽取”升级为“批量数组抽取（Array Extraction）”，单轮 API 交互可并发处理多个搜索 Snippet，大幅降低了系统的 I/O 延迟。

---

## 📊 Vibe Coding 实践与项目复盘

在本次开发中，我深度采用了 **Vibe Coding** 的人机协作模式，专注于**系统设计与瓶颈排查**。

**关于最终收集数量（40/50 条）的工程思考：**
在系统运行至第 20 轮迭代时，触发了 `MAX_ITERATIONS` 安全阀门，最终平滑退出并落库 40 条数据。这并非 Bug，而是基于**“质量优于数量”**的策略设计：
1. **语义门槛极高：** 系统宁愿舍弃边缘数据，也坚决剔除“标题写着 AI 但实际是 Java CRUD”的伪岗位。
2. **边界感控制：** 在真实的云端运行环境中，限制最大迭代次数（20次）是防止无限消耗 Token 的必要安全底线。
3. **未来优化：** 若要在生产环境中扩大召回率，我会引入多线程异步并发（Asyncio）以提升吞吐量，并为 Agent 挂载特定招聘网站的垂直 Search Tools。

---

## 🚀 快速启动指南

### 1. 环境准备
```bash
# 建议在虚拟环境中运行
pip install -r requirements.txt
```

### 2. 配置环境变量
复制 `.env.example` 文件并重命名为 `.env`，填入你的 API 密钥：
```env
OPENAI_API_KEY=你的硅基流动_API_KEY
LLM_BASE_URL=[https://api.siliconflow.cn/v1](https://api.siliconflow.cn/v1)
MODEL_NAME=deepseek-ai/DeepSeek-V2.5
TAVILY_API_KEY=你的Tavily_API_KEY
```

### 3. 运行 Agent 数据抓取引擎
```bash
python main.py
# 运行结束后，会在当前目录生成 ai_jobs.csv 和 ai_jobs.json
```

### 4. 启动 Streamlit 可视化数据大屏
```bash
streamlit run app.py
# 浏览器将自动打开交互式看板，支持动态筛选与技术栈趋势查看
```

---
*Created with Engineering Thinking & AI Collaboration.*
