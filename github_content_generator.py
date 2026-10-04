#!/usr/bin/env python3
"""
github_content_generator.py

Generates Reel scripts, single posts, and carousel decks for Instagram / LinkedIn /
YouTube / X (Twitter) from any public GitHub repository.

USAGE
-----
    python github_content_generator.py owner/repo [--out ./content] [--ai]

    --out   Output folder (default: ./generated_content/<repo>)
    --ai    Use an LLM to rewrite/upgrade the template copy. Uses OpenRouter when
            OPENROUTER_API_KEY is set (falls back to ANTHROPIC_API_KEY if not).
            If no key is available the plain template copy is written instead.
            Without --ai, the script runs fully offline using templates.

            Optional env vars:
              OPENROUTER_MODEL       model for long-form copy (Reel, carousel,
                                     LinkedIn, YouTube). Default anthropic/claude-sonnet-4.5
              OPENROUTER_MODEL_FAST  cheaper model for short copy (IG post, X thread).
                                     Default google/gemini-2.5-flash

REQUIREMENTS
------------
    pip install requests --break-system-packages
    pip install anthropic --break-system-packages   # optional, Anthropic fallback only

OUTPUT
------
    <out>/instagram_reel.md
    <out>/instagram_carousel.md
    <out>/instagram_post.md
    <out>/linkedin_post.md
    <out>/youtube_script.md
    <out>/x_thread.md
    <out>/repo_meta.json
"""

import argparse
import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from typing import List, Optional

import requests

GITHUB_API = "https://api.github.com"


# --------------------------------------------------------------------------- #
# 1. Fetch repo data
# --------------------------------------------------------------------------- #

@dataclass
class RepoInfo:
    full_name: str
    description: str
    stars: int
    forks: int
    language: str
    topics: List[str]
    readme: str
    url: str


def fetch_repo_info(owner_repo: str, token: Optional[str] = None) -> RepoInfo:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-content-generator-script",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    repo_resp = requests.get(f"{GITHUB_API}/repos/{owner_repo}", headers=headers, timeout=20)
    repo_resp.raise_for_status()
    repo = repo_resp.json()

    readme_text = ""
    readme_resp = requests.get(
        f"{GITHUB_API}/repos/{owner_repo}/readme",
        headers={**headers, "Accept": "application/vnd.github.raw+json", "User-Agent": "github-content-generator-script"},
        timeout=20,
    )
    if readme_resp.status_code == 200:
        readme_text = readme_resp.text

    return RepoInfo(
        full_name=repo.get("full_name", owner_repo),
        description=repo.get("description") or "",
        stars=repo.get("stargazers_count", 0),
        forks=repo.get("forks_count", 0),
        language=repo.get("language") or "Multiple",
        topics=repo.get("topics", []) or [],
        readme=readme_text,
        url=repo.get("html_url", f"https://github.com/{owner_repo}"),
    )


def extract_features(readme: str, limit: int = 6) -> List[str]:
    """Pull bullet points from the README as candidate 'feature' lines."""
    bullets = re.findall(r"^\s*[-*]\s+(.*)", readme, flags=re.MULTILINE)
    cleaned = []
    for b in bullets:
        b = re.sub(r"[`*_#]", "", b).strip()
        b = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", b)  # strip markdown links
        if 8 <= len(b) <= 140:
            cleaned.append(b)
        if len(cleaned) >= limit:
            break
    return cleaned


# --------------------------------------------------------------------------- #
# 2. Optional AI rewrite layer (OpenRouter, with Anthropic API as fallback)
# --------------------------------------------------------------------------- #

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
FAST_MODEL = os.environ.get("OPENROUTER_MODEL_FAST", "google/gemini-2.5-flash")

SYSTEM_PROMPT = (
    "You are a sharp, concise social media copywriter for Scroll-Worthy. "
    "You rewrite the draft you are given. Keep every factual detail (names, numbers, links) "
    "exactly as in the draft and never invent features, stats or claims. "
    "Return only the rewritten copy, with no preamble or commentary."
)


def ai_rewrite(instruction: str, draft: str, system: str = "", fast: bool = False) -> str:
    """Rewrite `draft` following `instruction` using an LLM.

    Tries OpenRouter first (OPENROUTER_API_KEY), then the Anthropic API
    (ANTHROPIC_API_KEY). If neither is configured, or every call fails, the
    original `draft` is returned unchanged so the pipeline never writes
    prompt text or empty files.

    fast=True routes to the cheaper OPENROUTER_MODEL_FAST (for short copy).
    """
    system = system or SYSTEM_PROMPT
    user_msg = f"{instruction}\n\n{draft}"

    # --- 1. OpenRouter ------------------------------------------------------
    or_key = os.environ.get("OPENROUTER_API_KEY")
    if or_key:
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {or_key}",
                    "Content-Type": "application/json",
                    "X-Title": "Scroll-Worthy",
                },
                json={
                    "model": FAST_MODEL if fast else DEFAULT_MODEL,
                    "max_tokens": 1200,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                },
                timeout=90,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            return (text or "").strip() or draft
        except Exception as exc:  # network, HTTP error, unexpected response shape
            print(f"[warn] OpenRouter call failed ({exc}); trying fallback", file=sys.stderr)

    # --- 2. Anthropic API fallback -----------------------------------------
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1200,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
            return "\n".join(parts).strip() or draft
        except Exception as exc:
            print(f"[warn] Anthropic call failed ({exc}); using template copy", file=sys.stderr)

    return draft


# --------------------------------------------------------------------------- #
# 3. Content generators (one function per platform/format)
# --------------------------------------------------------------------------- #

def _hashtags(repo: RepoInfo, extra: List[str]) -> str:
    base = [f"#{t.replace('-', '')}" for t in repo.topics[:5]]
    base += [f"#{repo.language}", "#OpenSource", "#GitHub", "#BuildInPublic"]
    base += extra
    seen, out = set(), []
    for h in base:
        h = h.replace(" ", "")
        if h.lower() not in seen and len(h) > 1:
            seen.add(h.lower())
            out.append(h)
    return " ".join(out[:12])


def gen_instagram_reel(repo: RepoInfo, features: List[str], use_ai: bool) -> str:
    hook = f"I built {repo.full_name.split('/')[-1]} so you don't have to."
    script = textwrap.dedent(f"""
    HOOK (0-3s): "{hook}"
    On screen text: "{repo.description or 'A project worth showing off'}"

    BEAT 1 (3-8s): Show the repo / terminal / app running.
      VO: "This is {repo.full_name.split('/')[-1]} — {repo.description or 'a tool I built'}."

    BEAT 2 (8-18s): Rapid cut through 3 features.
    """).strip() + "\n"
    for i, f in enumerate(features[:3], start=1):
        script += f"      Feature {i}: {f}\n"
    script += textwrap.dedent(f"""
    BEAT 3 (18-25s): Show the result / output / dashboard.
      VO: "The best part? {features[0] if features else 'It just works.'}"

    CTA (25-30s): "Link in bio — repo is open on GitHub. Star it if it's useful."

    On-screen caption:
    {repo.description or 'Check the repo in bio.'}

    Caption for post:
    {hook} 👇
    {repo.description}
    Built in {repo.language}. Repo linked in bio.
    {_hashtags(repo, ['#Reels', '#CodingReels', '#DevLife'])}
    """).strip()

    if use_ai:
        script = ai_rewrite(
            "Rewrite this Instagram Reel script to be punchier and more scroll-stopping, "
            "keep the same beat structure and timing labels, keep it under 30 seconds of spoken content:",
            script,
        )
    return script


def gen_instagram_carousel(repo: RepoInfo, features: List[str], use_ai: bool) -> str:
    slides = [f"SLIDE 1 (Cover): \"{repo.full_name.split('/')[-1]}\" — {repo.description or 'a project you should know about'}"]
    for i, feat in enumerate(features[:6], start=2):
        slides.append(f"SLIDE {i}: {feat}")
    slides.append(f"SLIDE {len(slides)+1} (Stack): Built with {repo.language}. "
                   f"⭐ {repo.stars} stars · 🍴 {repo.forks} forks")
    slides.append(f"SLIDE {len(slides)+1} (CTA): Full repo linked in bio. Save this for later 🔖")

    body = "\n\n".join(slides)
    caption = (
        f"Swipe through → {repo.description or 'what this project does'}.\n"
        f"Repo: {repo.url}\n"
        f"{_hashtags(repo, ['#Carousel', '#DevCommunity'])}"
    )
    out = body + "\n\n---\nCAPTION:\n" + caption
    if use_ai:
        out = ai_rewrite(
            "Rewrite this Instagram carousel (one line per slide, keep slide numbering) "
            "to be tighter and more visually descriptive for a designer to build from:",
            out,
        )
    return out


def gen_instagram_post(repo: RepoInfo, features: List[str], use_ai: bool) -> str:
    body = (
        f"{repo.description or repo.full_name}\n\n"
        + "\n".join(f"✅ {f}" for f in features[:5])
        + f"\n\nBuilt in {repo.language}. Link in bio.\n"
        + _hashtags(repo, ["#SoftwareEngineering"])
    )
    if use_ai:
        body = ai_rewrite(
            "Rewrite this single Instagram post caption to be more engaging, keep it under 150 words:",
            body,
            fast=True,
        )
    return body


def gen_linkedin_post(repo: RepoInfo, features: List[str], use_ai: bool) -> str:
    post = textwrap.dedent(f"""
    I open-sourced {repo.full_name.split('/')[-1]}.

    {repo.description or 'Here is what it does and why I built it.'}

    What it does:
    """).strip() + "\n"
    for f in features[:5]:
        post += f"→ {f}\n"
    post += textwrap.dedent(f"""
    Stack: {repo.language}

    Why this matters: sharing the build in public — the good, the bugs, and the fixes —
    is more useful to the community than a polished announcement after the fact.

    Repo: {repo.url}

    If you're working on something similar, I'd love to compare notes in the comments.

    {_hashtags(repo, ['#OpenSource', '#SoftwareDevelopment', '#BuildInPublic'])}
    """).strip()
    if use_ai:
        post = ai_rewrite(
            "Rewrite this LinkedIn post to sound like a credible practitioner sharing real work "
            "(no hype, no emojis in the body, professional but personal tone):",
            post,
        )
    return post


def gen_youtube_script(repo: RepoInfo, features: List[str], use_ai: bool) -> str:
    title = f"I Built {repo.full_name.split('/')[-1]} — Full Walkthrough"
    script = textwrap.dedent(f"""
    TITLE: {title}

    THUMBNAIL TEXT: "{repo.full_name.split('/')[-1].upper()}"

    [INTRO — 0:00-0:20]
    "In this video I'm walking you through {repo.full_name.split('/')[-1]} — {repo.description or 'a project I built and open-sourced'}.
    By the end you'll know exactly how it works and how to run it yourself."

    [WHY I BUILT THIS — 0:20-1:00]
    Explain the problem this solves, who it's for, and what existed before (or didn't).

    [FEATURE WALKTHROUGH — 1:00-5:00]
    """).strip() + "\n"
    for i, f in enumerate(features[:6], start=1):
        script += f"  {i}. {f} — show this live on screen, don't just describe it.\n"
    script += textwrap.dedent(f"""
    [ARCHITECTURE / HOW IT WORKS — 5:00-7:00]
    Show the repo structure, key files, and the core logic. Keep this at a level a
    junior developer could follow.

    [DEMO — 7:00-9:00]
    Run it end to end. Show real output.

    [OUTRO / CTA — 9:00-9:30]
    "Repo is linked in the description — star it, fork it, open an issue if you find a bug.
    Subscribe if you want more build-in-public content like this."

    DESCRIPTION:
    {repo.description}
    Repo: {repo.url}
    Stack: {repo.language}

    TAGS: {", ".join(repo.topics[:8]) or repo.language}
    """).strip()
    if use_ai:
        script = ai_rewrite(
            "Rewrite this YouTube script to be tighter with stronger retention hooks between sections, "
            "keep the timestamp structure:",
            script,
        )
    return script


def gen_x_thread(repo: RepoInfo, features: List[str], use_ai: bool) -> str:
    tweets = [f"1/ I built {repo.full_name.split('/')[-1]}.\n\n{repo.description or 'Here is what it does:'}"]
    for i, f in enumerate(features[:5], start=2):
        tweets.append(f"{i}/ {f}")
    n = len(tweets) + 1
    tweets.append(f"{n}/ Built in {repo.language}. Open source, link below.\n\n{repo.url}")
    thread = "\n\n".join(tweets)
    if use_ai:
        thread = ai_rewrite(
            "Rewrite this X (Twitter) thread to be punchier, one idea per tweet, keep the numbering (1/, 2/, ...):",
            thread,
            fast=True,
        )
    return thread


# --------------------------------------------------------------------------- #
# 4. Orchestration
# --------------------------------------------------------------------------- #

def generate_all(owner_repo: str, out_dir: str, use_ai: bool = False, token: Optional[str] = None) -> None:
    repo = fetch_repo_info(owner_repo, token=token)
    features = extract_features(repo.readme) or [
        repo.description or "Core functionality",
        f"Written in {repo.language}",
    ]

    os.makedirs(out_dir, exist_ok=True)

    files = {
        "instagram_reel.md": gen_instagram_reel(repo, features, use_ai),
        "instagram_carousel.md": gen_instagram_carousel(repo, features, use_ai),
        "instagram_post.md": gen_instagram_post(repo, features, use_ai),
        "linkedin_post.md": gen_linkedin_post(repo, features, use_ai),
        "youtube_script.md": gen_youtube_script(repo, features, use_ai),
        "x_thread.md": gen_x_thread(repo, features, use_ai),
    }

    for filename, content in files.items():
        with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as fh:
            fh.write(content + "\n")

    meta = {
        "repo": repo.full_name,
        "description": repo.description,
        "stars": repo.stars,
        "forks": repo.forks,
        "language": repo.language,
        "topics": repo.topics,
        "url": repo.url,
        "features_used": features,
        "ai_enhanced": use_ai,
    }
    with open(os.path.join(out_dir, "repo_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    print(f"Generated {len(files)} content files + repo_meta.json in: {out_dir}")


def main():
    parser = argparse.ArgumentParser(description="Generate multi-platform social content from a GitHub repo.")
    parser.add_argument("repo", help="GitHub repo as owner/name, e.g. ganesh/GK_AI_Traders")
    parser.add_argument("--out", default=None, help="Output directory (default: ./generated_content/<repo-name>)")
    parser.add_argument("--ai", action="store_true", help="Use an LLM (OPENROUTER_API_KEY, or ANTHROPIC_API_KEY as fallback) to sharpen the copy")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token (optional, raises rate limit)")
    args = parser.parse_args()

    out_dir = args.out or os.path.join("generated_content", args.repo.split("/")[-1])
    generate_all(args.repo, out_dir, use_ai=args.ai, token=args.token)


if __name__ == "__main__":
    main()
