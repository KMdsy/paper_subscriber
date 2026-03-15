# Paper Subscriber 📚

这是一个自动化的 arXiv 论文订阅与分析工具。它能够根据你的研究兴趣自动抓取、筛选、评分并深度解析最新的学术论文，最终生成结构化的看板和 markdown 笔记。

## Quick Start 🚀

### 1. 查看与更改研究兴趣
你的研究兴趣（关键词、领域、排除词）统一在配置文件中管理：
- **配置文件地址**: `config/fields.yaml`
- **操作方式**: 直接编辑该 YAML 文件。你可以添加新的领域 ID，或者在现有领域下增删关键词。

### 2. 运行论文抓取与处理
运行主脚本来获取最新论文。请确保在项目根目录下执行，并使用虚拟环境中的 Python：
```bash
# 使用虚拟环境运行抓取程序
.venv/bin/python3 scripts/fetch_and_process.py
```
*该脚本会自动跳过已处理的论文，并尝试修复之前处理失败的条目。*

### 3. 同步到 GitHub
如果你需要将生成的静态看板同步到 GitHub Pages 或远程仓库：
```bash
# 使用虚拟环境运行同步脚本
.venv/bin/python3 scripts/sync_github.py
```

---

## 自动化运行 (Scheduled Task) 🤖

为了实现每日自动追踪，我为你准备了一个集成脚本，它合并了上述的抓取与同步步骤，并包含了基础的错误处理逻辑。

### 使用方法：
```bash
# 赋予执行权限 (仅需一次)
chmod +x scripts/run_pipeline.sh

# 手动测试运行
./scripts/run_pipeline.sh
```

### 设置定时任务 (Crontab)：
你可以将其设置为每日定时运行（例如每天早上 8:30）：
```bash
# 执行 crontab -e 并添加以下行
30 8 * * * /home/dsy/projects/paper_subscriber/scripts/run_pipeline.sh >> /home/dsy/projects/paper_subscriber/pipeline.log 2>&1
```

## 项目结构 📁
- `docs/`: 包含静态看板页面 (`index.html`) 和论文数据 (`data.json`)。
- `scripts/`: 核心逻辑脚本。
- `config/`: 配置文件与抓取状态。
- `templates/`: Markdown 笔记模板。
