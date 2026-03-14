#!/usr/bin/env python3
"""
Improved pipeline:
- fetch arXiv RSS for a query
- keyword score (0-5)
- robust gemini calls for one-liner and Chinese abstract (if available)
- write simple md file to Obsidian vault with placeholders when generation fails
"""
import os, sys, subprocess, json, yaml, feedparser, time, re
from pathlib import Path
from datetime import datetime

# CONFIG
BASE_DIR = Path.home()  # adjust if running elsewhere
VAULT_PATH = Path.home() / "Obsidian" / "Research"   # change to your vault path
CONFIG_PATH = Path("config/fields.yaml")
ARXIV_FEED = "https://export.arxiv.org/rss/cs.CL"

# load fields
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

domains = cfg.get("domain", [])


def keyword_score(title, abstract, domain):
    text = (title + " " + abstract).lower()
    score = 0
    kws = domain.get("keywords", [])
    exs = domain.get("exclude_keywords", [])
    # exclude fast
    if any(ex.lower() in text for ex in exs):
        return 0
    for kw in kws:
        if kw.lower() in text:
            score += 1
    return min(score, 5)


def call_gemini_generate(prompt, expect_json=False, raw=False, timeout=40):
    """Call gemini CLI with a prompt. Return (ok, text_or_json)
    If expect_json True, try to parse JSON from stdout.
    """
    if raw:
        cmd = ["gemini", prompt]
    else:
        cmd = ["gemini", "--output-format", "json", prompt]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return False, f"gemini call exception: {e}"
    if res.returncode != 0:
        return False, res.stderr.strip() or res.stdout.strip()
    out = res.stdout.strip()
    if expect_json:
        try:
            j = json.loads(out)
            return True, j
        except Exception:
            try:
                start = out.index('{')
                j = json.loads(out[start:])
                return True, j
            except Exception:
                return True, out
    return True, out


def generate_one_liner(title, abstract):
    prompt = (
        f"Give a single-sentence English one-line summary (concise) of the paper.\n\n"
        f"Title: {title}\n\nAbstract: {abstract}\n\n"
        f"Respond with the one-line summary only."
    )
    ok, out = call_gemini_generate(prompt, expect_json=False, raw=True)
    if ok and out:
        return out.splitlines()[0].strip()
    return ""


def generate_abstract_zh(title, abstract):
    prompt = (
        f"Provide a high-quality Chinese translation of the following paper abstract.\n\n"
        f"Title: {title}\n\nAbstract: {abstract}\n\n"
        f"Respond with Chinese only."
    )
    ok, out = call_gemini_generate(prompt, expect_json=False, raw=True)
    if ok and out:
        return out.strip()
    return ""


def write_md(domain_id, meta, content):
    domain_dir = VAULT_PATH / domain_id
    domain_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r"[\\/:*?\"<>|]", "_", meta["title"])[:120]
    fname = domain_dir / f"{datetime.utcnow().strftime('%Y%m%d')}_{safe_title}.md"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(content)
    print("Wrote:", fname)


def render_paper_template(meta, abstract_zh, one_liner, auto_reason, gen_status):
    tpl = Path("templates/paper.md.tpl").read_text(encoding="utf-8")
    s = tpl.replace("{{title}}", meta["title"]) \
           .replace("{{authors}}", meta.get("authors","")) \
           .replace("{{source}}", meta.get("source","arXiv")) \
           .replace("{{date}}", meta.get("date","")) \
           .replace("{{url}}", meta.get("url","")) \
           .replace("{{has_code}}", str(meta.get("has_code", False)).lower()) \
           .replace("{{score}}", str(meta.get("score",0))) \
           .replace("{{domain_id}}", meta.get("domain_id","")) \
           .replace("{{abstract_en}}", meta.get("abstract","")) \
           .replace("{{abstract_zh}}", abstract_zh or "自动生成失败：请手动补充") \
           .replace("{{auto_reason}}", auto_reason or "")
    # append generation status and one_liner if present
    extra = "\n\n---\n\n" + f"自动生成状态: {gen_status}\n\n英文一行总结: {one_liner or 'N/A'}\n"
    return s + extra


def main():
    print("Fetching:", ARXIV_FEED)
    feed = feedparser.parse(ARXIV_FEED)
    for entry in feed.entries[:25]:
        title = entry.get("title","")
        summary = entry.get("summary","")
        link = entry.get("link","")
        authors = ", ".join([a.name for a in entry.get("authors", [])]) if entry.get("authors") else ""
        # score against domains
        best = {"score":0, "domain":None}
        for d in domains:
            s = keyword_score(title, summary, d)
            if s > best["score"]:
                best = {"score":s, "domain":d}
        if best["score"] == 0:
            continue
        meta = {
            "title": title,
            "authors": authors,
            "source": "arXiv",
            "date": entry.get("published", ""),
            "url": link,
            "has_code": False,
            "score": best["score"],
            "domain_id": best["domain"]["id"],
            "abstract": summary
        }
        gen_status = "none"
        one_liner = ""
        abstract_zh = ""
        # Only attempt generation for score >=2 to save calls
        if meta["score"] >= 2:
            one_liner = generate_one_liner(title, summary)
            abstract_zh = generate_abstract_zh(title, summary)
            gen_status = "ok" if (one_liner or abstract_zh) else "failed"
        auto_reason = f"Keyword match score {meta['score']}; matched domain {meta['domain_id']}."
        content = render_paper_template(meta, abstract_zh, one_liner, auto_reason, gen_status)
        write_md(meta["domain_id"], meta, content)
        time.sleep(1)
    # after processing, generate daily summary limited to top N per domain
    try:
        generate_daily_summary(domains)
    except Exception as e:
        print('daily summary generation failed:', e)

def generate_daily_summary(domains, top_n=10):
    # produce daily summary in requested format: domain H1, score H2, papers under
    today = datetime.utcnow().strftime('%Y-%m-%d')
    lines = []
    lines.append('# Daily Summary — ' + today + '\n')
    for d in domains:
        lines.append('# ' + d.get('name') + '\n')
        domain_dir = Path.home() / 'Obsidian' / 'Research' / d.get('id')
        if not domain_dir.exists():
            lines.append('(no papers)\n\n')
            continue
        papers_by_score = {5:[],4:[],3:[],2:[],1:[]}
        for md in sorted(domain_dir.glob('*.md')):
            txt = md.read_text(encoding='utf-8')
            m = re.search(r'score:\s*(\d)', txt)
            score = int(m.group(1)) if m else 0
            title_m = re.search(r'title:\s*"([^"]+)"', txt)
            title = title_m.group(1) if title_m else md.stem
            one_liner_m = re.search(r'英文一行总结:\s*(.+)', txt)
            one_liner = one_liner_m.group(1).strip() if one_liner_m else ''
            if score<1 or score>5:
                score=1
            papers_by_score.setdefault(score,[]).append({'title':title,'file':md.name,'one_liner':one_liner})
        for score in [5,4,3,2,1]:
            lines.append('## Score ' + str(score) + '\n')
            items = papers_by_score.get(score, [])[:top_n]
            if not items:
                lines.append('- (no papers)\n')
            else:
                for p in items:
                    if score>=3:
                        lines.append('- **' + p['title'] + '** — ' + p['one_liner'] + ' — [' + p['file'] + '](' + p['file'] + ')\n')
                    else:
                        txt = (Path.home() / 'Obsidian' / 'Research' / d.get('id') / p['file']).read_text(encoding='utf-8')
                        m2 = re.search(r'## 中文摘要\n([\s\S]*?)\n\n', txt)
                        zh = m2.group(1).strip() if m2 else ''
                        lines.append('- **' + p['title'] + '** — ' + zh[:200] + ' — [' + p['file'] + '](' + p['file'] + ')\n')
            lines.append('\n')
    summary_path = Path('daily-summaries')
    summary_path.mkdir(parents=True, exist_ok=True)
    fp = summary_path / f"daily-summary-{today}.md"
    fp.write_text('\n'.join(lines), encoding='utf-8')
    print('Wrote daily summary:', fp)

if __name__ == "__main__":
    main()
