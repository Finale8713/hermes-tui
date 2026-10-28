#!/usr/bin/env python3
"""Rerun terminal regressions in a scratch profile, without installs or live DB writes.

Portable across macOS, Linux, and Windows. The interpreter comes from the published
hermes launcher via --print-runtime-command; pytest is discovered read-only across
per-OS site-packages roots. When no root carries pytest this exits 2 with the one
sanctioned remedy instead of installing anything.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = [
    "tests/agent/test_platform_hint_cli_code.py",
    "tests/agent/test_platform_hint_overrides.py",
    "tests/agent/test_platform_hint_desktop.py",
    "tests/agent/test_platform_hint_cron_delivery.py",
    "tests/hermes_cli/test_cli_code_blocks.py",
    "tests/hermes_cli/test_cli_status_bar_cost.py",
    "tests/hermes_state/test_cost_coverage.py",
    "tests/hermes_state/test_aux_usage_accounting.py",
    "tests/hermes_state/test_session_model_usage_pk_heal.py",
    "tests/agent/test_async_token_accounting.py",
    "tests/hermes_cli/test_cli_status_bar.py",
    "tests/hermes_cli/test_cli_status_bar_goal.py",
    "tests/hermes_cli/test_status_bar_git_branch.py",
    "tests/hermes_state/test_hermes_state.py",
    "tests/hermes_cli/test_stream_delta_think_tag.py",
    "tests/hermes_cli/test_stream_partial_line_flush.py",
    "tests/hermes_cli/test_stream_flush_left.py",
    "tests/hermes_cli/test_transformed_stream_output.py",
    "tests/hermes_cli/test_status_lines_held_during_stream_box.py",
    "tests/hermes_cli/test_cli_markdown_rendering.py",
    "tests/hermes_cli/test_clipboard_text_write.py",
    "tests/agent/test_strip_reasoning_tags_cli.py",
    "tests/agent/test_missing_usage_accounting.py",
    "tests/agent/test_turn_usage_log_line.py",
    "tests/agent/test_turn_finalizer_cleanup_guard.py",
    "tests/agent/test_usage_pricing.py",
    "tests/agent/test_usage_pricing_tiers.py",
]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=None,
                        help="checkout to verify (default: $HERMES_HOME/hermes-agent, else ~/.hermes/hermes-agent)")
    parser.add_argument("--python", type=Path, default=None,
                        help="explicit interpreter; skips launcher discovery")
    parser.add_argument("--pytest-root", type=Path, default=None,
                        help="explicit site-packages root carrying pytest; skips discovery")
    parser.add_argument("--home", choices=("scratch", "real"), default="scratch",
                        help="HOME policy for the test child. scratch (default, the recorded "
                             "harness semantics) fully isolates HOME: the 19 known "
                             "test_cli_modern_layout.py import-gap failures are expected in "
                             "this environment (recorded 2026-10-21). real keeps the real HOME, "
                             "which passes the layout imports but trips 4 agent-side logging "
                             "tests (hermes_logging _known_log_homes realpaths a handler under "
                             "the child HERMES_HOME, and the home-I/O guard refuses) on this tree.")
    parser.add_argument("--list-roots", action="store_true",
                        help="print the discovery inputs and pytest roots, then exit")
    return parser.parse_args(argv)


def hermes_home():
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


def launcher_path(home, repo):
    found = shutil.which("hermes")
    if found:
        return Path(found)
    candidates = [home / ".local/bin/hermes", repo / ".hermes/bin/hermes"]
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "hermes" / "bin" / "hermes.cmd")
            candidates.append(Path(local) / "hermes" / "bin" / "hermes.exe")
        candidates.append(repo / ".hermes" / "bin" / "hermes.cmd")
        candidates.append(repo / ".hermes" / "bin" / "hermes.exe")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def runtime_interpreter(launcher):
    command = subprocess.run([str(launcher), "--print-runtime-command"],
                             check=True, capture_output=True, text=True)
    return Path(json.loads(command.stdout)[0])

def committed_env_exists(home, repo):
    """pm scopes a checkout's dependency state by sha256(path)[:16]
    (pm/environments.py:20-22); without a committed facts.json the pinned
    store interpreter's bootstrap refuses the checkout outright
    (NoCommittedEnvironment)."""
    key = hashlib.sha256(str(repo).encode("utf-8")).hexdigest()[:16]
    return (home / "installs" / key / "facts.json").is_file()


def venv_interpreter(repo):
    """The repo's own dev-synced .venv interpreter: the blessed interpreter for
    gating a checkout pm has not committed an environment for."""
    for candidate in (repo / ".venv" / "bin" / "python3",
                      repo / ".venv" / "bin" / "python",
                      repo / ".venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return candidate
    return None


def uv_cache_roots(home):
    explicit = os.environ.get("UV_CACHE_DIR")
    if explicit:
        return [Path(explicit)]
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        return [Path(local) / "uv" / "cache"] if local else []
    if sys.platform == "darwin":
        return [home / "Library" / "Caches" / "uv"]
    xdg = os.environ.get("XDG_CACHE_HOME") or str(home / ".cache")
    return [Path(xdg) / "uv"]


def site_packages(venv):
    return [p for p in [*venv.glob("lib/python*/site-packages"),
                        *venv.glob("Lib/site-packages")] if p.is_dir()]


def pytest_roots(home, repo):
    roots = list(site_packages(repo / ".venv"))
    for cache in uv_cache_roots(home):
        for archive in cache.glob("archive-v0/*"):
            roots += site_packages(archive)
    for env in (home / "installs").glob("*/environments/*/venv"):
        roots += site_packages(env)
    return roots


def find_cached_pytest(roots):
    for root in roots:
        if (root / "pytest" / "__init__.py").exists() and (root / "_pytest").is_dir():
            return root
    return None


def child_env(folder, home_mode):
    env = dict(os.environ)
    env.update(HERMES_HOME=str(Path(folder) / ".hermes"),
               TMPDIR=str(folder), TMP=str(folder), TEMP=str(folder),
               PYTHONDONTWRITEBYTECODE="1", HERMES_SKIP_INIT_WARMUP="1")
    if home_mode == "scratch":
        env["HOME"] = str(folder)
        env["USERPROFILE"] = str(folder)
    for key in ("PYTHONPATH", "HERMES_SCRATCH_DIR", "__HERMES_ACTIVATED"):
        env.pop(key, None)
    return env


def missing_tests(repo):
    return [path for path in TESTS if not (repo / path).is_file()]

def main():
    args = parse_args()
    home = hermes_home()
    repo = (args.repo or home / "hermes-agent").resolve()
    if not repo.is_dir():
        print("no checkout at {}; pass --repo".format(repo), file=sys.stderr)
        return 2
    missing = missing_tests(repo)
    if missing:
        print("this checkout does not carry the TUI port: {} of {} listed "
              "test files are missing (first: {}). The port lives on branch "
              "tui-port-v0.22.4 in the tank bare repo; install it first "
              "(packaging-design.md has the quickstart) or pass --repo at a "
              "checkout that carries it.".format(
                  len(missing), len(TESTS), missing[0]), file=sys.stderr)
        return 2

    if args.python is not None:
        interpreter = args.python
    elif not committed_env_exists(home, repo):
        # A fresh clone has no committed pm environment, so the pinned store
        # interpreter would refuse its own bootstrap (NoCommittedEnvironment).
        interpreter = venv_interpreter(repo)
        if interpreter is None:
            print("no committed pm environment for this checkout and no .venv in it; "
                  "run the sanctioned dev sync (`uv sync --locked --group dev`) inside "
                  "{}, then rerun, or pass --python".format(repo), file=sys.stderr)
            return 2
    else:
        launcher = launcher_path(home, repo)
        if launcher is None:
            print("no hermes launcher on PATH, ~/.local/bin, or the checkout; pass --python",
                  file=sys.stderr)
            return 2
        interpreter = runtime_interpreter(launcher)
    roots = pytest_roots(home, repo)
    if args.pytest_root is not None:
        pytest_root = args.pytest_root
    else:
        pytest_root = find_cached_pytest(roots)
    if args.list_roots:
        print("repo: {}".format(repo))
        print("interpreter: {}".format(interpreter))
        for root in roots:
            print("{} {}".format("pytest" if find_cached_pytest([root]) else "no    ", root))
        return 0
    if pytest_root is None:
        print("no cached pytest in any discovered root:", file=sys.stderr)
        for root in roots:
            print("  {}".format(root), file=sys.stderr)
        print("sanctioned remedy (one deliberate dev sync, pinned by upstream): "
              "run `uv sync --locked --group dev` inside {} using the uv the installer "
              "staged under {}/tools, then rerun. This script never installs "
              "anything.".format(repo, home), file=sys.stderr)
        return 2
    # Never under the real ~/.hermes: the home-I/O guard protects that tree in
    # --home real mode, and a scratch dir inside it makes every test write refuse.
    scratch_root = Path(tempfile.gettempdir())
    scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hermes-tui-verify-",
                                     dir=str(scratch_root)) as folder_name:
        folder = Path(folder_name)
        env = child_env(folder, args.home)
        # Let bootstrap see the real profile solely for dependency discovery.
        bootstrap_env = dict(env, HERMES_HOME=str(home))
        code = (
            "import sys, os, runpy; "
            "sys.path.insert(0, {!r}); import hermes_bootstrap; ".format(str(repo))
            + "os.environ['HERMES_HOME']={!r}; ".format(env["HERMES_HOME"])
            + "sys.path.insert(0, {!r}); ".format(str(pytest_root))
            + "sys.argv=['pytest','-q','-rs','-p','no:cacheprovider',"
              "'--basetemp=" + str(folder / "pytest") + "',*{!r}]; ".format(TESTS)
            + "print('Runtime:',sys.version,sys.executable); "
              "runpy.run_module('pytest',run_name='__main__')"
        )
        result = subprocess.run([str(interpreter), "-B", "-c", code],
                                cwd=str(repo), env=bootstrap_env)
        return result.returncode


if __name__ == "__main__":
    try:
        code = main()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        code = 0
    raise SystemExit(code)