from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.cogs.general.promo import (
    Promo,
    get_full_advert_template,
    get_short_advert_template,
)


class TestPromoFeature(unittest.TestCase):
    def setUp(self) -> None:
        self.bot = MagicMock()
        self.bot.user.name = "Kyoka"
        self.bot.user.display_avatar.url = "https://example.com/avatar.png"
        self.bot.guilds = [MagicMock(), MagicMock()]
        self.bot.users = [MagicMock() for _ in range(500)]
        self.bot.latency = 0.024
        self.cog = Promo(self.bot)

    def test_full_advert_template_includes_all_core_features(self) -> None:
        text = get_full_advert_template(
            bot_name="Kyoka",
            invite_url="https://discord.com/oauth2/authorize?client_id=123",
            support_url="https://discord.gg/7q4tn6dA6V",
            website_url="https://aizen-bot.pages.dev/",
            guilds_count=150,
            users_count=45000,
        )

        # Check core headline
        self.assertIn("KYOKA", text)
        self.assertIn("150", text)
        self.assertIn("45,000", text)

        # Check features
        self.assertIn("STUDIO-GRADE LOSSLESS MUSIC", text)
        self.assertIn("AUTONOMOUS ANTINUKE & ANTI-RAID", text)
        self.assertIn("PRECISION MODERATION", text)
        self.assertIn("+antiping", text)
        self.assertIn("+fakeban", text)
        self.assertIn("BLOX FRUITS & GAMING COMMAND CENTER", text)
        self.assertIn("SERVICE BILLS & REPUTATION LEDGER", text)
        self.assertIn("ENTERPRISE TICKETS, UTILITIES & AUTOMATION", text)

        # Check links
        self.assertIn("https://discord.com/oauth2/authorize?client_id=123", text)
        self.assertIn("https://discord.gg/7q4tn6dA6V", text)
        self.assertIn("https://aizen-bot.pages.dev/", text)

    def test_short_advert_template(self) -> None:
        short_text = get_short_advert_template(
            bot_name="Kyoka",
            invite_url="https://discord.com/invite",
            support_url="https://discord.gg/test",
            website_url="https://aizen-bot.pages.dev/",
        )
        self.assertIn("KYOKA", short_text)
        self.assertIn("Studio-Grade Lossless Music", short_text)
        self.assertIn("Autonomous Antinuke Shield", short_text)
        self.assertIn("Advanced Moderation & Anti-Ping", short_text)
        self.assertIn("Blox Fruits & Gaming Hub", short_text)
        self.assertIn("Service Bills & Vouch Ledger", short_text)

    def test_build_promo_container(self) -> None:
        container = self.cog.build_promo_container(
            bot_name="Kyoka",
            invite_url="https://discord.com/invite",
            support_url="https://discord.gg/test",
            website_url="https://aizen-bot.pages.dev/",
        )
        self.assertIsNotNone(container)
        self.assertTrue(len(container.components) > 0)


if __name__ == "__main__":
    unittest.main()
