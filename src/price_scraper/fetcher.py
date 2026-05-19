from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import RequestConfig

log = logging.getLogger(__name__)


# Header set that mimics Chrome on Windows. Many AZ retailers reject default
# python-requests UAs and basic header sets, so we send the full bundle a real
# Chrome navigation would send.
def _browser_headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8,"
            "application/signed-exchange;v=b3;q=0.7"
        ),
        "Accept-Language": "en-US,en;q=0.9,az;q=0.8,ru;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }


class FetchError(RuntimeError):
    pass


@dataclass
class Fetcher:
    """Polite HTTP client with retries and a per-shop rate limit."""

    cfg: RequestConfig
    _last_request_at: float = 0.0

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(_browser_headers(self.cfg.user_agent))

    def _sleep_if_needed(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.cfg.delay_seconds:
            time.sleep(self.cfg.delay_seconds - elapsed)

    def get(self, url: str) -> str:
        self._sleep_if_needed()

        # Some sites refuse if Referer is missing on a deep page hit.
        parts = urlsplit(url)
        headers = {
            "Referer": f"{parts.scheme}://{parts.netloc}/",
            "Sec-Fetch-Site": "same-origin",
        }

        @retry(
            stop=stop_after_attempt(self.cfg.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
            reraise=True,
        )
        def _do() -> requests.Response:
            return self.session.get(url, timeout=self.cfg.timeout, headers=headers)

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
