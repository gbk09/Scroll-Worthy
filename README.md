# Scroll-Worthy — GitHub Content Generator

Turns any GitHub repository into ready-to-post content for Instagram, LinkedIn,
YouTube, and X (Twitter) — Reels scripts, carousels, single posts, video
scripts, and threads, all generated from the repo's actual README and metadata.

Built for Scroll-Worthy: content people actually stop for.

## What it does

Given a GitHub repo (`owner/repo`), the script:
- Fetches the repo's description, stars, forks, language, topics, and README
- Extracts feature bullet points from the README
- Generates platform-specific content:
  - Instagram Reel script (hook, beats, CTA, caption)
  - Instagram Carousel (slide-by-slide breakdown + caption)
  - Instagram single post caption
  - LinkedIn post
  - YouTube script (intro, walkthrough, demo, outro, description, tags)
  - X (Twitter) thread

## Requirements

```bash
pip install requests --break-system-packages
pip install anthropic --break-system-packages   # optional, for --ai mode
```

## Usage

```bash
python github_content_generator.py owner/repo
python github_content_generator.py owner/repo --out ./content
python github_content_generator.py owner/repo --ai        # sharpens copy via Claude
python github_content_generator.py owner/repo --token YOUR_GITHUB_TOKEN
```

`--ai` requires an `ANTHROPIC_API_KEY` environment variable.
`--token` (or the `GITHUB_TOKEN` env var) raises GitHub's anonymous rate limit
(60 requests/hour) — recommended for repeated use.

## Output

Running the script creates a folder (default: `generated_content/<repo-name>/`)
containing:
