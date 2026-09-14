"""Bounded Playwright browser runner used by the ``browser_run`` tool."""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class BrowserError(RuntimeError):
    """A browser task violated policy or failed to execute."""

    def __init__(self, message: str, *, reason: str = "browser_error") -> None:
        super().__init__(message)
        self.reason = reason


def browser_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BrowserError(f"browser URL must be http(s) with a host: {url!r}", reason="browser_url_invalid")
    return parsed.hostname


def validate_browser_url(url: str, allowed_hosts: Sequence[str]) -> str:
    host = browser_host(url)
    if host.lower() not in {item.lower() for item in allowed_hosts}:
        raise BrowserError(f"browser host {host!r} is not in the allowlist", reason="browser_host_not_allowed")
    return host


def find_browser_executable(configured: str | None) -> str | None:
    candidate = configured or os.environ.get("EVALPILOT_BROWSER_EXECUTABLE")
    if candidate:
        return candidate
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("msedge"),
        r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    ]
    return next((str(item) for item in candidates if item and Path(item).exists()), None)


def screenshot_path(raw: str, root: Path) -> Path:
    root = root.expanduser().resolve()
    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    if target != root and root not in target.parents:
        raise BrowserError("browser screenshot path escapes the allowed root", reason="browser_path_not_allowed")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target
def _run_browser_sync(
    *,
    url: str,
    actions: Sequence[dict[str, Any]],
    screenshot: str,
    allowed_hosts: Sequence[str],
    screenshot_root: Path,
    timeout_seconds: float = 30.0,
    executable_path: str | None = None,
    headless: bool = True,
) -> dict[str, Any]:
    """Run a bounded browser task and return measured output plus a screenshot."""
    validate_browser_url(url, allowed_hosts)
    if len(actions) > 25:
        raise BrowserError("browser action limit exceeded", reason="browser_too_many_actions")

    output_path = screenshot_path(screenshot, screenshot_root)
    trace_actions: list[dict[str, Any]] = []
    extracted: dict[str, str] = {}
    console_errors: list[str] = []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserError("playwright is not installed", reason="browser_dependency_missing") from exc

    try:
        with sync_playwright() as playwright:
            launch_args: dict[str, Any] = {"headless": headless}
            executable = find_browser_executable(executable_path)
            if executable:
                launch_args["executable_path"] = executable
            browser = playwright.chromium.launch(**launch_args)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.set_default_timeout(timeout_seconds * 1000)
                page.on("pageerror", lambda error: console_errors.append(str(error)))
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
                validate_browser_url(page.url, allowed_hosts)

                for index, raw_action in enumerate(actions):
                    if not isinstance(raw_action, dict):
                        raise BrowserError(f"browser action {index} is not an object", reason="browser_action_invalid")
                    action = str(raw_action.get("action") or "").strip()
                    selector = str(raw_action.get("selector") or "").strip()
                    if action == "goto":
                        target = str(raw_action.get("url") or "").strip()
                        validate_browser_url(target, allowed_hosts)
                        page.goto(target, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
                    elif action == "fill":
                        page.locator(selector).fill(str(raw_action.get("value") or ""))
                    elif action == "click":
                        page.locator(selector).click()
                    elif action == "select":
                        page.locator(selector).select_option(str(raw_action.get("value") or ""))
                    elif action == "press":
                        page.locator(selector).press(str(raw_action.get("key") or "Enter"))
                    elif action == "wait_for":
                        page.locator(selector).wait_for(state=str(raw_action.get("state") or "visible"))
                    elif action == "wait_for_text":
                        expected = str(raw_action.get("text") or "")
                        page.wait_for_function(
                            "text => document.body.innerText.includes(text)",
                            arg=expected,
                            timeout=timeout_seconds * 1000,
                        )
                    elif action == "assert_text":
                        expected = str(raw_action.get("text") or "")
                        if expected not in page.locator("body").inner_text():
                            raise BrowserError(
                                f"browser assertion failed: expected text {expected!r}",
                                reason="browser_assertion_failed",
                            )
                    elif action == "extract_text":
                        name = str(raw_action.get("name") or "answer")
                        extracted[name] = page.locator(selector or "body").inner_text()
                    else:
                        raise BrowserError(f"unsupported browser action: {action!r}", reason="browser_action_unknown")
                    validate_browser_url(page.url, allowed_hosts)
                    trace_actions.append({"index": index, **raw_action, "url": page.url})

                page.screenshot(path=str(output_path), full_page=headless)
                visible_text = page.locator("body").inner_text()[:20000]
                title = page.title()
                final_url = page.url
            finally:
                browser.close()
    except BrowserError:
        raise
    except Exception as exc:
        raise BrowserError(f"browser task failed: {exc}", reason="browser_execution_failed") from exc

    answer = extracted.get("answer") or visible_text
    return {
        "answer": answer,
        "title": title,
        "final_url": final_url,
        "visible_text": visible_text,
        "extracted": extracted,
        "action_trace": trace_actions,
        "console_errors": console_errors,
        "screenshot_path": str(output_path),
        "model": "browser",
        "refused": False,
        "tool_calls": [f"browser.{item['action']}" for item in trace_actions],
    }



def run_browser(
    *,
    url: str,
    actions: Sequence[dict[str, Any]],
    screenshot: str,
    allowed_hosts: Sequence[str],
    screenshot_root: Path,
    timeout_seconds: float = 30.0,
    executable_path: str | None = None,
    headless: bool = True,
) -> dict[str, Any]:
    """Run sync Playwright outside an active asyncio event loop when necessary."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    kwargs = {
        "url": url,
        "actions": actions,
        "screenshot": screenshot,
        "allowed_hosts": allowed_hosts,
        "screenshot_root": screenshot_root,
        "timeout_seconds": timeout_seconds,
        "executable_path": executable_path,
        "headless": headless,
    }
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_browser_sync(**kwargs)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run_browser_sync, **kwargs).result()
