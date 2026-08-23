#!/usr/bin/env python3
"""Fetch live GitHub stats and inject them into README.md between the
STATS markers, formatted to match the terminal README's `$ command` style.
Also regenerates assets/lang-chart.svg, an animated top-languages bar chart.

Usage: python3 scripts/fetch_stats.py [--demo]
Reads GITHUB_TOKEN from the environment (set by the Action). Runs
unauthenticated (lower rate limit, no contribution/streak/commit data —
those need GraphQL, which requires auth) if unset.
"""
import datetime
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

USER = "Ashad001"
REPO = Path(__file__).resolve().parent.parent
TOKEN = os.environ.get("GITHUB_TOKEN")
START = "<!-- STATS:START -->"
END = "<!-- STATS:END -->"
AMBER = "#E8A33D"


def _headers():
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return headers


def _get(url):
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_profile():
    data = _get(f"https://api.github.com/users/{USER}")
    return data["public_repos"], data["followers"]


def fetch_repo_stats():
    stars = 0
    langs = Counter()
    top_repo, top_stars = None, -1
    page = 1
    while True:
        data = _get(
            f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&type=owner"
        )
        if not data:
            break
        for repo in data:
            if repo.get("fork"):
                continue
            s = repo.get("stargazers_count", 0)
            stars += s
            if s > top_stars:
                top_stars, top_repo = s, repo["name"]
            if repo.get("language"):
                langs[repo["language"]] += 1
        if len(data) < 100:
            break
        page += 1
    return stars, langs, top_repo, top_stars


def compute_streaks(days):
    """days: ascending list of {"date": ..., "contributionCount": int}."""
    longest = run = 0
    for d in days:
        if d["contributionCount"] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    current = 0
    for i, d in enumerate(reversed(days)):
        if d["contributionCount"] > 0:
            current += 1
        elif i == 0:
            continue  # today may just have no contributions yet
        else:
            break
    return current, longest


def fetch_contributions():
    """Requires an authenticated token; GraphQL has no unauthenticated access."""
    if not TOKEN:
        return None
    query = {
        "query": (
            "query($login:String!){user(login:$login){contributionsCollection{"
            "totalCommitContributions totalPullRequestContributions "
            "totalIssueContributions "
            "contributionCalendar{totalContributions weeks{contributionDays{"
            "date contributionCount}}}}}}"
        ),
        "variables": {"login": USER},
    }
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps(query).encode(),
        headers={**_headers(), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())["data"]["user"]["contributionsCollection"]
    days = [d for week in data["contributionCalendar"]["weeks"] for d in week["contributionDays"]]
    current_streak, longest_streak = compute_streaks(days)
    return {
        "total": data["contributionCalendar"]["totalContributions"],
        "commits": data["totalCommitContributions"],
        "prs": data["totalPullRequestContributions"],
        "issues": data["totalIssueContributions"],
        "current_streak": current_streak,
        "longest_streak": longest_streak,
    }


def render(public_repos, followers, stars, langs, top_repo, top_stars, contrib, timestamp):
    top_langs = " · ".join(lang for lang, _ in langs.most_common(3)) if langs else "n/a"
    rows = [
        ("public_repos", public_repos),
        ("followers", followers),
        ("total_stars", stars),
        ("most_starred", f"{top_repo} ({top_stars} ★)" if top_repo else "n/a"),
        ("top_languages", top_langs),
    ]
    if contrib:
        rows += [
            ("", ""),
            ("contributions_ytd", contrib["total"]),
            ("commits_ytd", contrib["commits"]),
            ("pull_requests_ytd", contrib["prs"]),
            ("issues_ytd", contrib["issues"]),
            ("current_streak", f"{contrib['current_streak']} days"),
            ("longest_streak", f"{contrib['longest_streak']} days"),
        ]
    width = max(len(label) for label, _ in rows) + 2
    lines = [f"{label:<{width}}{value}" if label else "" for label, value in rows]
    body = (
        "```\n$ gh api stats --live\n```\n\n"
        "```text\n" + "\n".join(lines) + f"\n\nlast_synced: {timestamp} UTC\n```"
    )
    return f"{START}\n{body}\n{END}"


def render_lang_chart(langs: Counter, path: Path, top_n: int = 6) -> None:
    items = langs.most_common(top_n)
    if not items:
        return
    max_count = items[0][1]
    label_w, bar_max_w, bar_h, row_h, pad = 130, 260, 12, 26, 10
    width = label_w + bar_max_w + 60
    height = pad * 2 + row_h * len(items)

    bars = []
    for i, (lang, count) in enumerate(items):
        y = pad + i * row_h
        bar_w = max(6, round(bar_max_w * count / max_count))
        delay = round(i * 0.12, 2)
        bars.append(
            f'<text x="0" y="{y + bar_h - 1}" class="label">{lang}</text>'
            f'<rect x="{label_w}" y="{y}" width="{bar_w}" height="{bar_h}" rx="2" '
            f'class="bar" style="animation-delay:{delay}s" />'
            f'<text x="{label_w + bar_max_w + 10}" y="{y + bar_h - 1}" class="count">{count}</text>'
        )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" \
viewBox="0 0 {width} {height}" font-family="Menlo, Consolas, monospace" font-size="12">
  <style>
    .label {{ fill: #6e7681; }}
    .count {{ fill: #6e7681; }}
    .bar {{ fill: {AMBER}; transform-box: fill-box; transform-origin: left;
            animation: grow 0.8s cubic-bezier(.2,.8,.2,1) both; }}
    @keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
    @media (prefers-color-scheme: dark) {{
      .label {{ fill: #8b949e; }}
      .count {{ fill: #8b949e; }}
    }}
  </style>
  {''.join(bars)}
</svg>'''
    path.write_text(svg)


def inject(readme_path: Path, block: str) -> bool:
    text = readme_path.read_text()
    if START not in text or END not in text:
        raise SystemExit(f"markers not found in {readme_path}")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    new_text = pattern.sub(lambda _: block, text)
    if new_text != text:
        readme_path.write_text(new_text)
        return True
    return False


def demo():
    """Smoke check: regex injection replaces the marked block and nothing else."""
    tmp = REPO / "_stats_inject_test.md"
    tmp.write_text("before\n<!-- STATS:START -->\nold\n<!-- STATS:END -->\nafter\n")
    try:
        block = render(10, 20, 30, Counter({"Python": 5, "Go": 2}), "demo-repo", 9, None, "2026-01-01 00:00")
        assert inject(tmp, block)
        result = tmp.read_text()
        assert result.startswith("before\n") and result.endswith("after\n")
        assert "public_repos" in result and "10" in result
        assert "old" not in result
        print("demo ok: stats block injected, surrounding content preserved")
    finally:
        tmp.unlink()


def main():
    public_repos, followers = fetch_profile()
    stars, langs, top_repo, top_stars = fetch_repo_stats()
    contrib = fetch_contributions()
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    block = render(public_repos, followers, stars, langs, top_repo, top_stars, contrib, timestamp)
    changed = inject(REPO / "README.md", block)

    render_lang_chart(langs, REPO / "assets" / "lang-chart.svg")

    # machine-readable copy for scripts/build_card.py
    card_stats = {
        "public_repos": public_repos,
        "followers": followers,
        "total_stars": stars,
        "most_starred": f"{top_repo} ({top_stars} \u2605)" if top_repo else "n/a",
        "top_languages": " \u00b7 ".join(l for l, _ in langs.most_common(3)) or "n/a",
    }
    if contrib:
        card_stats.update(
            commits_ytd=contrib["commits"],
            current_streak=contrib["current_streak"],
            longest_streak=contrib["longest_streak"],
        )
    (REPO / "assets" / "stats.json").write_text(json.dumps(card_stats, indent=2) + "\n")

    print("updated" if changed else "no changes")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        main()
