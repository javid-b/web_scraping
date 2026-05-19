from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .parser import ScrapedProduct


SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id         TEXT NOT NULL,
    category_url    TEXT NOT NULL,
    product_name    TEXT NOT NULL,
    product_url     TEXT,
    price_value     REAL,
    price_currency  TEXT,
    scraped_at      TEXT NOT NULL  -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_prices_shop_name      ON prices (shop_id, product_name);
CREATE INDEX IF NOT EXISTS idx_prices_scraped_at     ON prices (scraped_at);
CREATE INDEX IF NOT EXISTS idx_prices_shop_scraped   ON prices (shop_id, scraped_at);

CREATE TABLE IF NOT EXISTS product_clusters (
    cluster_id      INTEGER NOT NULL,
    shop_id         TEXT NOT NULL,
    product_name    TEXT NOT NULL,
    canonical_name  TEXT NOT NULL,
    PRIMARY KEY (shop_id, product_name)
);

CREATE INDEX IF NOT EXISTS idx_clusters_cluster ON product_clusters (cluster_id);

-- Convenience view: latest price per shop+product, joined with cluster.
CREATE VIEW IF NOT EXISTS latest_prices AS
SELECT p.shop_id,
       p.product_name,
       p.price_value,
       p.price_currency,
       p.product_url,
       p.scraped_at,
       c.cluster_id,
       c.canonical_name
FROM prices p
LEFT JOIN product_clusters c
  ON c.shop_id = p.shop_id AND c.product_name = p.product_name
WHERE p.id IN (
    SELECT MAX(id) FROM prices GROUP BY shop_id, product_name
);
"""


@dataclass
class PriceRow:
    shop_id: str
    category_url: str
    product_name: str
    product_url: str | None
    price_value: float | None
    price_currency: str | None
    scraped_at: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Storage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def insert_prices(
        self,
        shop_id: str,
        category_url: str,
        products: Iterable[ScrapedProduct],
        scraped_at: str | None = None,
    ) -> int:
        ts = scraped_at or utc_now_iso()
        rows = [
            (
                shop_id,
                category_url,
                p.name,
                p.product_url,
                p.price_value,
                p.price_currency,
                ts,
            )
            for p in products
        ]
        if not rows:
            return 0
        with self.tx() as c:
            c.executemany(
                """
                INSERT INTO prices
                    (shop_id, category_url, product_name, product_url,
                     price_value, price_currency, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def distinct_products(self) -> list[tuple[str, str]]:
        """Return (shop_id, product_name) for every product ever scraped."""
        cur = self.conn.execute(
            "SELECT DISTINCT shop_id, product_name FROM prices ORDER BY shop_id, product_name"
        )
        return [(r["shop_id"], r["product_name"]) for r in cur.fetchall()]

    def replace_clusters(self, rows: list[tuple[int, str, str, str]]) -> None:
        """Replace all cluster assignments.

        rows: list of (cluster_id, shop_id, product_name, canonical_name).
        """
        with self.tx() as c:
            c.execute("DELETE FROM product_clusters")
            if rows:
                c.executemany(
                    """
                    INSERT INTO product_clusters
                        (cluster_id, shop_id, product_name, canonical_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    rows,
                )

    def price_history(self, shop_id: str, product_name: str) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT scraped_at, price_value, price_currency
                FROM prices
                WHERE shop_id = ? AND product_name = ?
                ORDER BY scraped_at
                """,
                (shop_id, product_name),
            )
        )

    def cluster_latest(self, cluster_id: int) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM latest_prices WHERE cluster_id = ? ORDER BY shop_id",
                (cluster_id,),
            )
        )
