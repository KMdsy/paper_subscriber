#!/usr/bin/env python3
"""
Domain management script:
- Add a domain inferred from a research topic (using Gemini)
- Add a domain manually
- Remove a domain by ID
"""
import sys, yaml, json, subprocess, argparse, re
from pathlib import Path

CONFIG_PATH = Path("config/fields.yaml")

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

def call_gemini_json(prompt):
    cmd = ["gemini", "--output-format", "json", prompt]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        if res.returncode != 0:
            print(f"Gemini error: {res.stderr}")
            return None
        full_out = json.loads(res.stdout.strip())
        inner_text = full_out.get("response", "")
        # Extract JSON from inner markdown or text
        match = re.search(r'\{.*\}', inner_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return None
    except Exception as e:
        print(f"Gemini call failed: {e}")
        return None

def add_topic_inferred(topic):
    cfg = load_config()
    prompt = f"""
    I have a new research topic: "{topic}". 
    Please infer a research domain definition for my monitoring system.
    Return ONLY a JSON object with these EXACT fields:
    - "id": a unique string ID (kebab-case, e.g., "llm-reasoning")
    - "name": a concise display name (e.g., "LLM Reasoning")
    - "keywords": a list of 5-10 specific technical keywords or phrases
    - "exclude_keywords": a list of keywords to filter out irrelevant papers
    - "priority": "high"

    Example: {{"id": "test", "name": "Test", "keywords": ["k1"], "exclude_keywords": [], "priority": "high"}}
    """
    print(f"Inferring domain for topic: '{topic}' via Gemini...")
    domain_data = call_gemini_json(prompt)
    if not domain_data or not isinstance(domain_data, dict):
        print("Failed to infer domain data (not a dictionary).")
        return

    # Normalize keys (sometimes Gemini might capitalize or vary them)
    domain_data = {k.lower(): v for k, v in domain_data.items()}
    
    required_fields = ["id", "name", "keywords"]
    if not all(k in domain_data for k in required_fields):
        print(f"Missing required fields in Gemini response: {domain_data}")
        return

    # Check for duplicate ID
    existing_ids = [d["id"] for d in cfg.get("domain", [])]
    if domain_data["id"] in existing_ids:
        domain_data["id"] += f"-{len(existing_ids)}"

    cfg.setdefault("domain", []).append(domain_data)
    save_config(cfg)
    print(f"Successfully added domain: {domain_data['name']} (ID: {domain_data['id']})")

def add_domain_manual(domain_id, name, keywords, exclude):
    cfg = load_config()
    domain_data = {
        "id": domain_id,
        "name": name,
        "priority": "high",
        "keywords": [k.strip() for k in keywords.split(",")],
        "exclude_keywords": [e.strip() for e in exclude.split(",")] if exclude else []
    }
    cfg.setdefault("domain", []).append(domain_data)
    save_config(cfg)
    print(f"Successfully added domain: {name}")

def remove_domain(domain_id):
    cfg = load_config()
    domains = cfg.get("domain", [])
    new_domains = [d for d in domains if d["id"] != domain_id]
    if len(domains) == len(new_domains):
        print(f"Domain ID '{domain_id}' not found.")
    else:
        cfg["domain"] = new_domains
        save_config(cfg)
        print(f"Successfully removed domain: {domain_id}")

def list_domains():
    cfg = load_config()
    print("\nCurrently monitoring:")
    for d in cfg.get("domain", []):
        print(f"- {d['id']}: {d['name']} ({len(d['keywords'])} keywords)")

def main():
    parser = argparse.ArgumentParser(description="Manage monitored research domains.")
    subparsers = parser.add_subparsers(dest="command")

    # Add Topic Inferred
    infer_parser = subparsers.add_parser("add-topic", help="Add a domain by inferring from a topic")
    infer_parser.add_argument("topic", help="The research topic/title you are interested in")

    # Add Manual
    manual_parser = subparsers.add_parser("add-manual", help="Add a domain manually")
    manual_parser.add_argument("--id", required=True)
    manual_parser.add_argument("--name", required=True)
    manual_parser.add_argument("--keywords", required=True, help="Comma separated keywords")
    manual_parser.add_argument("--exclude", help="Comma separated exclude keywords")

    # Remove
    remove_parser = subparsers.add_parser("remove", help="Remove a domain by ID")
    remove_parser.add_argument("id")

    # List
    subparsers.add_parser("list", help="List all monitored domains")

    args = parser.parse_args()

    if args.command == "add-topic":
        add_topic_inferred(args.topic)
    elif args.command == "add-manual":
        add_domain_manual(args.id, args.name, args.keywords, args.exclude)
    elif args.command == "remove":
        remove_domain(args.id)
    elif args.command == "list":
        list_domains()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
