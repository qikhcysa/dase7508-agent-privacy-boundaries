"""Per-process credentials and editable settings for the hosted development run."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from typing import Callable
from urllib.parse import urlsplit

from member_a.agent_core.transport import HttpTransport


DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
DEFAULT_MODEL = "glm-5.3-flash"


class ConfigurationCancelled(ValueError):
    """The person closed the credential window without starting a request."""


def prompt_api_key(*, model: str, destination_host: str, environment_key: str,
                   validate_key: Callable[[str], None]) -> str:
    """Show a key-only window; validation does not send requests or save files."""
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except ImportError:
        raise ValueError("The API key window is unavailable; use environment configuration.") from None
    try:
        window = tk.Tk()
    except tk.TclError:
        raise ValueError("The API key window is unavailable; use environment configuration.") from None
    window.withdraw()
    window.title("会议助理 · API 配置")
    window.resizable(False, False)
    window.columnconfigure(0, weight=1)
    frame = ttk.Frame(window, padding=22)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    ttk.Label(frame, text="填写您的 API Key", font=("Microsoft YaHei UI", 13, "bold")).grid(
        row=0, column=0, sticky="w")
    ttk.Label(frame, text=f"模型：{model}\n目标服务器：{destination_host}").grid(row=1, column=0, sticky="w", pady=(8, 12))
    key_value = tk.StringVar(master=window, value="")
    entry = ttk.Entry(frame, textvariable=key_value, show="*", width=58)
    entry.grid(row=2, column=0, sticky="ew")
    help_text = ("已检测到环境变量中的密钥；留空可继续使用。" if environment_key
                 else "请输入您自己的 API Key。")
    ttk.Label(frame, text=help_text).grid(row=3, column=0, sticky="w", pady=(6, 0))
    ttk.Label(frame, text="密钥仅用于本次运行，不会保存到文件或代码仓库。",
              foreground="#555555").grid(row=4, column=0, sticky="w", pady=(5, 14))
    buttons = ttk.Frame(frame)
    buttons.grid(row=5, column=0, sticky="e")
    result: str | None = None

    def cancel() -> None:
        key_value.set("")
        window.destroy()

    def run() -> None:
        nonlocal result
        key = key_value.get().strip() or environment_key
        try:
            validate_key(key)
        except ValueError:
            messagebox.showerror("请检查 API Key", "API Key 不能为空，也不能包含空格或控制字符。",
                                 parent=window)
            entry.focus_set()
            return
        result = key
        key_value.set("")
        window.destroy()

    ttk.Button(buttons, text="取消", command=cancel).grid(row=0, column=0, padx=(0, 10))
    ttk.Button(buttons, text="运行", command=run).grid(row=0, column=1)
    window.protocol("WM_DELETE_WINDOW", cancel)
    window.bind("<Escape>", lambda _event: cancel())
    window.bind("<Return>", lambda _event: run())
    window.update_idletasks()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    x = max(0, (window.winfo_screenwidth() - width) // 2)
    y = max(0, (window.winfo_screenheight() - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")
    window.deiconify()
    window.lift()
    entry.focus_set()
    try:
        window.grab_set()
        window.mainloop()
    finally:
        try:
            window.destroy()
        except tk.TclError:
            pass
    if result is None:
        raise ConfigurationCancelled("API configuration cancelled.")
    return result


def _endpoint(base_url: str) -> str:
    if not isinstance(base_url, str) or not base_url:
        raise ValueError("A service address is required.")
    address = base_url.rstrip("/")
    if address.endswith("/chat/completions"):
        return address
    return address + "/chat/completions"


@dataclass(frozen=True)
class HostedConfig:
    """Settings stay in memory; neither repr nor exported run settings contain keys."""

    api_key: str = field(repr=False)
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = 120
    max_tokens: int = 8192
    max_steps: int = 8
    max_tool_calls: int = 16

    def __post_init__(self) -> None:
        if (not isinstance(self.api_key, str) or not self.api_key
                or any(ord(char) <= 32 or ord(char) == 127 for char in self.api_key)):
            raise ValueError("An API key without whitespace or control characters is required.")
        if (not isinstance(self.model, str) or not 1 <= len(self.model) <= 200
                or any(ord(char) <= 32 or ord(char) == 127 for char in self.model)):
            raise ValueError("A model name without whitespace or control characters is required.")
        try:
            if isinstance(self.timeout, bool):
                raise ValueError
            timeout = float(self.timeout)
        except (TypeError, ValueError):
            raise ValueError("Timeout must be a positive finite number.") from None
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be a positive finite number.")
        object.__setattr__(self, "timeout", timeout)
        for value in (self.max_tokens, self.max_steps, self.max_tool_calls):
            if type(value) is not int or value < 1:
                raise ValueError("Token, step and tool-call limits must be positive integers.")
        # This validates URL, key and timeout without creating a connection.
        # The same transport performs the eventual request in the runtime.
        HttpTransport(self.endpoint, api_key=self.api_key, timeout=timeout)

    @property
    def endpoint(self) -> str:
        return _endpoint(self.base_url)


def configure(*, interactive: bool = True, base_url: str | None = None,
              model: str | None = None, timeout: float = 120,
              max_tokens: int = 8192, max_steps: int = 8,
              max_tool_calls: int = 16) -> HostedConfig:
    """Read environment defaults, optionally showing a key-only desktop window.

    Explicit address/model arguments take precedence over environment defaults.
    Advanced address/model arguments and environment values remain supported.
    The normal window asks only for a masked key and never persists it.
    No files are read or written, and no model request is made here.
    """
    address = base_url if base_url is not None else os.environ.get("AGENT_BASE_URL", DEFAULT_BASE_URL)
    chosen_model = model if model is not None else os.environ.get("AGENT_MODEL", DEFAULT_MODEL)
    # Validate the destination before selecting credentials or opening a dialog.
    validated = HostedConfig(api_key="configuration_validation_only", base_url=address,
                             model=chosen_model, timeout=timeout, max_tokens=max_tokens,
                             max_steps=max_steps, max_tool_calls=max_tool_calls)
    destination = urlsplit(validated.endpoint)
    official_zhipu = (destination.scheme == "https"
                      and destination.hostname == "open.bigmodel.cn"
                      and destination.port in (None, 443))
    key = os.environ.get("AGENT_API_KEY", "")
    if not key and official_zhipu:
        key = os.environ.get("ZAI_API_KEY", "")
    if interactive:
        def validate_key(candidate: str) -> None:
            HostedConfig(api_key=candidate, base_url=address, model=chosen_model, timeout=timeout,
                         max_tokens=max_tokens, max_steps=max_steps, max_tool_calls=max_tool_calls)

        key = prompt_api_key(model=chosen_model, destination_host=destination.netloc,
                             environment_key=key, validate_key=validate_key)
    return HostedConfig(api_key=key, base_url=address, model=chosen_model,
                        timeout=timeout, max_tokens=max_tokens, max_steps=max_steps,
                        max_tool_calls=max_tool_calls)
