# Hermes TUI customizations

Packaging for a set of [Hermes Agent](https://github.com/NousResearch/hermes-agent)
CLI customizations, maintained as a **pinned branch + patch + portable test runner**
rather than an installer:

- a **session-cost badge** in the status bar (far-right slot), showing a trusted dollar
  total only when per-session cost accounting can prove it, and
  `Session cost unavailable` otherwise;
- **highlighted fenced code blocks** (Rich/Pygments, monokai, language label, no
  literal fences) for the classic prompt_toolkit CLI;
- **session-cost accounting repairs** (producer-side missing-usage accounting,
  OpenRouter context-tier pricing overrides, honest tiny-cost labels).

Upstream ships no plugin or entry-point hook for the classic CLI's status bar or
layout, so the customizations live as source changes over a pinned upstream commit.

## Repository contents

| File | What it is |
| --- | --- |
| `hermes-tui-customizations.patch.new` | The 23-file patch (16 modified + 7 new paths) against upstream base `4d04303818b61bf3aa09278af48356315515965b` (v0.22.4 era). sha256 `0675d0da20029aea6b0bb7865e11d94698d7ce517d40f37b1f4ff1d8f721b3bf`. |
| `packaging-design.md` | The design: how the patch becomes an installable pinned branch, per-OS quickstarts (macOS / Windows / Linux), update and re-port semantics, and the arena-synthesized rationale. |
| `verify.py` | Portable, dependency-free regression runner: discovers the pinned interpreter via `hermes --print-runtime-command`, discovers a cached pytest across per-OS site-packages roots, and runs a 27-path selection in an isolated scratch HOME. Never installs anything. |
| `display-settings.yaml` | The three config keys the features need (reference fragment; the operative path is `hermes config set`). |

## Install (any OS, from a port repository)

Both upstream installers (`install.sh` for macOS/Linux, `install.ps1` for Windows)
accept a fork source and a commit pin, and record the pin in
`.hermes-bootstrap-complete`. Point `HERMES_REPO_URL` at a repository carrying the
port branch (`tui-port-v0.22.4`, tip `dc28bd1ea2781fd4f5827df1d54b29510d96c6c0`),
pin it, then enable the two features through the supported config CLI:

```sh
curl -fsSL -o /tmp/install.sh \
  https://raw.githubusercontent.com/NousResearch/hermes-agent/4d04303818b61bf3aa09278af48356315515965b/scripts/install.sh
echo "20f44240ebada354a468104a6a6724d037afcb8883d4d09ddeb4815622c52d8b  /tmp/install.sh" | shasum -a 256 -c -
HERMES_REPO_URL="git@github.com:Finale8713/hermes-tui-port.git" \
  sh /tmp/install.sh --branch tui-port-v0.22.4 --commit dc28bd1ea2781fd4f5827df1d54b29510d96c6c0
exec "$SHELL" -l

hermes config set display.code_highlighting true
hermes config set display.status_bar.right_badge cost
hermes config set display.status_bar.fields '[model, context_pct, total_tokens, tps, latency, cache_hit, duration, cost]'
```

Windows uses `install.ps1` with `-Branch`/`-Commit` (same pin, same
`HERMES_REPO_URL`); see `packaging-design.md` for the full PowerShell quickstart.

**After installing, exit every running Hermes process before trusting the badge.**
The gateway process is the single writer of `state.db`; a writer that predates the
install keeps writing without cost coverage. Sessions written by the old writer stay
`Session cost unavailable` by design; fresh sessions show a total after their first
priced call.

## Verify

```sh
python3 verify.py            # expect exit 0
python3 verify.py --list-roots   # diagnose interpreter + pytest discovery
```

Recorded full-selection result on Linux: 711 passed, 1 skipped (the macOS clipboard
test), 74 subtests, exit 0, ~120 s. On a machine with no cached pytest anywhere the
runner exits 2 naming the tried roots and the one sanctioned remedy (a single
`uv sync --locked --group dev` under the installer-staged uv); it never installs
anything itself.

## Attribution

The customizations are derivatives of
[Hermes Agent](https://github.com/NousResearch/hermes-agent) (MIT, Copyright (c) 2025
Nous Research). This repository carries packaging artifacts and documentation; the
port branch itself lives in its own repository.