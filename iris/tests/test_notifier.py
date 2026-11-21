"""Testes unitários de supressão e disparo do módulo de notificações (Toast e NTFY)."""

import os
import subprocess
import sys
import urllib.request
from unittest.mock import MagicMock

import pytest

from src.modules.timelapse import notifier


class _ImmediateThread:
    """Substituto síncrono de threading.Thread para testar o corpo das threads sem concorrência."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


def test_pytest_disables_notifications_by_default():
    """Garante que o conftest.py mantém IRIS_DISABLE_NOTIFICATIONS='1' ativo durante o pytest."""
    assert os.environ.get("IRIS_DISABLE_NOTIFICATIONS") == "1"


@pytest.mark.parametrize("env_value", ["1", "true", "TRUE", "yes", "on"])
def test_notifications_suppressed_when_env_disabled(monkeypatch, env_value):
    """Garante que nenhuma thread, requisição HTTP ou processo PowerShell é disparado quando suprimido."""
    monkeypatch.setenv("IRIS_DISABLE_NOTIFICATIONS", env_value)
    monkeypatch.setattr(notifier.sys, "platform", "win32")

    thread_spy = MagicMock()
    urlopen_spy = MagicMock()
    run_spy = MagicMock()

    monkeypatch.setattr(notifier.threading, "Thread", thread_spy)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen_spy)
    monkeypatch.setattr(subprocess, "run", run_spy)

    notifier.send_ntfy_notification(topic="test-topic", title="T", message="M", tags=["sparkles"], actions=["view, X, https://x"])
    notifier.send_windows_toast(title="Toast", message="Body")
    notifier.notify_timelapse_render_done(project_name="proj", video_name="vid.mp4", topic="test-topic", enable_toast=True)

    thread_spy.assert_not_called()
    urlopen_spy.assert_not_called()
    run_spy.assert_not_called()


def test_notifications_enabled_dispatches_ntfy_and_toast_with_mocks(monkeypatch):
    """Garante que com IRIS_DISABLE_NOTIFICATIONS ausente ambos os canais são acionados corretamente (via mocks)."""
    monkeypatch.delenv("IRIS_DISABLE_NOTIFICATIONS", raising=False)
    monkeypatch.setattr(notifier.sys, "platform", "win32")
    monkeypatch.setattr(notifier.threading, "Thread", _ImmediateThread)

    urlopen_cm = MagicMock()
    urlopen_cm.__enter__ = MagicMock(return_value=urlopen_cm)
    urlopen_cm.__exit__ = MagicMock(return_value=False)
    urlopen_spy = MagicMock(return_value=urlopen_cm)
    run_spy = MagicMock()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen_spy)
    monkeypatch.setattr(subprocess, "run", run_spy)

    notifier.notify_timelapse_render_done(
        project_name="proj_teste",
        video_name="video.mp4",
        details="4K UHD",
        topic="iris-test-topic",
        enable_toast=True,
    )

    assert urlopen_spy.call_count == 1
    req = urlopen_spy.call_args[0][0]
    assert req.full_url == "https://ntfy.sh/iris-test-topic"
    assert req.get_method() == "POST"

    assert run_spy.call_count == 1
    cmd_args = run_spy.call_args[0][0]
    assert cmd_args[0] == "powershell"


def test_windows_toast_skipped_on_non_win32_even_when_enabled(monkeypatch):
    """Em sistemas não-Windows, send_windows_toast não executa subprocesso mesmo se habilitado."""
    monkeypatch.delenv("IRIS_DISABLE_NOTIFICATIONS", raising=False)
    monkeypatch.setattr(notifier.sys, "platform", "linux")

    thread_spy = MagicMock()
    monkeypatch.setattr(notifier.threading, "Thread", thread_spy)

    notifier.send_windows_toast("Titulo", "Mensagem")
    thread_spy.assert_not_called()
