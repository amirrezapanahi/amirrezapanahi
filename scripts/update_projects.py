from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


USERNAME = os.getenv("GITHUB_REPOSITORY_OWNER", "amirrezapanahi")
TOKEN = os.getenv("GITHUB_TOKEN", "")
FEATURED_TOPIC = os.getenv("FEATURED_TOPIC", "featured").lower()
MAX_PROJECTS = int(os.getenv("MAX_PROJECTS", "6"))
README_PATH = Path(os.getenv("README_PATH", "README.md"))
API_BASE = "https://api.github.com"
API_VERSION = "2026-03-10"
START_MARKER = "<!-- PROJECTS:START -->"
END_MARKER = "<!-- PROJECTS:END -->"


def github_request(path: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": f"{USERNAME}-profile-readme",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(f"{API_BASE}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"GitHub API error {error.code}: {request.full_url}\n{body}", file=sys.stderr)
        raise


def get_repositories() -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({
            "type": "owner", "sort": "updated", "direction": "desc",
            "per_page": 100, "page": page,
        })
        data = github_request(f"/users/{USERNAME}/repos?{query}")
        if not data:
            break
        repositories.extend(data)
        if len(data) < 100:
            break
        page += 1
    return repositories


def get_topics(repo_name: str) -> list[str]:
    data = github_request(f"/repos/{USERNAME}/{repo_name}/topics")
    return [topic.lower() for topic in data.get("names", [])]


def get_priority(topics: list[str]) -> int:
    priorities = [int(match.group(1)) for topic in topics if (match := re.fullmatch(r"priority-(\d+)", topic))]
    return min(priorities) if priorities else 999


def pushed_timestamp(repo: dict[str, Any]) -> float:
    value = repo.get("pushed_at")
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def select_projects(repositories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for repo in repositories:
        name = repo.get("name", "")
        if (not name or name.lower() == USERNAME.lower() or repo.get("fork")
                or repo.get("archived") or repo.get("disabled")):
            continue
        topics = get_topics(name)
        if FEATURED_TOPIC not in topics:
            continue
        repo["_topics"] = topics
        repo["_priority"] = get_priority(topics)
        selected.append(repo)

    selected.sort(key=lambda repo: (
        repo["_priority"], -repo.get("stargazers_count", 0), -pushed_timestamp(repo),
    ))
    return selected[:MAX_PROJECTS]


def project_icon(topics: list[str]) -> str:
    topic_set = set(topics)
    if {"robotics", "robot"} & topic_set:
        return "🤖"
    if {"embedded", "embedded-systems", "microcontroller", "arduino"} & topic_set:
        return "🔧"
    if {"iot", "internet-of-things"} & topic_set:
        return "📡"
    if {"automation", "automation-tool"} & topic_set:
        return "⚙️"
    if {"web", "full-stack", "fullstack", "frontend", "backend"} & topic_set:
        return "🌐"
    return "🚀"


def render_project(repo: dict[str, Any]) -> str:
    topics = repo.get("_topics", [])
    description = " ".join((repo.get("description") or f"A project by @{USERNAME}.").split())
    visible_topics = [topic for topic in topics if topic != FEATURED_TOPIC and not topic.startswith("priority-")][:6]
    metadata = [f"⭐ {repo.get('stargazers_count', 0)}", f"🍴 {repo.get('forks_count', 0)}"]
    if repo.get("language"):
        metadata.append(f"💻 {repo['language']}")
    metadata.append(f"🕒 {repo.get('pushed_at', '')[:10] or 'Unknown'}")
    links = f"[Repository →]({repo['html_url']})"
    homepage = (repo.get("homepage") or "").strip()
    if homepage.startswith(("https://", "http://")):
        links += f" · [Live Demo ↗]({homepage})"

    lines = [
        f"### {project_icon(topics)} [{repo['name']}]({repo['html_url']})", "", description, "",
        " · ".join(metadata),
    ]
    if visible_topics:
        lines.extend(["", " · ".join(f"`{topic}`" for topic in visible_topics)])
    return "\n".join([*lines, "", links])


def update_readme(content: str) -> bool:
    readme = README_PATH.read_text(encoding="utf-8")
    if START_MARKER not in readme or END_MARKER not in readme:
        raise RuntimeError("Project markers were not found in README.md.")
    replacement = f"{START_MARKER}\n\n{content}\n\n{END_MARKER}"
    updated = re.sub(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), replacement, readme, count=1, flags=re.DOTALL)
    if updated == readme:
        print("README is already up to date.")
        return False
    README_PATH.write_text(updated, encoding="utf-8")
    print("README updated.")
    return True


def main() -> None:
    print(f"Fetching repositories for @{USERNAME}...")
    projects = select_projects(get_repositories())
    print(f"Selected {len(projects)} featured projects.")
    content = "\n\n---\n\n".join(map(render_project, projects)) or (
        "> No featured projects yet. Add the `featured` topic to a repository."
    )
    update_readme(content)


if __name__ == "__main__":
    main()
