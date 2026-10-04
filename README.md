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
pip install anthropic --break-system-packages   # optional, Anthropic fallback only
```

## Usage

```bash
python github_content_generator.py owner/repo
python github_content_generator.py owner/repo --out ./content
python github_content_generator.py owner/repo --ai        # sharpens copy via OpenRouter
python github_content_generator.py owner/repo --token YOUR_GITHUB_TOKEN
```

`--ai` uses OpenRouter and requires an `OPENROUTER_API_KEY` environment variable
(in GitHub Actions: repo Settings → Secrets and variables → Actions → `OPENROUTER_API_KEY`).
If it is missing, `ANTHROPIC_API_KEY` is used as a fallback; if neither is set,
the plain template copy is written.

Optional model overrides (environment variables):
- `OPENROUTER_MODEL` — long-form copy (Reel, carousel, LinkedIn, YouTube). Default `anthropic/claude-sonnet-4.5`
- `OPENROUTER_MODEL_FAST` — short copy (Instagram post, X thread). Default `google/gemini-2.5-flash`

`--token` (or the `GITHUB_TOKEN` env var) raises GitHub's anonymous rate limit
(60 requests/hour) — recommended for repeated use.

## Output
instagram_reel.md
instagram_carousel.md
instagram_post.md
linkedin_post.md
youtube_script.md
x_thread.md
repo_meta.json
Running the script creates a folder (default: `generated_content/<repo-name>/`)
containing:
