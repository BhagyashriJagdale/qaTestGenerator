"""
GitHub Repository Context Fetcher.

Analyses a GitHub repo to extract endpoints, data models, UI components,
and tech stack — then returns a structured context string that the Generator
Agent uses to produce test cases grounded in the actual codebase.
"""

import base64
import re
import json
from typing import Optional
from rich.console import Console

console = Console()

# ------------------------------------------------------------------ #
# Constants                                                            #
# ------------------------------------------------------------------ #

_GITHUB_API = "https://api.github.com"

# File-path keywords → priority tier (1 = highest)
_PRIORITY_TIERS: list[tuple[int, list[str]]] = [
    (1, ["route", "router", "routes", "api", "endpoint", "controller", "handler"]),
    (2, ["model", "schema", "type", "interface", "entity", "dto", "domain"]),
    (3, ["component", "page", "view", "screen", "form"]),
    (4, ["service", "helper", "util", "middleware", "hook"]),
    (5, ["package.json", "requirements.txt", "openapi", "swagger", "pyproject"]),
]

_RELEVANT_EXTS = {
    ".ts", ".tsx", ".js", ".jsx",
    ".py", ".rb", ".go", ".java", ".kt",
    ".yaml", ".yml", ".json",
}

_SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", ".nuxt",
    "vendor", "__pycache__", ".venv", "venv", "coverage",
    ".pytest_cache", "target", "out", ".cache",
}

_MAX_FILES = 15
_MAX_CHARS_PER_FILE = 2000
_MAX_TOTAL_CONTEXT = 16_000


# ------------------------------------------------------------------ #
# Public interface                                                     #
# ------------------------------------------------------------------ #

class GitHubContextFetcher:
    """Fetch and summarise a GitHub repository for test-generation context."""

    def __init__(self, github_token: Optional[str] = None):
        import requests
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if github_token:
            self._session.headers["Authorization"] = f"Bearer {github_token}"

    # ---------------------------------------------------------------- #
    # Entry point                                                       #
    # ---------------------------------------------------------------- #

    def fetch(self, repo_url: str) -> str:
        """
        Analyse a GitHub repository and return a structured context string.

        Args:
            repo_url: Public or private GitHub URL
                      (https://github.com/owner/repo or git@github.com:owner/repo.git)

        Returns:
            Formatted context string ready to be injected into the generation prompt.

        Raises:
            ValueError: If the URL cannot be parsed or the repo is not accessible.
        """
        owner, repo = _parse_repo_url(repo_url)
        console.print(f"\n[bold cyan]  → Fetching GitHub context: {owner}/{repo}[/bold cyan]")

        # 1. Repo metadata
        meta = self._get_repo_meta(owner, repo)

        # 2. File tree
        default_branch = meta.get("default_branch", "main")
        tree = self._get_file_tree(owner, repo, default_branch)

        # 3. Prioritise and fetch relevant files
        ranked = _rank_files(tree)
        file_contents = self._fetch_files(owner, repo, ranked)

        # 4. Build context string
        context = _build_context_string(meta, owner, repo, file_contents)
        console.print(f"  [green]✓ GitHub context ready ({len(context)} chars)[/green]")
        return context

    # ---------------------------------------------------------------- #
    # Private helpers                                                   #
    # ---------------------------------------------------------------- #

    def _get_repo_meta(self, owner: str, repo: str) -> dict:
        resp = self._session.get(f"{_GITHUB_API}/repos/{owner}/{repo}", timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _get_file_tree(self, owner: str, repo: str, branch: str) -> list[str]:
        """Return a flat list of all file paths in the repo."""
        url = f"{_GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return [
            item["path"]
            for item in data.get("tree", [])
            if item.get("type") == "blob"
        ]

    def _fetch_files(
        self, owner: str, repo: str, paths: list[str]
    ) -> list[tuple[str, str]]:
        """Fetch raw content for up to _MAX_FILES paths. Returns (path, content) pairs."""
        results: list[tuple[str, str]] = []
        total_chars = 0

        for path in paths[:_MAX_FILES]:
            if total_chars >= _MAX_TOTAL_CONTEXT:
                break
            try:
                content = self._fetch_file_content(owner, repo, path)
                if content:
                    truncated = content[:_MAX_CHARS_PER_FILE]
                    results.append((path, truncated))
                    total_chars += len(truncated)
            except Exception:
                continue  # skip unreadable files silently

        return results

    def _fetch_file_content(self, owner: str, repo: str, path: str) -> Optional[str]:
        url = f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        resp = self._session.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("encoding") != "base64" or not data.get("content"):
            return None
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return None


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _parse_repo_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from various GitHub URL formats."""
    url = url.strip().rstrip("/").removesuffix(".git")

    # https://github.com/owner/repo
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if m:
        return m.group(1), m.group(2)

    # git@github.com:owner/repo
    m = re.match(r"git@github\.com:([^/]+)/(.+)", url)
    if m:
        return m.group(1), m.group(2)

    raise ValueError(
        f"Cannot parse GitHub URL: '{url}'. "
        "Expected format: https://github.com/owner/repo"
    )


def _rank_files(paths: list[str]) -> list[str]:
    """
    Return paths sorted by relevance tier, excluding non-code and skip directories.
    Highest-priority files come first.
    """
    def _priority(path: str) -> int:
        lower = path.lower()
        # Skip unwanted directories
        parts = path.split("/")
        if any(p in _SKIP_DIRS for p in parts):
            return 99

        # Skip irrelevant extensions
        ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
        if ext not in _RELEVANT_EXTS:
            return 99

        for tier, keywords in _PRIORITY_TIERS:
            if any(kw in lower for kw in keywords):
                return tier

        return 6  # relevant extension but no keyword match

    ranked = sorted(paths, key=_priority)
    return [p for p in ranked if _priority(p) < 99]


def _build_context_string(
    meta: dict,
    owner: str,
    repo: str,
    file_contents: list[tuple[str, str]],
) -> str:
    """Assemble a structured context string from repo metadata and file contents."""
    language = meta.get("language") or "Unknown"
    description = meta.get("description") or ""
    topics = ", ".join(meta.get("topics", [])) or "none"

    lines = [
        "## GITHUB REPOSITORY CONTEXT",
        f"**Repository:** {owner}/{repo}",
        f"**Primary Language:** {language}",
    ]
    if description:
        lines.append(f"**Description:** {description}")
    if topics != "none":
        lines.append(f"**Topics:** {topics}")
    lines.append("")

    # Group files by tier label
    tier_labels = {
        1: "API Routes & Endpoints",
        2: "Data Models & Schemas",
        3: "UI Components & Pages",
        4: "Services & Utilities",
        5: "Configuration & Dependencies",
        6: "Other Source Files",
    }
    grouped: dict[str, list[tuple[str, str]]] = {}

    for path, content in file_contents:
        lower = path.lower()
        tier = 6
        parts = path.split("/")
        if not any(p in _SKIP_DIRS for p in parts):
            for t, keywords in _PRIORITY_TIERS:
                if any(kw in lower for kw in keywords):
                    tier = t
                    break
        label = tier_labels.get(tier, "Other Source Files")
        grouped.setdefault(label, []).append((path, content))

    for label, files in grouped.items():
        lines.append(f"### {label}")
        for path, content in files:
            # For package.json, only show dependencies block
            if path.endswith("package.json"):
                content = _extract_package_json(content)
            lines.append(f"\n**`{path}`**")
            lines.append("```")
            lines.append(content.strip())
            lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _extract_package_json(raw: str) -> str:
    """Extract only name, dependencies, and devDependencies from package.json."""
    try:
        data = json.loads(raw)
        slim = {}
        for key in ("name", "version", "dependencies", "devDependencies", "scripts"):
            if key in data:
                slim[key] = data[key]
        return json.dumps(slim, indent=2)
    except Exception:
        return raw[:_MAX_CHARS_PER_FILE]
