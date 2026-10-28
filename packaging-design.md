# Cross-machine packaging design (2026-10-27)

Synthesized from two arena candidates plus a cross-judge (base: pinned branch in a
private port repository, zero installer code; grafts from a bootstrap-pack candidate
that was rejected as a shape). Facts below were verified on the author's Linux install
on 2026-10-27 unless cited otherwise.

## Problem

The 23-file TUI port (cost badge, fenced-code highlighting, session-cost accounting)
exists only as an uncommitted overlay on the live checkout and as a frozen patch,
`hermes-tui-customizations.patch.new` on base `4d04303818`. It must install on fresh
macOS, Windows, and Linux machines. Upstream has no plugin or entry-point hook for the
prompt_toolkit status bar or layout, so a source patch or a branch carrying one is the
only vehicle. Uncommitted overlays are fragile by construction: `hermes update` and
installer reruns stash/backup-and-reset dirty trees (`install.sh:815-872`,
`install.ps1:1095-1098`). The README forbids opportunistic rebases. Verification must
not install anything.

## Usage (caller's view)

### Rebuild the port commit from the patch (once per port)

Run on a machine that can reach both the upstream repository and the port repository.
The live checkout is never touched; the port commit is built in a throwaway worktree
at the pin.

```sh
cd ~/.hermes/hermes-agent
git worktree add --detach /tmp/hermes-port-publish 4d04303818b61bf3aa09278af48356315515965b
PATCH="$(pwd)/hermes-tui-customizations.patch.new"   # run this block from a clone of this repo
git -C /tmp/hermes-port-publish apply --check "$PATCH"
git -C /tmp/hermes-port-publish apply        "$PATCH"
git -C /tmp/hermes-port-publish commit -m "port: TUI customizations (cost badge, fenced-code highlighting, session-cost accounting) on v0.22.4 base 4d04303818"
PORT_SHA="$(git -C /tmp/hermes-port-publish rev-parse HEAD)"
# Consistency: the branch diff must reproduce the frozen patch (index-line noise
# aside, sha256 0675d0da20029aea6b0bb7865e11d94698d7ce517d40f37b1f4ff1d8f721b3bf).
git -C /tmp/hermes-port-publish diff 4d04303818b61bf3aa09278af48356315515965b..HEAD | sha256sum
# Publish: push the branch to the port repository.
git -C /tmp/hermes-port-publish push git@github.com:Finale8713/hermes-tui-port.git HEAD:refs/heads/tui-port-v0.22.4
git worktree remove --force /tmp/hermes-port-publish
```

Record `PORT_SHA` below where `<PORT_SHA>` appears. As executed 2026-10-27,
`PORT_SHA` = `dc28bd1ea2781fd4f5827df1d54b29510d96c6c0`.

### Fresh macOS machine

```sh
# Prereqs: Command Line Tools for git+python3, and SSH auth the port repo accepts.
xcode-select -p >/dev/null 2>&1 || xcode-select --install
# Install: upstream's own pin-era installer, sha256-gated, pointed at the port repo, pinned.
curl -fsSL -o /tmp/install.sh \
  https://raw.githubusercontent.com/NousResearch/hermes-agent/4d04303818b61bf3aa09278af48356315515965b/scripts/install.sh
echo "20f44240ebada354a468104a6a6724d037afcb8883d4d09ddeb4815622c52d8b  /tmp/install.sh" | shasum -a 256 -c -
HERMES_REPO_URL="git@github.com:Finale8713/hermes-tui-port.git" \
  sh /tmp/install.sh --branch tui-port-v0.22.4 --commit dc28bd1ea2781fd4f5827df1d54b29510d96c6c0
exec "$SHELL" -l        # pick up the published launcher on PATH
# Config: the supported CLI, default profile only.
hermes config set display.code_highlighting true
hermes config set display.status_bar.right_badge cost
hermes config set display.status_bar.fields '[model, context_pct, total_tokens, tps, latency, cache_hit, duration, cost]'
# Verify: portable runner from this repository. Expect exit 0.
python3 verify.py
grep -o '"pinnedCommit": *"[0-9a-f]*"' ~/.hermes/hermes-agent/.hermes-bootstrap-complete   # matches <PORT_SHA>
```

Writer restart matters on every OS: the gateway process is the single writer of
`~/.hermes/state.db` (`gateway_session_store.py:1-11`), and a writer started before
this install keeps running the old code, writing rows without cost coverage and
leaving the schema unreconciled (reconciliation runs on every writable open only;
read-only opens skip it, `hermes_state_schema.py:172-173`, `:948-966`). Before
trusting the badge, exit every running Hermes process (verify with `ps` that none
predates the install) and relaunch. A session whose calls were written by the old
writer stays `Session cost unavailable` by design; a fresh session shows a total
after its first priced call.

### Fresh Windows machine (PowerShell 5.1+)

```powershell
# Prereqs: Git for Windows (its OpenSSH), and SSH auth the port repo accepts
# (in $env:USERPROFILE\.ssh\config).
irm https://raw.githubusercontent.com/NousResearch/hermes-agent/4d04303818b61bf3aa09278af48356315515965b/scripts/install.ps1 -OutFile $env:TEMP\install.ps1
if ((Get-FileHash $env:TEMP\install.ps1 -Algorithm SHA256).Hash -ne "3D428CE54DEAFE26F8F52E40B2A49876D3CB95C49760E8350D6458046519479") { throw "installer hash mismatch" }
$env:HERMES_REPO_URL = "git@github.com:Finale8713/hermes-tui-port.git"
powershell -ExecutionPolicy Bypass -File $env:TEMP\install.ps1 -Branch tui-port-v0.22.4 -Commit dc28bd1ea2781fd4f5827df1d54b29510d96c6c0
# New terminal for PATH, then config. Windows HERMES_HOME default is
# $env:LOCALAPPDATA\hermes (hermes_constants), so pass --repo explicitly below.
hermes config set display.code_highlighting true
hermes config set display.status_bar.right_badge cost
hermes config set display.status_bar.fields '[model, context_pct, total_tokens, tps, latency, cache_hit, duration, cost]'
py -3 verify.py --repo "$env:LOCALAPPDATA\hermes\hermes-agent"    # expect exit 0
Select-String pinnedCommit "$env:LOCALAPPDATA\hermes\hermes-agent\.hermes-bootstrap-complete"
```

The writer-restart note above applies identically on Windows.

### Fresh Linux machine

Same as macOS with `sha256sum -c -` instead of `shasum -a 256 -c -`; the
`xcode-select` line is unnecessary.

### Update and re-port semantics

A pinned install stays put: the installer revalidates the pin on-branch and
re-detaches at it (`install.sh:933-951`, `install.ps1:1200-1243`), so a rerun is a
no-op for the pin. A rerun never touches running processes; the writer-restart note
after the macOS quickstart applies to every install and update. `hermes update` on a
fork-origin checkout is expected to offer nothing (no recorded channel choice) but is
not yet exercised on a scratch box; treat it as unverified and do not rely on it.
Moving to a new upstream pin is a deliberate re-port per the rebase policy: new base,
resolve, verify, refresh artifacts, new branch `tui-port-v<version>`, new `<PORT_SHA>`
here. The old branch stays for history.

## Shape

The one data structure is a git ref: `tui-port-v0.22.4` to one commit (parent
`4d04303818`, tree = pin + the 23-file patch). Everything else is derived, never
synced: the patch regenerates from the ref diff, the install pin is the ref tip, the
config keys come from the supported CLI, and verification reads the checkout it is
pointed at. The only code in the package is `verify.py`, portability helpers only
(`_launcher_path` (probe), `_runtime_interpreter` via `--print-runtime-command`,
`_site_roots`/`pytest_roots`/`find_cached_pytest` (ordered per-OS discovery),
`child_env` (explicit home policy), linear `main`). The 27-path `TESTS`
list is carried verbatim. Paths and hashes are validated at the edges (installer
sha256 gate before execution, launcher probe before use) and trusted as plain `Path`s
inside.

`verify.py` behavior, settled empirically 2026-10-27 on the author's Linux install:

- `--home scratch` (default, the recorded harness semantics): full HOME isolation.
  The whole 27-path selection is green: 711 passed, 1 skipped (macOS clipboard test on
  Linux), 74 subtests, exit 0, ~120 s. An earlier note about 19
  `test_cli_modern_layout.py` failures described a partial-isolation harness (real
  HOME with conftest isolating only HERMES_HOME), not a property of the tree.
- `--home real`: keeps the real HOME (passes the layout imports the same way) but
  stably trips 4 agent-side logging tests. Trace: `AIAgent.__init__` to
  `_setup_logging` to `hermes_logging._adopt_secondary_home` to `_known_log_homes`
  realpaths an existing handler path under the child HERMES_HOME, and the home-I/O
  guard refuses the guarded syscall (`tests/home_io_guard.py:127`). Scratch roots
  must be the system temp dir, never under the guarded real home.
- `--list-roots` prints discovery inputs and every probed site-packages root. On the
  reference install the launcher shim resolves on PATH, the pinned interpreter comes
  from `--print-runtime-command`, and pytest is found in the checkout's `.venv`;
  the pm environment venvs are probed and skipped.
- No pytest anywhere (fresh machine before any dev sync): exit 2, every tried root
  printed, and the one sanctioned remedy named (`uv sync --locked --group dev` in the
  checkout, using the uv the installer already staged). The script never installs
  anything.
- A checkout that does not carry the port is refused up front: exit 2 naming the
  missing count, the first missing file, and the port branch, before any launcher or
  pytest discovery. Piping output through `head` exits 0 instead of raising
  BrokenPipeError.

## Tradeoffs accepted

- A second lineage may share the port repository (unrelated history) in exchange for
  one exchange point and no new hosting.
- SSH reachability of the port repository is a hard install-time dependency, in
  exchange for zero installer code and no public distribution of a private
  cost-accounting port.
- Quickstarts stay manual (README-carried, upstream-supported commands only), in
  exchange for no bootstrap twins to maintain.
- Fresh machines may find no cached pytest; verify fails closed with the remedy named
  instead of pretending.
- Installs freeze at the pin; upstream movement requires a deliberate re-port.

## Alternatives considered

- Per-machine `git apply` over a plain upstream install (status quo). Exposes a dirty
  overlay to `hermes update` and installer reruns, which stash/reset dirty trees.
  The same patch content, none of the safety. Rejected.
- A wrapper installer (bootstrap twins per OS). Duplicates a parameterized surface
  upstream already maintains and doubles the platforms to test. Rejected on
  interface depth; its sha256-gated pin-era installer fetch was grafted into the
  quickstarts instead.
- A public fork as `HERMES_REPO_URL`. Same mechanics, but publishes a private
  cost-accounting port. Rejected.
- Committing docs or tooling into the port branch. Breaks the branch-diff-equals-patch
  invariant and rides in every future re-port. Rejected.

## Open questions and risks

- First real macOS and Windows fresh-machine runs are unobserved: SSH key
  provisioning, the `ssh://` URL form from Git-for-Windows, `hermes config set`
  before any interactive onboarding, the `Lib/site-packages` layout, and `py -3`
  availability. Each is a one-live-run verification item.
- `hermes update` on a fork-origin pinned checkout needs one scratch-box exercise
  before the docs promise no-op semantics.
- Off-machine backup coverage of any internal hosting remains unverified.

## Next implementation step

Clear the owner gate and run the publish block once per port; then install per the
quickstarts.