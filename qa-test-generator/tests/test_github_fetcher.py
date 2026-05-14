"""Unit tests for pure functions in tools/github_fetcher.py."""

import pytest
from tools.github_fetcher import _parse_repo_url, _rank_files


# ── _parse_repo_url ──────────────────────────────────────────────────────────

def test_parse_https_url():
    assert _parse_repo_url("https://github.com/owner/repo") == ("owner", "repo")


def test_parse_https_url_trailing_slash():
    assert _parse_repo_url("https://github.com/owner/repo/") == ("owner", "repo")


def test_parse_https_url_dot_git():
    assert _parse_repo_url("https://github.com/owner/repo.git") == ("owner", "repo")


def test_parse_ssh_url():
    assert _parse_repo_url("git@github.com:owner/repo.git") == ("owner", "repo")


def test_parse_ssh_url_no_extension():
    assert _parse_repo_url("git@github.com:owner/repo") == ("owner", "repo")


def test_parse_invalid_host_raises():
    with pytest.raises(ValueError, match="Cannot parse GitHub URL"):
        _parse_repo_url("https://gitlab.com/owner/repo")


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        _parse_repo_url("")


# ── _rank_files ──────────────────────────────────────────────────────────────

def test_rank_skips_node_modules():
    paths = ["node_modules/lodash/index.js", "src/routes/auth.ts"]
    ranked = _rank_files(paths)
    assert "node_modules/lodash/index.js" not in ranked
    assert "src/routes/auth.ts" in ranked


def test_rank_skips_all_skip_dirs():
    skip_paths = [
        "node_modules/pkg/file.js",
        ".git/config",
        "dist/bundle.js",
        "build/output.js",
        "__pycache__/module.pyc",
        ".venv/lib/module.py",
        "venv/lib/module.py",
        "coverage/report.html",
    ]
    assert _rank_files(skip_paths) == []


def test_rank_skips_irrelevant_extensions():
    paths = ["README.md", "image.png", "src/routes/auth.ts"]
    ranked = _rank_files(paths)
    assert "README.md" not in ranked
    assert "image.png" not in ranked
    assert "src/routes/auth.ts" in ranked


def test_rank_routes_before_components():
    paths = [
        "src/components/Login.tsx",
        "src/routes/auth.ts",
    ]
    ranked = _rank_files(paths)
    assert ranked.index("src/routes/auth.ts") < ranked.index("src/components/Login.tsx")


def test_rank_models_before_services():
    paths = [
        "src/services/authService.ts",
        "src/models/User.ts",
    ]
    ranked = _rank_files(paths)
    assert ranked.index("src/models/User.ts") < ranked.index("src/services/authService.ts")


def test_rank_package_json_included():
    paths = ["package.json", "src/app.ts"]
    ranked = _rank_files(paths)
    assert "package.json" in ranked


def test_rank_empty_input():
    assert _rank_files([]) == []


def test_rank_preserves_all_valid_files():
    paths = ["src/routes/auth.ts", "src/models/User.ts", "src/components/App.tsx"]
    ranked = _rank_files(paths)
    assert set(ranked) == set(paths)
