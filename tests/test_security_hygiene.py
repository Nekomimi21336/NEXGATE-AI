"""セキュリティ修正の回帰テスト（stdlib のみで動作）。"""

import os
import pathlib
import re
import subprocess
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config_secrets  # noqa: E402
import image_generation_registry  # noqa: E402
import model_registry  # noqa: E402
import search_settings  # noqa: E402


class ProviderKeyEnvPrecedenceTest(unittest.TestCase):
    def test_chat_provider_prefers_env_over_stored(self):
        stored = {"deepseek": {"api_key": "stored-key", "base_url": ""}}
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
            api_key, _ = model_registry.get_provider_credentials("deepseek", stored)
        self.assertEqual(api_key, "env-key")

    def test_image_provider_prefers_env_over_stored(self):
        stored = {"flux_bfl": {"api_key": "stored-key", "base_url": ""}}
        with mock.patch.dict(os.environ, {"BFL_API_KEY": "env-key"}):
            api_key, _ = image_generation_registry.get_image_provider_credentials(
                "flux_bfl", stored
            )
        self.assertEqual(api_key, "env-key")


class ConfigSecretsTest(unittest.TestCase):
    def test_env_names_match_oauth_modules(self):
        fields = dict(
            (sec, field) for sec, field, _ in config_secrets.SENSITIVE_FILE_FIELDS
        )
        google_envs = next(
            envs
            for sec, field, envs in config_secrets.SENSITIVE_FILE_FIELDS
            if sec == "google_oauth" and field == "client_secret"
        )
        discord_envs = next(
            envs
            for sec, field, envs in config_secrets.SENSITIVE_FILE_FIELDS
            if sec == "discord_oauth" and field == "client_secret"
        )
        self.assertEqual(google_envs, ("GOOGLE_CLIENT_SECRET",))
        self.assertEqual(discord_envs, ("DISCORD_CLIENT_SECRET",))

    def test_resolve_secret_prefers_env(self):
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "env-key"}):
            self.assertEqual(
                config_secrets.resolve_secret(("TAVILY_API_KEY",), "file-key"),
                "env-key",
            )

    def test_resolve_secret_falls_back_to_file(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                config_secrets.resolve_secret(("TAVILY_API_KEY",), "file-key"),
                "file-key",
            )


class SearchSettingsTest(unittest.TestCase):
    def test_merge_does_not_store_key_when_env_set(self):
        current = {"tavily_api_key": "current-key", "tavily_enabled": True}
        incoming = {"tavily_api_key": "incoming-key", "tavily_enabled": True}
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "env-key"}):
            merged = search_settings.merge_search_engines_config(incoming, current)
        self.assertEqual(merged["tavily_api_key"], "current-key")

    def test_merge_stores_key_when_env_missing(self):
        current = {"tavily_api_key": "current-key", "tavily_enabled": True}
        incoming = {"tavily_api_key": "incoming-key", "tavily_enabled": True}
        with mock.patch.dict(os.environ, {}, clear=True):
            merged = search_settings.merge_search_engines_config(incoming, current)
        self.assertEqual(merged["tavily_api_key"], "incoming-key")


class NoHardcodedSecretTest(unittest.TestCase):
    def test_no_insecure_flask_secret_fallback(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("nexgate-dev-secret-change-me", src)
        self.assertIn("FLASK_SECRET_KEY", src)


class NoSecretsInRepositoryTest(unittest.TestCase):
    """コミット対象に API キー等が紛れていないことを確認する。"""

    TOKEN_PATTERNS = (
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
        re.compile(r"sk-proj-[A-Za-z0-9_-]{16,}"),
        re.compile(r"csk-[A-Za-z0-9_-]{16,}"),
        re.compile(r"tvly-[A-Za-z0-9_-]{10,}"),
        re.compile(r"bfl_[A-Za-z0-9_-]{10,}"),
        re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    )

    def _tracked_files(self):
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            return [ROOT / rel for rel in result.stdout.splitlines()]
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git ls-files を実行できないためスキップ")

    def test_no_secret_tokens_in_tracked_source(self):
        hits = []
        for path in self._tracked_files():
            if not path.is_file():
                continue
            if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf"):
                continue
            try:
                raw = path.read_bytes()
                if b"\x00" in raw[:2048]:
                    continue
                text = raw.decode("utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for pattern in self.TOKEN_PATTERNS:
                    if pattern.search(line):
                        hits.append(f"{path.relative_to(ROOT)}:{lineno}")
                        break
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
