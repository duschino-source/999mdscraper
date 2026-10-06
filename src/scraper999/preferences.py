"""Store pairwise listing preferences for future local-model fine-tuning."""

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class PreferenceStore:
    def __init__(self, db_path: str | Path = "scraper.db"):
        self.conn = sqlite3.connect(str(db_path), timeout=30)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS listing_preferences (
                id INTEGER PRIMARY KEY,
                chosen_url TEXT NOT NULL,
                rejected_url TEXT NOT NULL,
                criteria TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS items (
                url TEXT PRIMARY KEY,
                title TEXT,
                price REAL,
                currency TEXT,
                description TEXT,
                date_added TEXT,
                last_seen TEXT,
                price_dropped INTEGER DEFAULT 0
            )"""
        )
        self.conn.commit()

    def record(self, chosen_url: str, rejected_url: str, criteria: dict, reason: str = ""):
        if chosen_url == rejected_url:
            raise ValueError("Chosen and rejected listings must be different")
        if not isinstance(criteria, dict) or not isinstance(criteria.get("weights"), dict):
            raise ValueError("Criteria must contain a weights object")
        weights = criteria["weights"]
        if set(weights) != {"price", "performance", "storage"}:
            raise ValueError("Weights must define price, performance, and storage")
        try:
            values = [float(weights[name]) for name in ("price", "performance", "storage")]
        except (TypeError, ValueError) as error:
            raise ValueError("Criteria weights must be numeric") from error
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("Criteria weights must be finite and non-negative")
        if not math.isclose(sum(values), 1.0, rel_tol=0, abs_tol=0.001):
            raise ValueError("Criteria weights must add up to 1")
        self.conn.execute(
            "INSERT INTO listing_preferences "
            "(chosen_url, rejected_url, criteria, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                chosen_url,
                rejected_url,
                json.dumps(criteria, ensure_ascii=False, sort_keys=True),
                reason,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def export_dpo(self, output_path: str | Path):
        """Export chosen/rejected pairs in the standard DPO JSONL shape."""
        rows = self.conn.execute(
            """SELECT p.id, p.chosen_url, p.rejected_url, p.criteria, p.reason,
                      c.title, c.price, c.currency, c.description,
                      r.title, r.price, r.currency, r.description
               FROM listing_preferences AS p
               LEFT JOIN items AS c ON c.url = p.chosen_url
               LEFT JOIN items AS r ON r.url = p.rejected_url
               ORDER BY p.id"""
        ).fetchall()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as output:
            for row in rows:
                (preference_id, chosen_url, rejected_url, criteria, reason,
                 chosen_title, chosen_price, chosen_currency, chosen_description,
                 rejected_title, rejected_price, rejected_currency, rejected_description) = row
                preferred = _listing_text(
                    chosen_url, chosen_title, chosen_price, chosen_currency, chosen_description
                )
                other = _listing_text(
                    rejected_url, rejected_title, rejected_price, rejected_currency, rejected_description
                )
                chosen_is_a = preference_id % 2 == 0
                listing_a, listing_b = (preferred, other) if chosen_is_a else (other, preferred)
                profile = json.loads(criteria)
                category = profile.get("category", "items")
                prompt = {
                    "task": f"Choose the better {category} listing using the user's preset criteria.",
                    "criteria": profile,
                    "listing_a": listing_a,
                    "listing_b": listing_b,
                    "instruction": "Reply with only A or B.",
                }
                output.write(json.dumps(
                    {"prompt": json.dumps(prompt, ensure_ascii=False),
                     "chosen": "A" if chosen_is_a else "B",
                     "rejected": "B" if chosen_is_a else "A"},
                    ensure_ascii=False,
                ) + "\n")
        return len(rows)

    def close(self):
        self.conn.close()


def _listing_text(url, title, price, currency, description):
    price_text = "unknown" if price is None else f"{price:g} {currency or ''}".strip()
    return (
        f"Title: {title or 'unknown'}\nPrice: {price_text}\n"
        f"Description: {description or 'unknown'}\nURL: {url}"
    )
