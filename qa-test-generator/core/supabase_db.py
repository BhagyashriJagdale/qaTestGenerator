"""
Supabase DB
-----------
Persists GeneratedTestSuite objects in a Supabase (Postgres) table.

Table: test_suites
  id            uuid        PK, auto-generated
  feature_name  text
  generated_at  timestamptz
  domain        text
  score         float
  total_tests   int
  manual_count  int
  api_count     int
  ui_count      int
  suite_json    jsonb       full GeneratedTestSuite serialised
  output_md     text        formatted markdown output
  created_at    timestamptz default now()

Run the SQL in supabase_schema.sql once in your Supabase SQL editor to create the table.
"""

from typing import Optional
from supabase import create_client, Client
from config import get_settings

TABLE = "test_suites"

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


class SupabaseDB:
    """Read / write test suites via the Supabase Python client."""

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.supabase_url and settings.supabase_key)

    # ── CRUD ──────────────────────────────────────────────────────────────

    def save_suite(self, suite) -> str:
        """Insert a GeneratedTestSuite row. Returns the new row's UUID."""
        total = (
            len(suite.manual_test_cases)
            + len(suite.api_test_cases)
            + len(suite.ui_test_cases)
        )
        score = suite.review.final_score if suite.review else 0.0

        row = {
            "feature_name": suite.feature_name,
            "generated_at": suite.generated_at.isoformat(),
            "domain":       getattr(suite.analysis, "domain", ""),
            "score":        score,
            "total_tests":  total,
            "manual_count": len(suite.manual_test_cases),
            "api_count":    len(suite.api_test_cases),
            "ui_count":     len(suite.ui_test_cases),
            "suite_json":   suite.model_dump(mode="json"),
            "output_md":    suite.markdown_output,
        }

        result = _get_client().table(TABLE).insert(row).execute()
        return result.data[0]["id"]

    def list_suites(self, limit: int = 100) -> list[dict]:
        """Return lightweight summaries, newest first."""
        result = (
            _get_client()
            .table(TABLE)
            .select("id, feature_name, generated_at, domain, score, total_tests, manual_count, api_count, ui_count")
            .order("generated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def get_suite(self, suite_id: str) -> Optional[dict]:
        """Return the full suite_json for a given UUID."""
        result = (
            _get_client()
            .table(TABLE)
            .select("suite_json")
            .eq("id", suite_id)
            .single()
            .execute()
        )
        return result.data.get("suite_json") if result.data else None

    def get_output(self, suite_id: str) -> Optional[str]:
        """Return the markdown output for a given UUID."""
        result = (
            _get_client()
            .table(TABLE)
            .select("output_md")
            .eq("id", suite_id)
            .single()
            .execute()
        )
        return result.data.get("output_md") if result.data else None

    def get_full_row(self, suite_id: str) -> Optional[dict]:
        """Return the full row (metadata + suite_json + output_md)."""
        result = (
            _get_client()
            .table(TABLE)
            .select("*")
            .eq("id", suite_id)
            .single()
            .execute()
        )
        return result.data or None

    def delete_suite(self, suite_id: str) -> bool:
        """Delete a suite row by UUID."""
        _get_client().table(TABLE).delete().eq("id", suite_id).execute()
        return True

    def search_suites(self, query: str, limit: int = 50) -> list[dict]:
        """Full-text search on feature_name and domain."""
        result = (
            _get_client()
            .table(TABLE)
            .select("id, feature_name, generated_at, domain, score, total_tests, manual_count, api_count, ui_count")
            .ilike("feature_name", f"%{query}%")
            .order("generated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []


_db: Optional[SupabaseDB] = None


def get_supabase_db() -> SupabaseDB:
    global _db
    if _db is None:
        _db = SupabaseDB()
    return _db
