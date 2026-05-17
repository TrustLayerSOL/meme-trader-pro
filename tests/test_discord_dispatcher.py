import unittest
from unittest import mock

from notifications.discord_dispatcher import build_dispatch_plan


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

