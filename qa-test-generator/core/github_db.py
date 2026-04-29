"""
GitHub File-Based DB
--------------------
Persists GeneratedTestSuite objects as files inside a GitHub repository.

Directory layout inside the repo:
  {db_path}/
    index.json                        ← master index (one entry per suite)
    YYYY-MM-DD/
      {slug}_{HHMMSS}/
        metadata.json                 ← lightweight summary
        suite.json                    ← full GeneratedTestSuite JSON
        output.md                     ← formatted markdown output

All file I/O goes through the GitHub Contents REST API.
No extra dependencies beyond `requests`.
"""

import base64
import json
import re
from datetime import datetime
from typing import Optional

import requests

from config import get_settings


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "-", text)[:48]


class GitHubDB:
    """Read/write test suites to a GitHub repository via the Contents API."""

    API = "https://api.github.com"

    def __init__(self):
        settings = get_settings()
        self.token = settings.github_token
        self.repo  = settings.github_repo        # "owner/repo"
        self.branch = settings.github_branch
        self.db_path = settings.github_db_path   # default "qa-test-suites"

    # ── public checks ──────────────────────────────────────────────────────

    def is_configured(self) -> bool:
        return bool(self.token and self.repo)

    # ── public CRUD ────────────────────────────────────────────────────────

    def save_suite(self, suite) -> str:
        """
        Persist a GeneratedTestSuite.
        Returns the path of the created directory (usable as an ID).
        """
        ts = suite.generated_at
        date_str = ts.strftime("%Y-%m-%d")
        time_str = ts.strftime("%H%M%S")
        slug = _slugify(suite.feature_name)
        dir_path = f"{self.db_path}/{date_str}/{slug}_{time_str}"

        total = (
            len(suite.manual_test_cases)
            + len(suite.api_test_cases)
            + len(suite.ui_test_cases)
        )
        score = suite.review.final_score if suite.review else 0.0

        metadata = {
            "id":            f"{slug}_{date_str}_{time_str}",
            "feature_name":  suite.feature_name,
            "generated_at":  ts.isoformat(),
            "score":         score,
            "total_tests":   total,
            "manual_count":  len(suite.manual_test_cases),
            "api_count":     len(suite.api_test_cases),
            "ui_count":      len(suite.ui_test_cases),
            "path":          dir_path,
            "domain":        getattr(suite.analysis, "domain", ""),
        }

        suite_dict = suite.model_dump(mode="json")

        # Write all three files
        self._put_file(f"{dir_path}/metadata.json", json.dumps(metadata, indent=2),  f"add metadata: {suite.feature_name}")
        self._put_file(f"{dir_path}/suite.json",    json.dumps(suite_dict, indent=2), f"add suite: {suite.feature_name}")
        self._put_file(f"{dir_path}/output.md",     suite.markdown_output,            f"add output: {suite.feature_name}")

        # Update master index
        self._update_index(metadata)

        return dir_path

    def list_suites(self) -> list[dict]:
        """Return all suite summaries from index.json, newest first."""
        raw = self._get_file_content(f"{self.db_path}/index.json")
        if raw is None:
            return []
        try:
            entries = json.loads(raw)
            return sorted(entries, key=lambda x: x.get("generated_at", ""), reverse=True)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_suite(self, suite_path: str) -> Optional[dict]:
        """Fetch and return the full suite.json for a given path."""
        raw = self._get_file_content(f"{suite_path}/suite.json")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def get_output(self, suite_path: str) -> Optional[str]:
        """Fetch the markdown output for a given path."""
        return self._get_file_content(f"{suite_path}/output.md")

    def delete_suite(self, suite_path: str) -> bool:
        """Delete all files for a suite and remove it from the index."""
        for filename in ("metadata.json", "suite.json", "output.md"):
            self._delete_file(f"{suite_path}/{filename}", f"delete: {suite_path}")

        # Remove from index
        entries = self.list_suites()
        updated = [e for e in entries if e.get("path") != suite_path]
        index_path = f"{self.db_path}/index.json"
        sha = self._get_file_sha(index_path)
        self._put_file(index_path, json.dumps(updated, indent=2), "update index after delete", sha=sha)
        return True

    # ── GitHub Contents API helpers ────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept":        "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, path: str) -> str:
        return f"{self.API}/repos/{self.repo}/contents/{path}"

    def _get_file(self, path: str) -> Optional[dict]:
        """GET file metadata + content. Returns None if not found."""
        resp = requests.get(
            self._url(path),
            headers=self._headers(),
            params={"ref": self.branch},
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def _get_file_content(self, path: str) -> Optional[str]:
        data = self._get_file(path)
        if data is None:
            return None
        return base64.b64decode(data["content"]).decode("utf-8")

    def _get_file_sha(self, path: str) -> Optional[str]:
        data = self._get_file(path)
        return data["sha"] if data else None

    def _put_file(self, path: str, content: str, message: str, sha: Optional[str] = None):
        """Create or update a file. Fetches existing SHA automatically if not provided."""
        if sha is None:
            sha = self._get_file_sha(path)

        payload: dict = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch":  self.branch,
        }
        if sha:
            payload["sha"] = sha

        resp = requests.put(
            self._url(path),
            headers=self._headers(),
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()

    def _delete_file(self, path: str, message: str):
        sha = self._get_file_sha(path)
        if sha is None:
            return
        resp = requests.delete(
            self._url(path),
            headers=self._headers(),
            json={"message": message, "sha": sha, "branch": self.branch},
            timeout=15,
        )
        resp.raise_for_status()

    def _update_index(self, new_entry: dict):
        """Append new_entry to index.json, creating the file if it doesn't exist."""
        index_path = f"{self.db_path}/index.json"
        existing_data = self._get_file(index_path)

        if existing_data:
            entries = json.loads(base64.b64decode(existing_data["content"]).decode("utf-8"))
            sha = existing_data["sha"]
        else:
            entries = []
            sha = None

        # Avoid duplicates
        entries = [e for e in entries if e.get("path") != new_entry["path"]]
        entries.append(new_entry)

        self._put_file(
            index_path,
            json.dumps(entries, indent=2),
            f"update index: {new_entry['feature_name']}",
            sha=sha,
        )


_db: Optional[GitHubDB] = None


def get_github_db() -> GitHubDB:
    global _db
    if _db is None:
        _db = GitHubDB()
    return _db
