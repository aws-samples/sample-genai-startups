from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse, urlunparse

from .contracts import RetrievedPage


def _evidence_blocks(text: str, *, max_chars: int = 900) -> list[dict[str, str]]:
    blocks: list[str] = []
    for paragraph in re.split(r"\n\s*\n+", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        remaining = paragraph
        while len(remaining) > max_chars:
            boundary = max(
                remaining.rfind("\n", 0, max_chars + 1),
                remaining.rfind(" ", 0, max_chars + 1),
            )
            if boundary <= 0:
                boundary = max_chars
            block = remaining[:boundary].strip()
            if block:
                blocks.append(block)
            remaining = remaining[boundary:].strip()
        if remaining:
            blocks.append(remaining)
    return [
        {"block_id": f"b{index:04d}", "text": block}
        for index, block in enumerate(blocks, start=1)
    ]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            value = unquote(target[0])
            parsed = urlparse(value)
    return urlunparse(parsed._replace(fragment=""))


def _host_allowed(url: str, domains: tuple[str, ...]) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in domains
    )


def _page_id(url: str, content_sha256: str) -> str:
    digest = hashlib.sha256(
        f"{url}\0{content_sha256}".encode("utf-8")
    ).hexdigest()[:20]
    return f"page_{digest}"


@dataclass(frozen=True)
class PageArtifact:
    requested_url: str
    url: str
    title: str
    text: str
    retrieved_at: str
    sha256: str
    page_id: str
    blocks: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrowserOperation:
    operation: str
    started_at: str
    completed_at: str
    input: dict[str, Any]
    output: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _model_page_payload(
    page: PageArtifact,
    *,
    max_chars: int,
) -> dict[str, Any]:
    base = {
        "page_id": page.page_id,
        "url": page.url,
        "title": page.title,
        "retrieved_at": page.retrieved_at,
        "sha256": page.sha256,
    }
    visible_blocks: list[dict[str, str]] = []
    for block in page.blocks:
        candidate = {
            **base,
            "blocks": [*visible_blocks, block],
            "blocks_truncated": True,
        }
        if len(json.dumps(candidate, indent=2)) > max_chars:
            break
        visible_blocks.append(block)
    if not visible_blocks and page.blocks:
        raise RuntimeError("page metadata and one evidence block exceed tool limit")
    return {
        **base,
        "blocks": visible_blocks,
        "blocks_truncated": len(visible_blocks) < len(page.blocks),
    }


class AgentCoreBrowserCapture:
    """Managed Browser session with application-owned evidence capture."""

    def __init__(
        self,
        *,
        region: str,
        allowed_domains: list[str],
        max_searches: int = 8,
        max_page_reads: int = 20,
        max_results_per_search: int = 5,
        model_text_limit: int = 40_000,
    ) -> None:
        self.region = region
        self.allowed_domains = tuple(
            sorted({domain.lower() for domain in allowed_domains})
        )
        self.max_searches = max_searches
        self.max_page_reads = max_page_reads
        self.max_results_per_search = max_results_per_search
        self.model_text_limit = model_text_limit
        self._client: Any = None
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._pages: list[PageArtifact] = []
        self._operations: list[BrowserOperation] = []
        self._searches: list[str] = []
        self._page_cursor = 0
        self._search_cursor = 0
        self._navigation_lock = asyncio.Lock()

    @property
    def session_id(self) -> str | None:
        return None if self._client is None else self._client.session_id

    async def __aenter__(self) -> "AgentCoreBrowserCapture":
        from bedrock_agentcore.tools.browser_client import BrowserClient
        from playwright.async_api import async_playwright

        self._client = BrowserClient(
            self.region,
            integration_source="verified-research-poc",
        )
        self._client.start(
            identifier="aws.browser.v1",
            name="brompton-paired-research-v1",
            session_timeout_seconds=1800,
            viewport={"width": 1280, "height": 900},
        )
        ws_url, headers = self._client.generate_ws_headers()
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(
            ws_url,
            headers=headers,
            timeout=30_000,
        )
        self._context = self._browser.contexts[0]
        self._page = (
            self._context.pages[0]
            if self._context.pages
            else await self._context.new_page()
        )
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()
        finally:
            if self._client is not None:
                self._client.stop()

    async def search_web(self, query: str) -> list[dict[str, str]]:
        async with self._navigation_lock:
            return await self._search_web(query)

    async def _search_web(self, query: str) -> list[dict[str, str]]:
        query = query.strip()
        if not query:
            raise ValueError("search query cannot be empty")
        if len(self._searches) >= self.max_searches:
            raise RuntimeError("registered search cap reached")
        started = _now()
        self._searches.append(query)

        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            response = await self._page.goto(
                search_url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            if response is not None and response.status >= 400:
                raise RuntimeError(
                    f"search endpoint returned HTTP {response.status}"
                )
            results = await self._duckduckgo_results()
        except Exception as error:
            self._operations.append(
                BrowserOperation(
                    operation="search_web",
                    started_at=started,
                    completed_at=_now(),
                    input={"query": query},
                    output={
                        "status": "failed",
                        "error": f"{type(error).__name__}: {error}",
                    },
                )
            )
            raise
        else:
            self._operations.append(
                BrowserOperation(
                    operation="search_web",
                    started_at=started,
                    completed_at=_now(),
                    input={"query": query},
                    output={
                        "status": "completed",
                        "result_count": len(results),
                        "urls": [item["url"] for item in results],
                    },
                )
            )
        return results

    async def _duckduckgo_results(self) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        cards = self._page.locator(".result")
        for index in range(await cards.count()):
            card = cards.nth(index)
            anchor = card.locator("a.result__a").first
            if await anchor.count() == 0:
                continue
            href = await anchor.get_attribute("href")
            if not href:
                continue
            url = _normalize_url(href)
            if url in seen or not _host_allowed(url, self.allowed_domains):
                continue
            title = (await anchor.inner_text()).strip()
            snippet_locator = card.locator(".result__snippet").first
            snippet = (
                (await snippet_locator.inner_text()).strip()
                if await snippet_locator.count()
                else ""
            )
            results.append({"title": title, "url": url, "snippet": snippet})
            seen.add(url)
            if len(results) >= self.max_results_per_search:
                break
        return results

    async def read_page(self, url: str) -> PageArtifact:
        async with self._navigation_lock:
            return await self._read_page(url)

    async def _read_page(self, url: str) -> PageArtifact:
        url = _normalize_url(url.strip())
        if not _host_allowed(url, self.allowed_domains):
            raise ValueError(f"URL is outside the registered source policy: {url}")
        if len(self._pages) >= self.max_page_reads:
            raise RuntimeError("registered page-read cap reached")

        started = _now()
        response = await self._page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        if response is not None and response.status >= 400:
            raise RuntimeError(
                f"page returned HTTP {response.status}: {self._page.url}"
            )
        final_url = _normalize_url(self._page.url)
        if not _host_allowed(final_url, self.allowed_domains):
            raise ValueError(
                "page redirected outside the registered source policy: "
                f"{final_url}"
            )
        title = (await self._page.title()).strip()
        body = self._page.locator("body")
        text = (await body.inner_text(timeout=20_000)).strip()
        if not text:
            raise RuntimeError(f"page returned no readable body text: {final_url}")
        retrieved_at = _now()
        content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        artifact = PageArtifact(
            requested_url=url,
            url=final_url,
            title=title,
            text=text,
            retrieved_at=retrieved_at,
            sha256=content_sha256,
            page_id=_page_id(final_url, content_sha256),
            blocks=tuple(_evidence_blocks(text)),
        )
        self._pages.append(artifact)
        self._operations.append(
            BrowserOperation(
                operation="read_page",
                started_at=started,
                completed_at=retrieved_at,
                input={"url": url},
                output={
                    "url": final_url,
                    "title": title,
                    "characters": len(text),
                    "sha256": artifact.sha256,
                    "page_id": artifact.page_id,
                    "block_count": len(artifact.blocks),
                },
            )
        )
        return artifact

    def drain_pages(self) -> list[RetrievedPage]:
        pages = [
            RetrievedPage(
                url=item.url,
                title=item.title,
                text=item.text,
                page_id=item.page_id,
                blocks={
                    block["block_id"]: block["text"]
                    for block in item.blocks
                },
            )
            for item in self._pages[self._page_cursor :]
        ]
        self._page_cursor = len(self._pages)
        return pages

    def drain_searches(self) -> list[str]:
        searches = self._searches[self._search_cursor :]
        self._search_cursor = len(self._searches)
        return list(searches)

    def artifacts(self) -> list[PageArtifact]:
        return list(self._pages)

    def operations(self) -> list[BrowserOperation]:
        return list(self._operations)

    def page_by_url(self, url: str) -> PageArtifact | None:
        normalized = _normalize_url(url)
        return next(
            (
                page
                for page in reversed(self._pages)
                if page.url == normalized or page.requested_url == normalized
            ),
            None,
        )

    def page_by_id(self, page_id: str) -> PageArtifact | None:
        return next(
            (
                page
                for page in reversed(self._pages)
                if page.page_id == page_id
            ),
            None,
        )

    def tool_server(self, *, search_limit: int) -> Any:
        from claude_agent_sdk import create_sdk_mcp_server, tool
        from mcp.types import ToolAnnotations

        @tool(
            "search_web",
            "Run a focused web search over the registered source domains.",
            {"query": str},
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def search_tool(args: dict[str, Any]) -> dict[str, Any]:
            calls = getattr(search_tool, "calls", 0)
            if calls >= search_limit:
                raise RuntimeError("phase search limit reached")
            search_tool.calls = calls + 1
            results = await self.search_web(args["query"])
            return {
                "content": [
                    {"type": "text", "text": json.dumps(results, indent=2)}
                ]
            }

        @tool(
            "read_page",
            "Read and capture one allowed result page before citing it.",
            {"url": str},
            annotations=ToolAnnotations(
                readOnlyHint=True,
                maxResultSizeChars=self.model_text_limit + 2_000,
            ),
        )
        async def read_tool(args: dict[str, Any]) -> dict[str, Any]:
            page = await self.read_page(args["url"])
            payload = _model_page_payload(
                page,
                max_chars=self.model_text_limit,
            )
            return {
                "content": [
                    {"type": "text", "text": json.dumps(payload, indent=2)}
                ]
            }

        return create_sdk_mcp_server(
            "live_web",
            version="1.0.0",
            tools=[search_tool, read_tool],
        )
