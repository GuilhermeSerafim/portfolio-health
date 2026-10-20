import asyncio
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import monitor


NOW = datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc)
SPEC = {
    "id": "georisk", "name": "OrbTalus", "role": "demo",
    "url": "https://demo.example/", "marker": "OrbTalus",
    "allowedHosts": ["demo.example"], "entryScript": True,
}
HTML = b'<title>OrbTalus</title><script type="module" src="./app.mjs"></script>'


def response(code=200, body=HTML, content_type="text/html", url="https://demo.example/"):
    return monitor.Response(code, body, content_type, url)


class PolicyTests(unittest.TestCase):
    def test_blocked_probe_is_unknown_not_down(self):
        for code in (401, 403, 429):
            result = monitor.classify(response(code), SPEC)
            self.assertEqual(result["status"], "unknown", code)

    def test_normal_cloudflare_injection_does_not_hide_valid_content(self):
        html = HTML + b'<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
        self.assertEqual(monitor.classify(response(body=html), SPEC)["status"], "operational")

    def test_challenge_and_wrong_200_content_are_distinct(self):
        challenge = response(body=b"<title>Just a moment...</title>")
        self.assertEqual(monitor.classify(challenge, SPEC)["status"], "unknown")
        wrong = response(body=b"<title>Not found</title>")
        self.assertEqual(monitor.classify(wrong, SPEC)["status"], "down")

    def test_incomplete_document_cannot_pass_without_entry_script(self):
        self.assertEqual(
            monitor.classify(response(body=b"<title>OrbTalus</title>"), SPEC)["status"],
            "down",
        )

    def test_pending_target_has_no_made_up_timestamp(self):
        item = monitor.pending_project({"id": "seven-tools", "name": "SEVEN Tools", "role": "demo"})
        self.assertEqual(item["status"], "unknown")
        self.assertEqual(item["reasonCode"], "demo_pending")
        self.assertIsNone(item["checkedAt"])
        self.assertIsNone(item["url"])

    def test_fresh_generation_does_not_renew_expired_probe(self):
        project = {
            "status": "operational", "checkedAt": "2026-10-20T17:00:00Z",
            "validUntil": "2026-10-20T19:00:00Z", "components": [],
        }
        self.assertEqual(monitor.effective_status(project, NOW), "unknown")

    def test_unknown_component_and_future_timestamp_prevent_green(self):
        project = {
            "status": "operational", "checkedAt": "2026-10-20T18:00:00Z",
            "validUntil": "2026-10-20T18:45:00Z",
            "components": [{"status": "unknown", "checkedAt": None, "validUntil": None}],
        }
        self.assertEqual(monitor.effective_status(project, NOW), "unknown")
        project["components"] = []
        project["checkedAt"] = "2026-10-20T18:10:00Z"
        self.assertEqual(monitor.effective_status(project, NOW), "unknown")

    def test_redirect_cannot_escape_origin_or_include_credentials(self):
        for url in ("https://private.example/x", "http://demo.example/", "https://user:pass@demo.example/"):
            with self.assertRaises(ValueError):
                monitor.validate_url(url, SPEC["allowedHosts"])

    def test_changed_target_does_not_inherit_last_success(self):
        prior = {"projects": [{"id": "georisk", "targetId": "old", "lastSuccessAt": "2026-10-20T17:00:00Z"}]}
        self.assertIsNone(monitor.previous_success(prior, "georisk", "new", NOW))

    def test_history_accepts_only_valid_past_success_for_same_target(self):
        prior = {"projects": [{"id": "georisk", "targetId": "same", "lastSuccessAt": "2026-10-20T17:00:00Z"}]}
        self.assertEqual(monitor.previous_success(prior, "georisk", "same", NOW), "2026-10-20T17:00:00Z")
        prior["projects"][0]["lastSuccessAt"] = "2026-10-21T17:00:00Z"
        self.assertIsNone(monitor.previous_success(prior, "georisk", "same", NOW))

    def test_malformed_history_is_ignored_instead_of_breaking_new_snapshot(self):
        self.assertIsNone(monitor.previous_success({"projects": 3}, "georisk", "same", NOW))

    def test_expired_maintenance_does_not_override_observation(self):
        maintenance = {
            "startsAt": "2026-10-20T16:00:00Z", "endsAt": "2026-10-20T17:00:00Z",
            "message": "Scheduled update",
        }
        self.assertIsNone(monitor.active_maintenance(maintenance, NOW))


class CollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_deadline_terminates_the_owned_process(self):
        real_spawn = asyncio.create_subprocess_exec
        spawned = []

        async def sleeper(*args, **kwargs):
            process = await real_spawn(sys.executable, "-c", "import time; time.sleep(10)", **kwargs)
            spawned.append(process)
            return process

        with patch.object(monitor.asyncio, "create_subprocess_exec", side_effect=sleeper):
            result, redirect = await monitor.curl_once("https://demo.example/", 0.05)
        self.assertEqual(result.error, "timeout")
        self.assertIsNotNone(spawned[0].returncode)

    async def test_transport_refuses_redirect_before_second_host_request(self):
        async def redirect(url, timeout):
            if url != "https://demo.example/":
                self.fail("Transport escaped the allowlist")
            return response(code=302), "https://private.example/path"

        with patch.object(monitor, "curl_once", side_effect=redirect):
            result = await monitor.fetch("https://demo.example/", allowed_hosts=["demo.example"], timeout=1)
        self.assertEqual(result.error, "unexpected_redirect")

    async def test_two_failures_required_and_recovery_is_degraded(self):
        with patch.object(monitor, "check_once", side_effect=[
            {"status": "down", "reasonCode": "http_error"},
            {"status": "operational", "reasonCode": "ok"},
        ]):
            item = await monitor.probe_project(SPEC, {}, timeout=1, retry_delay=0, deadline=asyncio.get_running_loop().time()+2)
        self.assertEqual(item["status"], "degraded")
        self.assertEqual(item["reasonCode"], "intermittent")
        self.assertIsNotNone(item["lastSuccessAt"])

    async def test_two_http_failures_report_down_with_real_check_time(self):
        with patch.object(monitor, "check_once", return_value={"status": "down", "reasonCode": "http_error"}):
            item = await monitor.probe_project(SPEC, {}, timeout=1, retry_delay=0, deadline=asyncio.get_running_loop().time()+2)
        self.assertEqual(item["status"], "down")
        self.assertIsNotNone(item["checkedAt"])
        self.assertIsNone(item["lastSuccessAt"])
        self.assertEqual(item["components"][0]["attempts"], 2)

    async def test_total_deadline_returns_unknown_and_pending_without_waiting_for_probe(self):
        async def hung(*args, **kwargs):
            await asyncio.sleep(10)
        with patch.object(monitor, "check_once", side_effect=hung):
            feed = await monitor.collect([SPEC, {"id": "playsenac", "name": "Play", "role": "demo"}], total_timeout=0.03)
        self.assertEqual(feed["projects"][0]["status"], "unknown")
        self.assertEqual(feed["projects"][0]["reasonCode"], "deadline_exceeded")
        self.assertEqual(feed["projects"][1]["phase"], "pending")

    async def test_entry_script_html_fallback_is_not_healthy(self):
        async def get(url, **kwargs):
            if url.endswith(".mjs"):
                return response(body=b"<html>Fallback</html>", url=url)
            return response()
        with patch.object(monitor, "fetch", side_effect=get):
            result = await monitor.check_once(SPEC, timeout=1)
        self.assertEqual(result["status"], "down")
        self.assertEqual(result["reasonCode"], "entry_script_invalid")

    async def test_external_entry_script_is_not_fetched(self):
        external = b'<title>OrbTalus</title><script type="module" src="https://external.example/paid.js"></script>'
        with patch.object(monitor, "fetch", return_value=response(body=external)):
            result = await monitor.check_once(SPEC, timeout=1)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reasonCode"], "unexpected_redirect")

    async def test_healthy_document_and_script_have_limited_coverage(self):
        async def get(url, **kwargs):
            return response(body=b"export const ok = true;", content_type="text/javascript", url=url) if url.endswith(".mjs") else response()
        with patch.object(monitor, "fetch", side_effect=get):
            feed = await monitor.collect([SPEC], total_timeout=2)
        item = feed["projects"][0]
        self.assertEqual(item["status"], "operational")
        self.assertEqual(item["coverage"], "http-content")
        self.assertEqual(item["components"][0]["checks"], ["html-marker", "entry-script"])
        self.assertEqual(feed["source"]["observationScope"], "single-runner")


if __name__ == "__main__":
    unittest.main()
