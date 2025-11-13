"""
SQLite FTS5 helper used to narrow long node spans when PageIndex provides
large sections. Intended for small in-memory workloads within the demo.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, List, Tuple


class FTS5Fallback:
    def __init__(self, table_name: str = "paragraphs") -> None:
        self.table_name = table_name
        self.conn = sqlite3.connect(":memory:")
        self._init_table()

    def _init_table(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name} USING fts5(idx UNINDEXED, content)"
        )
        self.conn.commit()

    def load_paragraphs(self, paragraphs: Iterable[Tuple[int, str]]) -> None:
        cursor = self.conn.cursor()
        cursor.execute(f"DELETE FROM {self.table_name}")
        cursor.executemany(
            f"INSERT INTO {self.table_name}(idx, content) VALUES (?, ?)",
            paragraphs,
        )
        self.conn.commit()

    def top_spans(self, query: str, top_k: int = 3) -> List[Tuple[int, str, float]]:
        cursor = self.conn.cursor()
        cursor.execute(
            f"""
            SELECT idx, content, bm25({self.table_name}) AS score
            FROM {self.table_name}
            WHERE {self.table_name} MATCH ?
            ORDER BY score LIMIT ?
            """,
            (query, top_k),
        )
        return cursor.fetchall()

    def close(self) -> None:
        self.conn.close()
