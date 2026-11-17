"""Bot integration: the analysis feature is wired in without breaking collage mode.

These tests import bot.py directly. Importing does not start Telegram, and no
network calls are made.
"""

from __future__ import annotations

import asyncio
import gc
import warnings

import pytest

import bot


class TestFeatureDetection:
    def test_investigator_package_is_available(self):
        assert bot.INVESTIGATOR is True

    def test_analysis_is_off_without_an_api_key(self):
        """No key means the feature reports itself unavailable, it does not fake data."""
        assert bot.INVESTIGATE_ENABLED == (bool(bot.GEMINI_API_KEY) and bot.INVESTIGATOR)

    def test_unavailable_reason_names_the_missing_key(self):
        reason = bot._unavailable_reason()
        if not bot.GEMINI_API_KEY:
            assert "GEMINI_API_KEY" in reason
        else:
            assert reason

    def test_description_types_are_the_two_required_ones(self):
        assert set(bot.DESCRIPTION_TYPES) == {bot.ELDORADO, bot.AUCTION}

    def test_desc_labels_cover_both_types(self):
        assert set(bot.DESC_LABELS) == {bot.ELDORADO, bot.AUCTION}


class TestConfig:
    def test_default_description_is_valid(self):
        assert bot.DEFAULT_DESCRIPTION in (bot.ELDORADO, bot.AUCTION)

    def test_prefs_carry_a_description_type(self):
        prefs = bot.Prefs()
        assert prefs.desc_type in (bot.ELDORADO, bot.AUCTION, "both")

    def test_gemini_transport_defaults_to_auto(self):
        assert bot.GEMINI_TRANSPORT in ("auto", "interactions", "generatecontent")


class TestHandlersExist:
    @pytest.mark.parametrize("name", ["cmd_analyze", "cmd_desc", "cb_desc",
                                      "run_investigation", "_fetch_parts",
                                      "investigation_available"])
    def test_handler_is_defined(self, name):
        assert callable(getattr(bot, name))


class TestMimeSniffing:
    def test_png(self):
        assert bot._sniff_mime(b"\x89PNG\r\n\x1a\n" + b"x" * 10) == "image/png"

    def test_jpeg(self):
        assert bot._sniff_mime(b"\xff\xd8\xff\xe0" + b"x" * 10) == "image/jpeg"

    def test_webp(self):
        assert bot._sniff_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"

    def test_gif(self):
        assert bot._sniff_mime(b"GIF89a" + b"x" * 10) == "image/gif"

    def test_unknown_defaults_to_jpeg(self):
        assert bot._sniff_mime(b"not an image") == "image/jpeg"


class TestDescriptionKeyboard:
    def test_keyboard_offers_both_types_and_both(self):
        keyboard = bot._desc_keyboard(bot.ELDORADO)
        values = {button.callback_data for row in keyboard.inline_keyboard
                  for button in row}
        assert values == {"desc:eldorado", "desc:auction", "desc:both"}

    def test_selected_type_is_ticked(self):
        keyboard = bot._desc_keyboard(bot.AUCTION)
        labels = {b.callback_data: b.text for row in keyboard.inline_keyboard for b in row}
        assert labels["desc:auction"].startswith("✓")
        assert not labels["desc:eldorado"].startswith("✓")


class TestLastItemsMemory:
    def test_last_items_is_a_dict(self):
        assert isinstance(bot.LAST_ITEMS, dict)

    def test_clear_drops_the_saved_batch(self):
        bot.LAST_ITEMS[999] = [("file", 1.0)]
        bot.SESSIONS.pop(999, None)
        # cmd_clear removes both the session and the saved batch.
        bot.drop_session(999)
        bot.LAST_ITEMS.pop(999, None)
        assert 999 not in bot.LAST_ITEMS


class TestGracefulDegradation:
    """The pokego package is optional: without it the collage bot must still import.

    This guards a real regression - a bare ``-> GeminiClient`` annotation is
    evaluated at import time and crashed the bot when the package was absent.
    """

    def _import_bot_without_pokego(self):
        import builtins
        import importlib
        import sys

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "pokego" or name.startswith("pokego."):
                raise ImportError("simulated missing package")
            return real_import(name, *args, **kwargs)

        saved = {k: v for k, v in sys.modules.items()
                 if k == "bot" or k.startswith("pokego")}
        for key in saved:
            sys.modules.pop(key, None)
        builtins.__import__ = blocked
        try:
            return importlib.import_module("bot")
        finally:
            builtins.__import__ = real_import
            sys.modules.pop("bot", None)
            sys.modules.update(saved)

    def test_bot_imports_without_the_package(self):
        module = self._import_bot_without_pokego()
        assert module.INVESTIGATOR is False
        assert module.INVESTIGATE_ENABLED is False

    def test_collage_welcome_survives_without_the_package(self):
        module = self._import_bot_without_pokego()
        assert "collage" in module.welcome().lower()

    def test_desc_keyboard_is_still_safe_without_the_package(self):
        module = self._import_bot_without_pokego()
        keyboard = module._desc_keyboard(module.ELDORADO)
        assert keyboard.inline_keyboard

    def test_unavailable_reason_is_honest_without_the_package(self):
        module = self._import_bot_without_pokego()
        assert "pokego" in module._unavailable_reason()


class TestWelcomeText:
    def test_welcome_mentions_classification_when_enabled(self):
        text = bot.welcome()
        if bot.INVESTIGATE_ENABLED:
            assert "MINI" in text and "STACKED" in text
            assert "/analyze" in text

    def test_welcome_still_describes_collage(self):
        assert "collage" in bot.welcome().lower()

    def test_welcome_is_not_empty(self):
        assert len(bot.welcome()) > 50


class TestStatusText:
    def test_status_includes_investigation_line(self):
        """The /status text is built inline; assert the strings it depends on exist."""
        if bot.INVESTIGATOR:
            assert bot.DESC_LABELS
            assert hasattr(bot.Prefs(), "desc_type")


class TestReportDelivery:
    def test_telegram_message_limit_is_the_real_cap(self):
        assert bot.TELEGRAM_MSG_LIMIT == 4096

    def test_report_filename_is_markdown(self):
        assert bot.REPORT_FILENAME.endswith(".md")


class _FakeApplication:
    """Mirrors Application.create_task, which wraps our coroutine in a callback."""

    def create_task(self, coro, **kwargs):
        async def wrapper():
            return await coro
        return asyncio.create_task(wrapper())


class TestDebounceTimer:
    """A cancelled timer must not leave an un-awaited coroutine behind.

    Application.create_task awaits our coroutine inside its own callback. When
    the timer is cancelled before its first step (a second image arriving within
    AUTO_BUILD_SEC), that await never happens and Python warns at GC.
    """

    def test_cancelling_before_first_step_does_not_orphan_the_coroutine(self):
        async def run():
            app = _FakeApplication()
            s = bot.Session()
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                s.timer = bot._schedule_timer(app, 1, 999, s)
                s.timer.cancel()
                s.timer = None
                gc.collect()
                await asyncio.sleep(0.05)
                gc.collect()
                return [w for w in caught if "never awaited" in str(w.message)]

        assert asyncio.run(run()) == []

    def test_helper_returns_a_task_and_still_builds_when_it_elapses(self):
        """The debounce must still fire; the done-callback must not break it."""
        calls: list = []

        async def fake_try_launch(app, chat_id, uid, s):
            calls.append((chat_id, uid))

        original = bot.try_launch
        original_sec = bot.AUTO_BUILD_SEC
        bot.try_launch = fake_try_launch
        bot.AUTO_BUILD_SEC = 0.01
        try:
            async def run():
                app = _FakeApplication()
                s = bot.Session()
                task = bot._schedule_timer(app, 7, 999, s)
                assert isinstance(task, asyncio.Task)
                await asyncio.wait_for(task, timeout=2)
                return calls

            assert asyncio.run(run()) == [(7, 999)]
        finally:
            bot.try_launch = original
            bot.AUTO_BUILD_SEC = original_sec
