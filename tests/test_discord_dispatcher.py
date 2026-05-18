import unittest
from contextlib import contextmanager
from unittest import mock

from notifications.discord_dispatcher import build_dispatch_plan, post_discord_webhook


class DiscordDispatcherTests(unittest.TestCase):
    def test_dispatch_plan_is_disabled_without_webhook(self):
        report = {
            "mode": "DISCORD_BEHAVIORAL_INTELLIGENCE_REVIEW_ONLY",
            "discord_events": [{"event_id": "event-1", "message": "hello"}],
        }

        with mock.patch("notifications.discord_dispatcher.urlopen") as mocked_urlopen:
            plan = build_dispatch_plan(report, webhook_url="", send=False)

        self.assertFalse(plan["dispatch_enabled"])
        self.assertEqual(plan["events_ready"], 1)
        self.assertEqual(plan["events_sent"], 0)
        self.assertEqual(plan["events_blocked"], 1)
        mocked_urlopen.assert_not_called()

    def test_dispatch_plan_dry_run_never_posts(self):
        report = {
            "mode": "DISCORD_BEHAVIORAL_INTELLIGENCE_REVIEW_ONLY",
            "discord_events": [{"event_id": "event-1", "message": "hello"}],
        }

        with mock.patch("notifications.discord_dispatcher.urlopen") as mocked_urlopen:
            plan = build_dispatch_plan(report, webhook_url="https://discord.com/api/webhooks/test", send=False)

        self.assertFalse(plan["dispatch_enabled"])
        self.assertEqual(plan["events_ready"], 1)
        self.assertEqual(plan["events_sent"], 0)
        self.assertEqual(plan["events_blocked"], 1)
        self.assertIn("dry_run", plan["block_reasons"])
        mocked_urlopen.assert_not_called()

    def test_dispatch_plan_routes_events_to_channel_webhooks(self):
        report = {
            "mode": "DISCORD_BEHAVIORAL_INTELLIGENCE_REVIEW_ONLY",
            "discord_events": [
                {"event_id": "wallet", "channel": "#wallet-review", "message": "wallet update"},
                {"event_id": "research", "channel": "#research-updates", "message": "research update"},
                {"event_id": "missing", "channel": "#regime-monitor", "message": "regime update"},
            ],
        }

        with mock.patch("notifications.discord_dispatcher.urlopen") as mocked_urlopen:
            mocked_urlopen.return_value.__enter__.return_value.status = 204
            plan = build_dispatch_plan(
                report,
                webhook_url="",
                channel_webhooks={
                    "#wallet-review": "https://discord.com/api/webhooks/wallet",
                    "research-updates": "https://discord.com/api/webhooks/research",
                },
                send=True,
            )

        self.assertTrue(plan["dispatch_enabled"])
        self.assertEqual(plan["events_ready"], 3)
        self.assertEqual(plan["events_sent"], 2)
        self.assertEqual(plan["events_blocked"], 1)
        self.assertEqual(plan["events_failed"], 0)
        self.assertEqual(plan["blocked_events"][0]["event_id"], "missing")
        self.assertEqual(mocked_urlopen.call_count, 2)

    def test_discord_post_uses_discord_compatible_user_agent(self):
        captured_request = None

        @contextmanager
        def fake_urlopen(request, timeout):
            nonlocal captured_request
            captured_request = request
            response = mock.Mock()
            response.status = 204
            yield response

        with mock.patch("notifications.discord_dispatcher.urlopen", side_effect=fake_urlopen):
            status = post_discord_webhook(
                "https://discord.com/api/webhooks/test",
                {"content": "route check"},
            )

        self.assertEqual(status, 204)
        self.assertIsNotNone(captured_request)
        self.assertIn("MemeTraderPro", captured_request.headers.get("User-agent", ""))

    def test_dispatch_plan_skips_already_sent_events(self):
        report = {
            "mode": "DISCORD_BEHAVIORAL_INTELLIGENCE_REVIEW_ONLY",
            "discord_events": [
                {"event_id": "event-1", "channel": "#wallet-review", "message": "already sent"},
                {"event_id": "event-2", "channel": "#wallet-review", "message": "new event"},
            ],
        }

        with mock.patch("notifications.discord_dispatcher.urlopen") as mocked_urlopen:
            mocked_urlopen.return_value.__enter__.return_value.status = 204
            plan = build_dispatch_plan(
                report,
                webhook_url="",
                channel_webhooks={"#wallet-review": "https://discord.com/api/webhooks/wallet"},
                send=True,
                sent_event_ids={"event-1"},
            )

        self.assertTrue(plan["dispatch_enabled"])
        self.assertEqual(plan["events_ready"], 2)
        self.assertEqual(plan["events_sent"], 1)
        self.assertEqual(plan["events_blocked"], 1)
        self.assertEqual(plan["blocked_events"][0]["reason"], "already_sent")
        self.assertEqual(plan["newly_sent_event_ids"], ["event-2"])
        self.assertEqual(mocked_urlopen.call_count, 1)
