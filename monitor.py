"""Bounded, read-only HTTPS probes for public portfolio demonstrations.

Only Python's standard library and curl are required. Responses and stderr are
never published. No browser scripts, transactions or model calls are executed.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit


MAX_AGE = 2700
MAX_BODY = 2 * 1024 * 1024
STATUSES = {"operational", "degraded", "maintenance", "down", "unknown"}
MESSAGES = {
    "operational": "A página e o script principal responderam à checagem.",
    "degraded": "Houve resposta intermitente nesta checagem.",
    "maintenance": "Manutenção programada.",
    "down": "O alvo não respondeu como esperado em duas tentativas.",
    "unknown": "Disponibilidade não confirmada.",
}


def utcnow():
    return datetime.now(timezone.utc)


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Expected an explicit UTC timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def target_id(spec):
    identity = [
        spec.get("url"), spec["role"], "http-content", 1,
        spec.get("marker"), bool(spec.get("entryScript")),
        sorted(spec.get("allowedHosts", [])),
    ]
    digest = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()[:16]
    return f'{spec["id"]}:{digest}'


@dataclass
class Response:
    code: int
    body: bytes
    content_type: str
    url: str
    error: str | None = None


class ModuleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.module = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type") == "module" and attrs.get("src") and not self.module:
            self.module = attrs["src"]


def module_url(response):
    parser = ModuleParser()
    parser.feed(response.body.decode("utf-8", errors="replace"))
    return urljoin(response.url, parser.module) if parser.module else None


def validate_url(url, allowed_hosts):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https" or parsed.hostname not in allowed_hosts
        or parsed.username or parsed.password or parsed.port not in (None, 443)
        or parsed.query or parsed.fragment
    ):
        raise ValueError("Probe URL outside the reviewed HTTPS scope")
    return url


def challenge_title(response):
    return "text/html" in response.content_type and bool(re.search(
        r"<title\b[^>]*>\s*(just a moment|attention required)",
        response.body.decode("utf-8", errors="replace"), re.IGNORECASE,
    ))


def classify(response, spec):
    if response.error:
        unknown = response.error in {
            "collector_error", "unexpected_redirect", "response_too_large", "redirect_limit",
        }
        return {"status": "unknown" if unknown else "down", "reasonCode": response.error}
    if response.code in (401, 403, 429):
        return {"status": "unknown", "reasonCode": "rate_limited" if response.code == 429 else "probe_blocked"}
    if response.code != 200:
        return {"status": "down", "reasonCode": "http_error"}
    text = response.body.decode("utf-8", errors="replace")
    if challenge_title(response):
        return {"status": "unknown", "reasonCode": "probe_blocked"}
    if spec["marker"].casefold() not in text.casefold():
        return {"status": "down", "reasonCode": "content_mismatch"}
    if "text/html" not in response.content_type:
        return {"status": "down", "reasonCode": "content_mismatch"}
    if spec.get("entryScript") and not module_url(response):
        return {"status": "down", "reasonCode": "entry_script_missing"}
    return {"status": "operational", "reasonCode": "ok"}


async def curl_once(url, timeout):
    """The process deadline covers DNS, connection, body and curl shutdown."""
    executable = shutil.which("curl.exe" if os.name == "nt" else "curl")
    if not executable:
        return Response(0, b"", "", url, "collector_error"), None
    with tempfile.TemporaryDirectory(prefix="portfolio-probe-") as directory:
        output = Path(directory) / "body"
        command = [
            executable, "--silent", "--show-error", "--request", "GET",
            "--proto", "=https", "--connect-timeout", str(min(5, timeout)),
            "--max-time", str(timeout), "--max-filesize", str(MAX_BODY),
            "--user-agent", "PortfolioHealth/1.0 (+https://github.com/GuilhermeSerafim/portfolio-health)",
            "--output", str(output), "--write-out", "%{json}", url,
        ]
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            raw, _ = await asyncio.wait_for(process.communicate(), timeout=max(0.01, timeout))
        except (asyncio.TimeoutError, asyncio.CancelledError) as error:
            if process.returncode is None:
                process.kill()
            await process.communicate()
            if isinstance(error, asyncio.CancelledError):
                raise
            return Response(0, b"", "", url, "timeout"), None
        try:
            metadata = json.loads(raw)
        except (ValueError, UnicodeError):
            return Response(0, b"", "", url, "collector_error"), None
        error = {
            6: "dns_error", 7: "connection_error", 28: "timeout",
            35: "tls_error", 60: "tls_error", 63: "response_too_large",
        }.get(process.returncode, "collector_error" if process.returncode else None)
        if output.exists() and output.stat().st_size <= MAX_BODY:
            body = output.read_bytes()
        else:
            body = b""
            if output.exists():
                error = "response_too_large"
        result = Response(
            int(metadata.get("http_code", 0)), body,
            metadata.get("content_type") or "", url, error,
        )
        return result, metadata.get("redirect_url")


async def fetch(url, *, allowed_hosts, timeout):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    try:
        for _ in range(4):
            validate_url(url, allowed_hosts)
            remaining = deadline - loop.time()
            if remaining <= 0:
                return Response(0, b"", "", url, "timeout")
            result, redirect = await curl_once(url, remaining)
            if result.error or not (300 <= result.code < 400) or not redirect:
                return result
            url = urljoin(url, redirect)
        return Response(0, b"", "", url, "redirect_limit")
    except ValueError:
        return Response(0, b"", "", "", "unexpected_redirect")
    except (OSError, TypeError):
        return Response(0, b"", "", "", "collector_error")


async def check_once(spec, *, timeout):
    loop = asyncio.get_running_loop()
    started = loop.time()
    page = await fetch(spec["url"], allowed_hosts=spec["allowedHosts"], timeout=timeout)
    outcome = classify(page, spec)
    outcome["httpStatus"] = page.code if 100 <= page.code <= 599 else None
    outcome["checks"] = ["html-marker"]
    if outcome["status"] != "operational" or not spec.get("entryScript"):
        return outcome
    script_url = module_url(page)
    try:
        validate_url(script_url, spec["allowedHosts"])
    except (ValueError, TypeError):
        return {**outcome, "status": "unknown", "reasonCode": "unexpected_redirect"}
    remaining = timeout - (loop.time() - started)
    if remaining <= 0:
        return {**outcome, "status": "down", "reasonCode": "timeout"}
    script = await fetch(script_url, allowed_hosts=spec["allowedHosts"], timeout=remaining)
    outcome["checks"].append("entry-script")
    if script.error:
        return {**outcome, **classify(script, spec)}
    if script.code in (401, 403, 429):
        return {**outcome, **classify(script, spec)}
    if challenge_title(script):
        return {**outcome, "status": "unknown", "reasonCode": "probe_blocked"}
    valid_js_type = any(mime in script.content_type for mime in ("javascript", "ecmascript"))
    if script.code != 200 or not script.body.strip() or not valid_js_type:
        return {**outcome, "status": "down", "reasonCode": "entry_script_invalid"}
    return outcome


def pending_project(spec):
    return {
        "id": spec["id"], "name": spec["name"], "targetId": target_id(spec),
        "role": spec["role"], "url": spec.get("url"),
        "phase": "pending" if not spec.get("url") else "active",
        "status": "unknown", "reasonCode": "demo_pending" if not spec.get("url") else "not_checked",
        "publicMessage": "Demo pública ainda não cadastrada." if not spec.get("url") else MESSAGES["unknown"],
        "checkedAt": None, "lastSuccessAt": None, "validUntil": None,
        "coverage": "http-content", "components": [], "maintenance": None,
    }


def previous_success(previous, project_id, identity, now):
    if not isinstance(previous, dict):
        return None
    entries = previous.get("projects", [])
    if not isinstance(entries, list):
        return None
    for item in entries:
        if not isinstance(item, dict) or item.get("id") != project_id or item.get("targetId") != identity:
            continue
        try:
            value = parse_time(item["lastSuccessAt"])
            if value <= now:
                return stamp(value)
        except (KeyError, ValueError, TypeError):
            pass
    return None


def active_maintenance(value, now):
    if not isinstance(value, dict):
        return None
    try:
        start, end = parse_time(value["startsAt"]), parse_time(value["endsAt"])
        message = value["message"]
        if start <= now < end and isinstance(message, str) and 0 < len(message) <= 160:
            return {"startsAt": stamp(start), "endsAt": stamp(end), "message": message}
    except (KeyError, ValueError, TypeError):
        pass
    return None


def effective_status(project, now):
    status = project.get("status", "unknown")
    if status not in STATUSES or status == "unknown":
        return "unknown"
    try:
        checked = parse_time(project["checkedAt"])
        until = min(parse_time(project["validUntil"]), checked + timedelta(seconds=MAX_AGE))
        if checked > now + timedelta(minutes=5) or now >= until or until <= checked:
            return "unknown"
        for component in project.get("components", []):
            if effective_status(component, now) == "unknown":
                return "unknown"
    except (KeyError, ValueError, TypeError):
        return "unknown"
    return status


async def probe_project(spec, previous, *, timeout, retry_delay, deadline):
    loop = asyncio.get_running_loop()
    project = pending_project(spec)
    if not spec.get("url"):
        return project
    attempts = 0
    started = loop.time()
    try:
        async with asyncio.timeout_at(deadline):
            first = await check_once(spec, timeout=min(timeout, max(.001, deadline-loop.time())))
            attempts = 1
            result = first
            if first["status"] == "down":
                await asyncio.sleep(retry_delay)
                result = await check_once(spec, timeout=min(timeout, max(.001, deadline-loop.time())))
                attempts = 2
                if result["status"] == "operational":
                    result = {**result, "status": "degraded", "reasonCode": "intermittent"}
    except asyncio.TimeoutError:
        result = {"status": "unknown", "reasonCode": "deadline_exceeded"}
    except Exception:
        result = {"status": "unknown", "reasonCode": "collector_error"}
    checked = utcnow()
    status = result["status"]
    component = {
        "id": "public-entry", "status": status, "reasonCode": result["reasonCode"],
        "checkedAt": stamp(checked), "validUntil": stamp(checked + timedelta(seconds=MAX_AGE)),
        "attempts": attempts, "checks": result.get("checks", []),
        "responseTimeMs": max(0, round((loop.time()-started)*1000)),
        "httpStatus": result.get("httpStatus"),
    }
    success = stamp(checked) if status in {"operational", "degraded"} else previous_success(previous, spec["id"], project["targetId"], checked)
    project.update(
        status=status, reasonCode=result["reasonCode"], publicMessage=MESSAGES[status],
        checkedAt=component["checkedAt"], validUntil=component["validUntil"],
        lastSuccessAt=success, components=[component],
    )
    maintenance = active_maintenance(spec.get("maintenance"), checked)
    if maintenance:
        project.update(maintenance=maintenance, status="maintenance", reasonCode="scheduled_maintenance", publicMessage=maintenance["message"])
    return project


async def collect(specs, previous=None, *, total_timeout=180, timeout=15, retry_delay=30):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + total_timeout
    semaphore = asyncio.Semaphore(4)

    async def run(spec):
        async with semaphore:
            return await probe_project(spec, previous or {}, timeout=timeout, retry_delay=retry_delay, deadline=deadline)

    projects = await asyncio.gather(*(run(spec) for spec in specs))
    return {
        "schemaVersion": 1, "generatedAt": stamp(utcnow()), "maxAgeSeconds": MAX_AGE,
        "source": {
            "provider": "github-actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "local",
            "event": os.environ.get("GITHUB_EVENT_NAME", "local"),
            "runId": os.environ.get("GITHUB_RUN_ID"),
            "commit": os.environ.get("GITHUB_SHA"),
            "observationScope": "single-runner",
        },
        "projects": projects,
    }


def read_targets(path):
    specs = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {"georisk", "seven-tools", "playsenac", "mesa"}
    if not isinstance(specs, list) or len(specs) != 4 or {x["id"] for x in specs} != expected:
        raise ValueError("Expected the four reviewed public project IDs")
    for spec in specs:
        if spec.get("role") not in {"demo", "original"} or not isinstance(spec.get("name"), str):
            raise ValueError("Invalid public target metadata")
        if spec.get("url"):
            validate_url(spec["url"], spec["allowedHosts"])
            if not isinstance(spec.get("marker"), str) or not spec["marker"]:
                raise ValueError("Each active target needs an explicit content marker")
    return specs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", default="targets.json")
    parser.add_argument("--output", default="dist/status.json")
    parser.add_argument("--previous")
    parser.add_argument("--total-timeout", type=float, default=180)
    args = parser.parse_args()
    if not 0 < args.total_timeout <= 180:
        parser.error("total-timeout must be positive and at most 180 seconds")
    previous = {}
    if args.previous:
        try:
            data = Path(args.previous)
            if data.stat().st_size <= 256_000:
                previous = json.loads(data.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    feed = asyncio.run(collect(read_targets(args.targets), previous, total_timeout=args.total_timeout))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(feed, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({item["id"]: {"status": item["status"], "reasonCode": item["reasonCode"]} for item in feed["projects"]}))


if __name__ == "__main__":
    main()
