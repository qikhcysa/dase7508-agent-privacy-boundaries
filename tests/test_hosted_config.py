"""Credential-free checks of hosted configuration and the key-only popup."""

from dataclasses import FrozenInstanceError
import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_privacy.hosted_config import (
    ConfigurationCancelled, DEFAULT_BASE_URL, DEFAULT_MODEL, HostedConfig,
    configure, prompt_api_key,
)


def fake_tk(actions):
    """A toolkit double that runs button callbacks without opening a window."""
    state = SimpleNamespace(variables=[], widgets=[], buttons={}, errors=[], destroyed=False,
                            protocols={})

    class Variable:
        def __init__(self, *, master, value):
            self.value = value
            state.variables.append(self)

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class Widget:
        def __init__(self, kind, *args, **kwargs):
            self.kind, self.options = kind, kwargs
            state.widgets.append(self)
            if kind == "button":
                state.buttons[kwargs["text"]] = kwargs["command"]

        def grid(self, *args, **kwargs):
            pass

        def columnconfigure(self, *args, **kwargs):
            pass

        def focus_set(self):
            pass

    class Window:
        def withdraw(self):
            pass

        def title(self, text):
            state.title = text

        def resizable(self, *args):
            pass

        def columnconfigure(self, *args, **kwargs):
            pass

        def destroy(self):
            state.destroyed = True

        def protocol(self, event, callback):
            state.protocols[event] = callback

        def bind(self, *args):
            pass

        def update_idletasks(self):
            pass

        def winfo_reqwidth(self):
            return 600

        def winfo_reqheight(self):
            return 250

        def winfo_screenwidth(self):
            return 1920

        def winfo_screenheight(self):
            return 1080

        def geometry(self, text):
            state.geometry = text

        def deiconify(self):
            pass

        def lift(self):
            pass

        def grab_set(self):
            pass

        def mainloop(self):
            actions(state)

    ttk = SimpleNamespace(
        Frame=lambda *a, **kw: Widget("frame", *a, **kw),
        Label=lambda *a, **kw: Widget("label", *a, **kw),
        Entry=lambda *a, **kw: Widget("entry", *a, **kw),
        Button=lambda *a, **kw: Widget("button", *a, **kw),
    )
    tk = SimpleNamespace(Tk=Window, TclError=RuntimeError, StringVar=Variable, ttk=ttk,
                         messagebox=SimpleNamespace(showerror=lambda *a, **kw: state.errors.append(a)))
    return tk, state


class HostedConfigTests(unittest.TestCase):
    def test_defaults_hide_key_and_complete_endpoint(self):
        config = HostedConfig(api_key="synthetic_private_key")
        self.assertEqual(config.model, DEFAULT_MODEL)
        self.assertEqual(config.base_url, DEFAULT_BASE_URL)
        self.assertEqual(config.endpoint, DEFAULT_BASE_URL + "chat/completions")
        self.assertNotIn(config.api_key, repr(config))
        self.assertEqual((config.max_tokens, config.max_steps, config.max_tool_calls), (8192, 8, 16))
        with self.assertRaises(FrozenInstanceError):
            config.model = "different"

    def test_base_and_complete_urls_are_normalized_once(self):
        for address in ("https://example.test/v1", "https://example.test/v1/",
                        "https://example.test/v1/chat/completions",
                        "https://example.test/v1/chat/completions/"):
            with self.subTest(address=address):
                self.assertEqual(HostedConfig("synthetic_key", address).endpoint,
                                 "https://example.test/v1/chat/completions")
        self.assertEqual(HostedConfig("synthetic_key", "http://127.0.0.1:8080/v1").endpoint,
                         "http://127.0.0.1:8080/v1/chat/completions")

    def test_environment_and_explicit_overrides_remain_supported(self):
        with patch.dict(os.environ, {"AGENT_API_KEY": "first_synthetic_key",
                                    "ZAI_API_KEY": "second_synthetic_key",
                                    "AGENT_BASE_URL": "https://env.test/v1",
                                    "AGENT_MODEL": "env-model"}, clear=True), \
                patch("agent_privacy.hosted_config.prompt_api_key") as popup:
            config = configure(interactive=False)
            self.assertEqual(config.api_key, "first_synthetic_key")
            self.assertEqual(config.model, "env-model")
            self.assertEqual(config.endpoint, "https://env.test/v1/chat/completions")
            config = configure(interactive=False, base_url="https://override.test/v1", model="other-model")
            self.assertEqual(config.model, "other-model")
            self.assertEqual(config.endpoint, "https://override.test/v1/chat/completions")
        popup.assert_not_called()
        with patch.dict(os.environ, {"ZAI_API_KEY": "fallback_synthetic_key"}, clear=True):
            self.assertEqual(configure(interactive=False).api_key, "fallback_synthetic_key")

    def test_interactive_default_uses_popup_and_presets(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch("agent_privacy.hosted_config.prompt_api_key", return_value="typed_synthetic_key") as popup:
            config = configure()
            self.assertNotIn("AGENT_API_KEY", os.environ)
        self.assertEqual(config.model, DEFAULT_MODEL)
        self.assertEqual(config.base_url, DEFAULT_BASE_URL)
        self.assertEqual(config.api_key, "typed_synthetic_key")
        self.assertEqual(popup.call_args.kwargs["model"], DEFAULT_MODEL)
        popup.call_args.kwargs["validate_key"]("another_synthetic_key")
        with self.assertRaises(ValueError):
            popup.call_args.kwargs["validate_key"]("")

    def test_popup_cancellation_stops_configuration(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch("agent_privacy.hosted_config.prompt_api_key", side_effect=ConfigurationCancelled), \
                self.assertRaises(ConfigurationCancelled):
            configure()

    def test_missing_key_fails_without_gui_when_noninteractive(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch("agent_privacy.hosted_config.prompt_api_key") as popup:
            with self.assertRaises(ValueError):
                configure(interactive=False)
        popup.assert_not_called()

    def test_invalid_addresses_and_keys_never_echo_input(self):
        addresses = ("https://user:synthetic_secret@example.test/v1", "https://example.test/v1?api_key=secret",
                     "https://example.test/v1#secret", "http://example.test/v1", "not-a-url",
                     "https://example.test/\nsecret", "https://example.test:bad/v1")
        for address in addresses:
            with self.subTest(address=address), self.assertRaises(ValueError) as caught:
                HostedConfig("synthetic_key", address)
            self.assertNotIn(address, str(caught.exception))
        for key in ("", "secret\nvalue", "secret value", None):
            with self.subTest(key=key), self.assertRaises(ValueError) as caught:
                HostedConfig(key)
            self.assertNotIn("secret", str(caught.exception).lower())

    def test_invalid_limits_and_advanced_defaults_prevent_popup(self):
        for settings in ({"max_tokens": 0}, {"max_steps": -1}, {"max_tool_calls": True},
                         {"timeout": float("nan")}, {"timeout": float("inf")}, {"timeout": 0},
                         {"model": ""}, {"model": "bad\nmodel"}, {"model": "x" * 201}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                HostedConfig("synthetic_key", **settings)
        with patch.dict(os.environ, {"AGENT_BASE_URL": "https://user:secret@example.test/v1"}, clear=True), \
                patch("agent_privacy.hosted_config.prompt_api_key") as popup, self.assertRaises(ValueError):
            configure()
        popup.assert_not_called()

    def test_popup_has_one_masked_field_and_validates_before_start(self):
        def actions(state):
            self.assertEqual(len(state.variables), 1)
            self.assertEqual(state.variables[0].get(), "")
            entries = [w for w in state.widgets if w.kind == "entry"]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].options["show"], "*")
            self.assertEqual(set(state.buttons), {"运行", "取消"})
            state.variables[0].set("synthetic gui key")
            state.buttons["运行"]()
            self.assertFalse(state.destroyed)
            self.assertEqual(len(state.errors), 1)
            self.assertNotIn("synthetic gui key", str(state.errors))
            state.variables[0].set("synthetic_gui_key")
            state.buttons["运行"]()

        tk, state = fake_tk(actions)
        with patch.dict(sys.modules, {"tkinter": tk}):
            key = prompt_api_key(model=DEFAULT_MODEL, environment_key="",
                                 validate_key=lambda candidate: HostedConfig(candidate))
        self.assertEqual(key, "synthetic_gui_key")
        self.assertTrue(state.destroyed)
        self.assertEqual(state.variables[0].get(), "")
        self.assertFalse(any(DEFAULT_BASE_URL in str(w.options) for w in state.widgets))

    def test_popup_blank_reuses_environment_key_and_clears_widget(self):
        tk, state = fake_tk(lambda state: state.buttons["运行"]())
        with patch.dict(sys.modules, {"tkinter": tk}):
            key = prompt_api_key(model=DEFAULT_MODEL, environment_key="environment_synthetic_key",
                                 validate_key=lambda candidate: HostedConfig(candidate))
        self.assertEqual(key, "environment_synthetic_key")
        self.assertNotIn(key, str([w.options for w in state.widgets]))
        self.assertEqual(state.variables[0].get(), "")

    def test_popup_empty_key_stays_editable_and_cancel_does_not_start(self):
        def actions(state):
            state.buttons["运行"]()
            self.assertFalse(state.destroyed)
            self.assertEqual(len(state.errors), 1)
            state.protocols["WM_DELETE_WINDOW"]()

        tk, _state = fake_tk(actions)
        with patch.dict(sys.modules, {"tkinter": tk}), self.assertRaises(ConfigurationCancelled):
            prompt_api_key(model=DEFAULT_MODEL, environment_key="",
                           validate_key=lambda candidate: HostedConfig(candidate))


if __name__ == "__main__":
    unittest.main()
