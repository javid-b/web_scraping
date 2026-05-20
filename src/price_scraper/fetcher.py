from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
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
        "Accept-Encoding": "gzip, deflate",
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


# Domains and resource types we never need for scraping — blocking them speeds
# the page up dramatically and stops `networkidle` from waiting forever on
# constantly-polling analytics widgets.
_BLOCK_HOSTS = (
    "google-analytics", "googletagmanager", "googletagservices", "googleadservices",
    "doubleclick", "googlesyndication", "facebook.net", "facebook.com/tr",
    "hotjar", "clarity.ms", "yandex.ru/metrika", "mc.yandex", "metrika",
    "tiktok.com/i18n", "criteo", "snapchat", "twitter.com/i", "x.com/i",
    "intercom", "tawk.to", "livechat", "zendesk", "crisp.chat",
)
_BLOCK_TYPES = {"image", "media", "font"}


def _maybe_block_route(route, request) -> None:  # type: ignore[no-untyped-def]
    url = request.url
    rtype = request.resource_type
    if rtype in _BLOCK_TYPES:
        route.abort()
        return
    if any(host in url for host in _BLOCK_HOSTS):
        route.abort()
        return
    route.continue_()


class FetchError(RuntimeError):
    pass


@dataclass
class Fetcher:
    """Polite HTTP client with retries and a per-shop rate limit.

    Three engines:
      * requests       - plain python-requests session
      * cloudscraper   - mimics Chrome TLS fingerprint, defeats Cloudflare WAF
      * playwright     - real headless Chromium, runs JavaScript before reading
    """

    cfg: RequestConfig
    _last_request_at: float = 0.0
    _engine: str = ""
    _pw: Any = field(default=None, init=False, repr=False)
    _pw_browser: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._engine = (self.cfg.engine or "requests").lower()
        if self._engine == "playwright":
            try:
                import playwright  # noqa: F401
            except ImportError as exc:
                raise FetchError(
                    "engine: playwright requires the 'playwright' package. Run:\n"
                    "    pip install playwright\n"
                    "    playwright install chromium"
                ) from exc
            self.session = None  # type: ignore[assignment]
        elif self._engine == "cloudscraper":
            try:
                import cloudscraper
            except ImportError as exc:
                raise FetchError(
                    "engine: cloudscraper requires the 'cloudscraper' package; "
                    "run `pip install cloudscraper`"
                ) from exc
            self.session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            self.session.headers.update(_browser_headers(self.cfg.user_agent))
        elif self._engine == "requests":
            self.session = requests.Session()
            self.session.headers.update(_browser_headers(self.cfg.user_agent))
        else:
            raise FetchError(f"unknown request.engine: {self.cfg.engine!r}")

    def _sleep_if_needed(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.cfg.delay_seconds:
            time.sleep(self.cfg.delay_seconds - elapsed)

    def _ensure_playwright(self) -> None:
        if self._pw_browser is not None:
            return
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._pw_browser = self._pw.chromium.launch(headless=True)
        log.info("started Playwright browser (chromium, headless)")

    def close(self) -> None:
        """Release the headless browser process. Idempotent."""
        if self._pw_browser is not None:
            try:
                self._pw_browser.close()
            except Exception:  # noqa: BLE001
                pass
            self._pw_browser = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
            self._pw = None

    def __del__(self) -> None:
        self.close()

    def _get_playwright(self, url: str) -> str:
        self._ensure_playwright()
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        ctx = self._pw_browser.new_context(
            user_agent=self.cfg.user_agent,
            extra_http_headers={
                k: v for k, v in _browser_headers(self.cfg.user_agent).items()
                if k.lower() not in {"user-agent", "accept-encoding"}
            },
        )
        page = ctx.new_page()
        try:
            page.route("**/*", _maybe_block_route)
            try:
                page.goto(url, wait_until="load", timeout=self.cfg.timeout * 1000)
            except PlaywrightTimeoutError:
                log.warning(
                    "Playwright goto timeout for %s; proceeding with partial DOM",
                    url,
                )
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except PlaywrightTimeoutError:
                pass
            return page.content()
        finally:
            page.close()
            ctx.close()
            self._last_request_at = time.monotonic()

    def get(self, url: str) -> str:
        self._sleep_if_needed()

        if self._engine == "playwright":
            return self._get_playwright(url)

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

        # If the server insists on an encoding we can't decode (e.g. brotli
        # without the `brotli` package, or zstd), `resp.text` silently returns
        # compressed bytes interpreted as text. Surface that as a clear error.
        enc = resp.headers.get("Content-Encoding", "").lower()
        if enc in {"br", "zstd"}:
            raise FetchError(
                f"server returned Content-Encoding: {enc}, which python-requests "
                f"can't decode by default. Install `brotli` (pip install brotli) "
                f"or remove that codec from Accept-Encoding."
            )

        resp.encoding = resp.apparent_encoding or resp.encoding
        return resp.text
