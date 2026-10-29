"""Unit tests for Nexus Chaos Monkey (chaos/chaos_monkey.py)."""

import pytest
from unittest.mock import patch, MagicMock
from chaos.chaos_monkey import (
    attack_http_500,
    attack_latency_spike,
    attack_container_kill,
    attack_pause_container,
)


def test_attack_http_500():
    with patch("chaos.chaos_monkey.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        attack_http_500()
        mock_post.assert_called_once()
        assert "/chaos/fail" in mock_post.call_args[0][0]


def test_attack_latency_spike():
    with patch("chaos.chaos_monkey.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        attack_latency_spike()
        mock_post.assert_called_once()
        assert "/chaos/slow" in mock_post.call_args[0][0]


def test_attack_container_kill_fallback():
    with patch("chaos.chaos_monkey.get_target_containers", return_value=[]):
        with patch("chaos.chaos_monkey.requests.post") as mock_post:
            attack_container_kill()
            mock_post.assert_called_once()
            assert "/chaos/crash" in mock_post.call_args[0][0]
