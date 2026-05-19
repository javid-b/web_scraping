from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import RequestConfig

log = logging.getLogger(__name__)


class FetchError(RuntimeError):
    pass


@dataclass
class Fetcher:
    """Polite HTTP client with retries and a per-shop rate limit."""

    cfg: RequestConfig
    _last_request_at: float = 0.0

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.cfg.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,az;q=0.8,ru;q=0.7",
            }
        )

    def _sleep_if_needed(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.cfg.delay_seconds:
            time.sleep(self.cfg.delay_seconds - elapsed)

    def get(self, url: str) -> str:
        self._sleep_if_needed()

        @retry(
            stop=stop_after_attempt(self.cfg.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
            reraise=True,
        )
        def _do() -> requests.Response:
            return self.session.get(url, timeout=self.cfg.timeout)

        try:
            resp = _do()
        except requests.RequestException as exc:
            raise FetchError(f"network error fetching {url}: {exc}") from exc
        finally:
            self._last_request_at = time.monotonic()

        if resp.status_code >= 400:
            raise FetchError(f"HTTP {resp.status_code} for {url}")

        resp.encoding = resp.apparent_encoding or resp.encoding
        return resp.text
