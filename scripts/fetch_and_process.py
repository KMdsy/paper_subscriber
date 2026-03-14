#!/usr/bin/env python3
"""
Advanced paper subscriber pipeline (v3):
- Two-pass scoring (Heuristic -> Gemini Refined)
- Differential templates (Deep-dive, Quick-read, Base)
- Gemini-powered structural analysis and translation
"""
import os, sys, subprocess, json, yaml, feedparser, time, re
from pathlib import Path
from datetime import datetime

# CONFIG
CONFIG_PATH = Path("config/fields.yaml")
WHITELIST_PATH = Path("config/whitelist.yaml")
VAULT_PATH = Path.home() / "Obsidian" / "Research"

def load_yaml(path):
    if not path.exists(): return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

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
    if any(ex.lower() in text for ex in exs): return 0
    matches = sum(1 for kw in kws if kw.lower() in text)
    return min(matches, 5)

def call_gemini_json(prompt):
    cmd = ["gemini", "--output-format", "json", prompt]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode != 0: return None
        full_out = json.loads(res.stdout.strip())
        inner_text = full_out.get("response", "")
        match = re.search(r'\{.*\}', inner_text, re.DOTALL)
        return json.loads(match.group(0)) if match else None
    except: return None

def call_gemini_text(prompt):
    cmd = ["gemini", prompt]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return res.stdout.strip() if res.returncode == 0 else ""
    except: return ""

def gemini_refine_score(title, abstract, domains_context):
    prompt = f"Expert research assistant. Rate this paper 1-5 (or 0) based on context: {domains_context}. Rules: 5=High rel+quality, 4=High rel, 3=Mid rel, 2=Irrel but high heat/lab, 1=Irrel, 0=Trash.\nPaper: {title}\nAbstract: {abstract}\nReturn JSON: {{'score': int, 'reason': 'string'}}"
    res = call_gemini_json(prompt)
    if res and "score" in res: return res
    return {"score": 1, "reason": "parsing error fallback"}

def generate_deep_dive(title, abstract):
    prompt = f"Structured review (Deep Dive) for researcher. Title: {title}. Abstract: {abstract}. Return JSON: method_highlights, experiment_highlights, pros, cons, reproducibility, task_list."
    return call_gemini_json(prompt)

def generate_quick_read(title, abstract):
    prompt = f"Quick summary for paper. Title: {title}. Abstract: {abstract}. Return JSON: core_contribution, app_value_score (1-10)."
    return call_gemini_json(prompt)

def generate_abstract_zh(title, abstract):
    prompt = f"Translate to Chinese: Title: {title}. Abstract: {abstract}."
    return call_gemini_text(prompt)

def render_paper(meta, score_data, abstract_zh):
    score = meta["score"]
    
    def to_str(val):
        if isinstance(val, list): return "\n".join([f"- {i}" for i in val])
        return str(val)

    if score == 5:
        tpl_path = Path("templates/deep_dive.md.tpl")
        tpl = tpl_path.read_text(encoding="utf-8")
        s = tpl.replace("{{method_highlights}}", to_str(score_data.get("method_highlights", ""))) \
               .replace("{{experiment_highlights}}", to_str(score_data.get("experiment_highlights", ""))) \
               .replace("{{pros}}", to_str(score_data.get("pros", ""))) \
               .replace("{{cons}}", to_str(score_data.get("cons", ""))) \
               .replace("{{reproducibility}}", to_str(score_data.get("reproducibility", ""))) \
               .replace("{{task_list}}", to_str(score_data.get("task_list", "")))
    elif score in [3, 4]:
        tpl_path = Path("templates/quick_read.md.tpl")
        tpl = tpl_path.read_text(encoding="utf-8")
        s = tpl.replace("{{core_contribution}}", to_str(score_data.get("core_contribution", ""))) \
               .replace("{{app_value_score}}", str(score_data.get("app_value_score", 0)))
    else:
        tpl_path = Path("templates/base.md.tpl")
        tpl = tpl_path.read_text(encoding="utf-8")
        s = tpl.replace("{{abstract_en}}", meta["abstract"])
    
    s = s.replace("{{title}}", meta["title"]) \
         .replace("{{authors}}", meta["authors"]) \
         .replace("{{source}}", meta["source"]) \
         .replace("{{date}}", meta["date"]) \
         .replace("{{url}}", meta["url"]) \
         .replace("{{has_code}}", str(meta["has_code"])) \
         .replace("{{score}}", str(score)) \
         .replace("{{domain_id}}", meta["domain_id"]) \
         .replace("{{reason}}", meta["reason"]) \
         .replace("{{abstract_zh}}", abstract_zh or "Translation Failed")
    return s

def process_paper(p, domains_context):
    print(f"Refining: {p['title']}...")
    ref = gemini_refine_score(p["title"], p["abstract"], domains_context)
    p["score"] = ref.get("score", 1)
    p["reason"] = ref.get("reason", "N/A")
    if p["score"] == 0: return None
    
    print(f"Final Score: {p['score']} | Processing content...")
    abstract_zh = generate_abstract_zh(p["title"], p["abstract"])
    p["abstract_zh"] = abstract_zh # 保存到 JSON
    
    score_data = {}
    if p["score"] == 5:
        score_data = generate_deep_dive(p["title"], p["abstract"]) or {}
    elif p["score"] in [3, 4]:
        score_data = generate_quick_read(p["title"], p["abstract"]) or {}
    
    p["score_data"] = score_data # 保存到 JSON
        
    content = render_paper(p, score_data, abstract_zh)
    domain_dir = VAULT_PATH / p["domain_id"]
    domain_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r"[\\/:*?\"<>|]", "_", p["title"])[:100]
    fname = domain_dir / f"{datetime.utcnow().strftime('%Y%m%d')}_{safe_title}.md"
    fname.write_text(content, encoding="utf-8")
    return p

def save_to_json(papers):
    json_path = Path("docs/data.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    existing_data = []
    if json_path.exists():
        try: existing_data = json.loads(json_path.read_text(encoding="utf-8"))
        except: pass
    seen_urls = {p["url"] for p in papers}
    new_data = [p for p in existing_data if p["url"] not in seen_urls]
    new_data.extend(papers)
    new_data = sorted(new_data, key=lambda x: x["date"], reverse=True)[:200]
    json_path.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    domains_context = "\n".join([f"- {d['name']}: {', '.join(d['keywords'])}" for d in domains])
    all_raw = []
    for src in sources:
        print(f"Fetching {src['name']}...")
        feed = feedparser.parse(src["url"])
        for entry in feed.entries[:10]:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            authors = ", ".join([a.name for a in entry.get("authors", [])]) if entry.get("authors") else ""
            
            best_domain = {"score": 0, "id": "general"}
            for d in domains:
                s = keyword_score(title, summary, d)
                if s > best_domain["score"]:
                    best_domain = {"score": s, "id": d["id"]}
            
            # Initial filter: only papers with ANY keyword match or pref source
            is_pref = is_preferred_source(authors, summary)
            if best_domain["score"] == 0 and not is_pref: continue

            all_raw.append({
                "title": title, "authors": authors, "source": src["name"],
                "date": entry.get("published", datetime.utcnow().strftime("%Y-%m-%d")),
                "url": entry.get("link", ""), "has_code": "code" in summary.lower(),
                "score": 1, "domain_id": best_domain["id"],
                "abstract": summary, "reason": ""
            })
    
    seen = set()
    final_list = []
    for p in all_raw:
        if p["url"] in seen: continue
        seen.add(p["url"])
        res = process_paper(p, domains_context)
        if res: final_list.append(res)
        time.sleep(1)
    
    if final_list: save_to_json(final_list)

if __name__ == "__main__":
    main()
