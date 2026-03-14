#!/usr/bin/env python3
"""
Advanced paper subscriber pipeline (v3):
- Two-pass scoring (Heuristic -> LLM Refined)
- Differential templates (Deep-dive, Quick-read, Base, Plain(no translation))
- LLM-powered structural analysis and translation
"""
import os, sys, subprocess, json, yaml, feedparser, time, re, calendar, uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from tqdm import tqdm
from utils import OpenRouterClient

# Initialize OpenRouter Client
or_client = OpenRouterClient()


# CONFIG
CONFIG_PATH = Path("config/fields.yaml")
WHITELIST_PATH = Path("config/whitelist.yaml")
STATE_PATH = Path("config/state.json")
VAULT_PATH = Path.home() / "Obsidian" / "content" / "Research"
UTC8 = timezone(timedelta(hours=8))

def load_yaml(path):
    if not path.exists(): return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_state():
    if not STATE_PATH.exists():
        # Default to 24 hours ago if no state exists
        default_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        return {"last_update_time": default_time}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except:
        return {"last_update_time": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}

def save_state(last_update_time_iso):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"last_update_time": last_update_time_iso}, ensure_ascii=False, indent=2), encoding="utf-8")

def struct_time_to_datetime(st):
    return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)

cfg = load_yaml(CONFIG_PATH)
whitelist = load_yaml(WHITELIST_PATH)
domains = cfg.get("domain", [])
sources = cfg.get("global_settings", {}).get("sources", [])
pref_insts = whitelist.get("preferred_institutions", [])
pref_authors = whitelist.get("preferred_authors", [])

def is_preferred_source(authors_str, summary):
    text = (authors_str + " " + summary).lower()
    found_insts = [inst for inst in pref_insts if inst.lower() in text]
    found_authors = [auth for auth in pref_authors if auth.lower() in authors_str.lower()]
    return len(found_insts) > 0 or len(found_authors) > 0

def keyword_score(title, abstract, domain):
    text = (title + " " + abstract).lower()
    kws = domain.get("keywords", [])
    exs = domain.get("exclude_keywords", [])
    if any(ex.lower() in text for ex in exs): return 0 # 排除词命中直接 0 分
    matches = sum(1 for kw in kws if kw.lower() in text)
    return min(matches, 5) # 最多 5 分

def llm_refine_score(title, abstract, domains_context):
    prompt = f'''你是你为研究助理。我会给你我的研究方向，请你为我给出的一篇论文及其摘要打个分数。并将该论文赋予一个领域标签（domain_id），如果我提供的列表中没有恰当的标签，请标注为 "general"。

# 评分标准
分值范围：1-5 (or 0) 
- 5分：和我的研究方向高度相关且论文质量优秀，值得深入分析和总结，值得精读文章
- 4分：和我的研究方向高度相关，论文质量较好，值得阅读全文，但不需要特别深入分析
- 3分：和我的研究方向中等相关，论文质量一般，可以快速浏览摘要
- 2分：和我的研究方向相关性低，但有一定价值
- 1分：和我的研究方向相关性很低，价值有限
- 0分：无价值，垃圾文章

# 我的研究方向
{domains_context}

# 论文内容
## 题目
{title}

## 摘要
{abstract}

# 输出格式
请输出 ** JSON 格式** 的结果 (**Please output in JSON format**)
```json
{{"score": int, "reason": "string", "domain_id": "string"}}
```
'''
    res = or_client.call_json(prompt)
    if res and "score" in res and "domain_id" in res: return res
    return {"score": 1, "reason": "parsing error fallback", "domain_id": "general", "error": res.get("error", "unknown error")}

def generate_deep_dive(title, abstract):
    prompt = f'''请作为一名资深科研助手，对下述论文进行深度解析（Deep Dive）。

# 论文信息
## 题目
{title}

## 摘要
{abstract}

# 任务要求
请分析论文的核心贡献，并按以下结构输出 **JSON 格式**：
1. **abstract_zh**: 将英文摘要翻译成中文，要求准确传达原文信息，同时语言流畅自然（String）。
2. **method_highlights**: 重点介绍方法论创新点，不仅是步骤，还要说明其巧妙之处（List of strings）。
3. **experiment_highlights**: 实验结果的关键发现、数据集对比情况以及显著性结论（List of strings）。
4. **pros**: 该论文的核心优势、独到见解或性能突破（List of strings）。
5. **cons**: 实验局限性、方法缺陷或尚未解决的边界情况（List of strings）。
6. **reproducibility**: 评估该研究的可复现性（如是否提供代码、参数描述是否详尽、实验设置是否清晰）（String）。
7. **task_list**: 建议的研究行动清单（如：阅读某篇参考文献、尝试复现某模块、将该方法应用到特定场景等）（List of strings）。

# 输出限制
- 必须使用中文回答。
- 仅返回 JSON 本身，不要包含任何 Markdown 代码块标签或其他解释文字。
'''
    return or_client.call_json(prompt)

def generate_quick_read(title, abstract):
    prompt = f'''请对下述论文进行快速摘要（Quick Summary），并翻译摘要为**中文**。

# 论文信息
## 题目
{title}

## 摘要
{abstract}

# 任务要求
请分析论文并按以下结构输出 **JSON 格式**：
1. **abstract_zh**: 将英文摘要翻译成中文，要求准确传达原文信息，同时语言流畅自然（String）。
2. **core_contribution**: 用一句话高度概括该论文解决的核心问题及提出的主要方法（String）。
3. **app_value_score**: 评估该研究在实际应用或科研落地中的价值，打分范围 1-5（Integer）。5 分表示该研究具有极高的应用潜力，1 分表示应用价值较低。


# 输出限制
- 必须使用中文回答。
- 仅返回 JSON 本身，不要包含任何 Markdown 代码块标签或其他解释文字。
'''
    return or_client.call_json(prompt)

def generate_abstract_zh(title, abstract):
    prompt = f'''请将以下论文摘要翻译成**中文**，要求准确传达原文信息，同时语言流畅自然。   

# 论文信息
## 题目
{title}

## 摘要
{abstract}

# 输出限制
必须使用中文回答，仅返回 JSON 本身，不要包含任何 Markdown 代码块标签或其他解释文字。：
```json
{{"abstract_zh": "string"}}
```
'''
    return or_client.call_json(prompt)

def render_paper(meta, last_update_time_dt):
    score = meta["score"]
    abstract_zh = meta.get('abstract_zh', 'N/A')
    
    def to_str(val):
        if isinstance(val, list): return "\n".join([f"- {i}" for i in val])
        return str(val)

    if score in [5, 4]:
        tpl_path = Path("templates/deep_dive.md.tpl")
        tpl = tpl_path.read_text(encoding="utf-8")
        s = tpl.replace("{{method_highlights}}", to_str(meta.get("method_highlights", ""))) \
               .replace("{{experiment_highlights}}", to_str(meta.get("experiment_highlights", ""))) \
               .replace("{{pros}}", to_str(meta.get("pros", ""))) \
               .replace("{{cons}}", to_str(meta.get("cons", ""))) \
               .replace("{{reproducibility}}", to_str(meta.get("reproducibility", ""))) \
               .replace("{{task_list}}", to_str(meta.get("task_list", ""))) \
               .replace("{{abstract_zh}}", abstract_zh or "Translation Failed") \
               .replace("{{abstract}}", meta["abstract"])
    elif score in [3]:
        tpl_path = Path("templates/quick_read.md.tpl")
        tpl = tpl_path.read_text(encoding="utf-8")
        s = tpl.replace("{{core_contribution}}", to_str(meta.get("core_contribution", ""))) \
               .replace("{{app_value_score}}", str(meta.get("app_value_score", 0))) \
               .replace("{{abstract_zh}}", abstract_zh or "Translation Failed") \
               .replace("{{abstract}}", meta["abstract"])
    elif score in [2]:
        tpl_path = Path("templates/base.md.tpl")
        tpl = tpl_path.read_text(encoding="utf-8")
        s = tpl.replace("{{abstract_zh}}", abstract_zh or "Translation Failed") \
               .replace("{{abstract}}", meta["abstract"])
    else:
        tpl_path = Path("templates/plain.md.tpl")
        tpl = tpl_path.read_text(encoding="utf-8")
        s = tpl.replace("{{abstract}}", meta["abstract"])

    
    s = s.replace("{{title}}", meta["title"]) \
         .replace("{{authors}}", meta["authors"]) \
         .replace("{{source}}", meta["source"]) \
         .replace("{{date}}", meta["date"]) \
         .replace("{{url}}", meta["url"]) \
         .replace("{{has_code}}", str(meta["has_code"])) \
         .replace("{{score}}", str(score)) \
         .replace("{{domain_id}}", meta.get("domain_id", "general")) \
         .replace("{{reason}}", meta.get("reason", "N/A")) 

    s = s.replace("{{last_update_time}}", last_update_time_dt.astimezone(UTC8).strftime("%Y-%m-%d %H:%M:%S"))
    return s

def process_paper(p, domains_context, last_update_time_dt):
    print(f"Refining: {p['title']}...")
    ref = llm_refine_score(p["title"], p["abstract"], domains_context) # 调用 LLM 进行评分细化
    p["score"] = ref.get("score", 1)
    p["reason"] = ref.get("reason", "N/A")
    p["domain_id"] = ref.get("domain_id", "general")
    if 'error' in ref:
        print(f"⚠️ LLM refinement error for paper '{p['title']}': {ref['error']}")
        p['error'] = ref['error'] # 将错误信息保存在 paper 数据中，方便后续分析
    if p["score"] == 0: return None
    
    score_data = {}
    if p["score"] in [5, 4]:
        print(f"Final Score: {p['score']} | Processing content...")
        score_data = generate_deep_dive(p["title"], p["abstract"]) or {}
    elif p["score"] in [3]:
        print(f"Final Score: {p['score']} | Processing content...")
        score_data = generate_quick_read(p["title"], p["abstract"]) or {}
    elif p["score"] in [2]:
        print(f"Final Score: {p['score']} | Processing content...")
        score_data = generate_abstract_zh(p["title"], p["abstract"]) or {}
    else:
        print(f"Final Score: {p['score']} | Skip processing content.")

    # 保存到 JSON
    for k in score_data.keys():
        p[k] = score_data[k] # 将深度解析的内容覆盖之前的字段，方便后续使用，包含 abstract_zh、abstract 和其他细化信息
        
    content = render_paper(p, last_update_time_dt)
    domain_dir = VAULT_PATH / p["domain_id"]
    domain_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r"[\\/:*?\"<>|]", "_", p["url"].split("/")[-1])
    safe_title += '_' + re.sub(r"[\\/:*?\"<>|]", "_", p["title"])[:100]
    fname = domain_dir / f"{datetime.now(UTC8).strftime('%Y%m%d')}_{safe_title}.md"
    fname.write_text(content, encoding="utf-8")
    return p

def save_to_json(papers):
    """
    保存论文数据到 JSON 文件
    Args:
        papers: 要保存的论文列表
        is_incremental: 是否为增量保存（默认 False 为全量保存）
    """
    json_path = Path("docs/data.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    new_data = sorted(papers, key=lambda x: x["date"], reverse=True)
    
    # 写入文件
    json_path.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"Full save completed: {len(new_data)} total papers")

def main():
    domains_context = "Domain with keywords:\n" + "\n".join([f"- {d['name']} (domain_id: {d['id']}): {', '.join(d['keywords'])}" for d in domains])
    all_raw = []
    
    # 加载持久化状态
    state = load_state()
    last_update_time_dt = datetime.fromisoformat(state["last_update_time"])
    print(f"Last update time: {last_update_time_dt.astimezone(UTC8).strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)")

    # 获取已有数据用于查重和补全检查
    json_path = Path("docs/data.json")
    
    # 导出领域映射供前端使用
    domain_map = {d['id']: d['name'] for d in domains}
    domain_map['general'] = 'General Research'
    domains_json_path = Path("docs/domains.json")
    domains_json_path.write_text(json.dumps(domain_map, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Domain mapping exported to {domains_json_path}")

    existing_papers = []
    if json_path.exists():
        try:
            backup_path = json_path.parent / f"data_{datetime.now(UTC8).strftime('%Y-%m-%d_%H-%M-%S')}.backup.json"
            backup_path.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Backup created: {backup_path.name}")
            existing_papers = json.loads(json_path.read_text(encoding="utf-8"))
        except: pass
    
    existing_urls = {p["url"]: p for p in existing_papers}

    new_last_update_time_dt = datetime.now(timezone.utc)
    
    for src in sources:
        print(f"Fetching {src['name']}...")
        feed = feedparser.parse(src["url"])
        for entry in feed.entries:  
            url = entry.get("link", "")
            
            # 时间过滤：只保留大于最近更新时间的文章
            published_parsed = entry.get("published_parsed")
            if not published_parsed: continue
            pub_dt = struct_time_to_datetime(published_parsed)
            
            if pub_dt <= last_update_time_dt:
                continue

            # 如果 URL 已存在且已经有中文摘要，则跳过抓取
            if url in existing_urls and "abstract_zh" in existing_urls[url] and existing_urls[url]["abstract_zh"]:
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", "")
            authors = ", ".join([a.name for a in entry.get("authors", [])]) if entry.get("authors") else ""
            
            best_domain = {"score": 0, "id": "general"}
            for d in domains:
                s = keyword_score(title, summary, d) # 关键词匹配的初步评分
                if s > best_domain["score"]:
                    best_domain = {"score": s, "id": d["id"]}
            
            is_pref = is_preferred_source(authors, summary)
            if best_domain["score"] == 0 and not is_pref: continue

            all_raw.append({
                "title": title, "authors": authors, "source": src["name"],
                "date": pub_dt.astimezone(UTC8).strftime("%Y-%m-%d %H:%M:%S"),
                "url": url, "has_code": "code" in summary.lower(),
                "score": 1, "domain_id": best_domain["id"], # 至少是相关领域，所以初始分 1 分
                "abstract": summary, "reason": ""
            })
    
    if not all_raw:
        print("No new papers found.")
        return

    print('=='*20)
    print(f"\nTotal new papers to process: {len(all_raw)}\n")
    print('=='*20)

    # 处理新论文
    processed_list = []
    for i, p in enumerate(tqdm(all_raw, desc="Processing papers")):
        try:
            res = process_paper(p, domains_context, new_last_update_time_dt)
            if res: 
                processed_list.append(res)
                # 每处理一篇论文就保存一次，避免崩溃丢失数据
                save_to_json(processed_list)
                print(f"✅ Paper {i+1}/{len(all_raw)} saved: {p['title'][:50]}...")
        except Exception as e:
            print(f"❌ Failed to process paper {i+1}: {p['title'][:50]}... Error: {str(e)}")
            continue
        time.sleep(1) # 1s 避免过快调用 LLM 导致失败
    
    # 最终保存（实际上已经在循环中保存了，这里是确保）
    save_to_json(processed_list)  # 全量保存，创建备份
    
    # 更新并持久化最近更新时间
    save_state(new_last_update_time_dt.isoformat())
    print(f"State updated: last_update_time = {new_last_update_time_dt.astimezone(UTC8).strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)")

if __name__ == "__main__":
    main()
