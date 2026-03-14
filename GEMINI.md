# Gemini Context: paper_subscriber

This project is an automated pipeline for fetching, scoring, and summarizing arXiv research papers, specifically targeting Computational Linguistics (`cs.CL`). It uses keyword-based scoring and the `gemini` CLI to generate metadata and translations for research notes.

## Project Overview

- **Purpose**: Automate research tracking by filtering arXiv feeds and generating rich summaries.
- **Main Technologies**: Python 3, `feedparser`, `PyYAML`, and the `gemini` CLI tool.
- **Workflow**:
    1.  **Fetch**: Retrieves the latest papers from the arXiv `cs.CL` RSS feed.
    2.  **Score**: Ranks papers based on keywords defined in `config/fields.yaml`.
    3.  **Summarize**: For high-scoring papers (score >= 2), it uses the `gemini` CLI to generate a one-sentence English summary and a Chinese translation of the abstract.
    4.  **Export**: Saves individual paper notes as Markdown files (using `templates/paper.md.tpl`) into a local Obsidian vault and generates a daily summary in `daily-summaries/`.

## Key Files and Directories

- `scripts/fetch_and_process.py`: The core automation script.
- `config/fields.yaml`: Configuration for domains, keywords (to include/exclude), and priorities.
- `templates/paper.md.tpl`: Markdown template for individual paper notes.
- `daily-summaries/`: Directory containing generated daily aggregate reports.
- `README.md`: Basic project introduction (currently minimal).

## Building and Running

### Prerequisites
- Python 3.x
- Python packages: `pip install feedparser pyyaml`
- `gemini` CLI tool installed and configured in the system PATH.

### Configuration
Edit `config/fields.yaml` to define your research interests:
- `domain`: List of research areas.
- `keywords`: Terms that increase a paper's score.
- `exclude_keywords`: Terms that disqualify a paper (score set to 0).

### Running the Pipeline
Execute the main script:
```bash
python3 scripts/fetch_and_process.py
```
*Note: The script currently assumes an Obsidian vault path at `~/Obsidian/Research`. You may need to modify `VAULT_PATH` in `scripts/fetch_and_process.py` if your vault is located elsewhere.*

## Development Conventions

- **Logic Separation**: Scoring logic is decoupled from fetching and rendering.
- **Template-Based**: Output format for paper notes is controlled by `templates/paper.md.tpl`.
- **Fail-Safe**: If Gemini generation fails, the script uses placeholders (e.g., "自动生成失败") instead of crashing.
- **Throttling**: Includes `time.sleep(1)` between processing papers to respect API/feed limits.
