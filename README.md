# AI Novelist Studio

AI-powered novel writing assistant with DeepSeek integration — one-click chapter generation, character management, and foreshadowing tracking.

## Features

- **One-click writing**: Auto-build context -> Generate chapter via DeepSeek API -> Update characters & hooks
- **Continuity**: Reads previous chapter ending to ensure seamless plot & emotional flow
- **Scene diversity**: Analyzes scene types to avoid repetitive chapter structures
- **Outline sync**: Automatically updates Plot_Outline.md after each generation
- **Character tracking**: Extracts new characters and maintains appearance logs
- **Foreshadowing management**: Scans metadata blocks and updates Hooks_Tracker.md
- **Bidirectional links**: Obsidian [[wiki-link]] format with graph view support

## Quick Start

### Requirements
- Python 3.10+
- Node.js 18+ (plugin development only)
- DeepSeek API Key

### Install Python dependencies
```powershell
cd NovelProject
pip install requests pyyaml
```

### Configure API Key
Copy `.env.example` to `.env` and fill in your key:
```
DEEPSEEK_API_KEY=sk-your-key
```

### One-click write next chapter
```powershell
python auto_write.py --novel "文明升阶" --goal "your goal" --update-characters --update-hooks
```

### Obsidian Plugin
Copy `.obsidian/plugins/ai-novelist-studio/` to your vault's `.obsidian/plugins/` directory. See [plugin README](.obsidian/plugins/ai-novelist-studio/README.md) for details.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Python Scripts | pathlib, argparse, yaml, requests, subprocess |
| Obsidian Plugin | TypeScript, Obsidian API, esbuild |
| AI Engine | DeepSeek Chat API |
| Data Format | Markdown + YAML Frontmatter |
