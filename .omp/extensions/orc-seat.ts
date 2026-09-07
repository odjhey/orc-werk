// TASK-M5-005 -- .omp/extensions/orc-seat.ts
//
// What this hook does, and only this: on a `ship` seat's `write`/`edit` tool calls, it
// DETECTS AND BLOCKS THE NAIVE, ACCIDENTAL CASE -- a declared path/edit-target that
// lexically- or symlink-resolves outside its OWN `.worktrees/<branch>` directory, or a
// target this guard cannot resolve to any local path at all (issue #297; see below). It
// is a TRIPWIRE, not a control, and no sentence in this file is a soundness/enforcement
// claim: it decides on `ctx.cwd` and the tool call's OWN declared path input --
// structural context this hook genuinely receives, never the text of a command -- and
// it was, for that reason, the one guard of ADR-0007's original four-guard design
// (record-before-yield, no subagent `gh pr merge`, verify push/commit/comment/review
// denial, ship worktree fence) that four separate adversarial audits left unmodified,
// while those same audits repeatedly defeated the other three on their command-text
// channel until they were deleted outright. But a FIFTH audit (issue #297, ledger
// `task-m5-005-guards` seq 36, against this same head `ef093a3`) defeated THIS guard
// too, two further structural ways: a `write`/`edit` whose target carries no local path
// at all (`ssh://host/<path>`, which the harness tool surface documents as genuinely
// writable) fell through the old "zero candidates means nothing to check" default and
// returned ALLOW; and a hardlinked name created inside the seat's own worktree shares
// an inode with a sibling worktree's file while its OWN `realpath` stays inside --
// `realpath` resolves symlinks, never hardlinks, so this comparison cannot see that
// aliasing at all (see the comment at the realpath comparison below). The first defect
// is fixed below: an unresolvable target now DENIES, never silently ALLOWs. The second
// is disclosed, not fixed -- sound detection would need an unbounded, racy inode sweep
// of every sibling worktree on every call, and is not attempted here.
//
// *** Command-text interception was attempted, and abandoned, for the other three ***
//
// The removed guards -- record-before-yield, no subagent `gh pr merge`, verify
// push/commit/comment/review denial, no subagent pushes to a shared branch -- all
// decided by inspecting `event.input.command`, the ONLY thing a `tool_call` hook's
// `bash` event carries. That is a single STRING: never shell argv, never the resolved
// executable, never process identity. Four attempts across runs `task-m5-005` and
// `task-m5-005-guards` (ledger seq 16; `orc history task-m5-005-guards --limit 0`; root
// cause filed as issue #290) each patched a bypass this way and re-armed another, in
// both match directions (blacklist, then a corrected whitelist): live audits defeated it
// with `g\it push origin +master` and `g\h pr merge`, which advanced disposable bare
// remotes past the guards meant to stop exactly that, and with `PATH=<stub> orc record
// ...`, which satisfied the record-before-yield gate while only a logging stub ran.
// "Does this command string invoke X" is not decidable from the string alone -- the
// shell has `&&`, `||`, `;`, quoting, backslash-escaped binary names, `uv run`
// wrapping, and `PATH` manipulation, and every patch closing one of those re-opened
// another. Issue #297 (above) completed this capability finding on the OTHER channel
// too: no OMP `tool_call` hook can soundly enforce a seat rule, full stop.
//
// Per the operator's 2026-09-07 descope ruling (recorded on this task card, citing run
// `task-m5-005-guards` seq 16 and issue #290), this hook does not re-attempt any of the
// four removed guards. They are POLICY, not mechanism -- honored by the seat
// definitions (`ship.md`/`verify.md`) and audited after the fact via the ledger/PR
// history, never by this hook or by any other `tool_call` hook. Where a rung genuinely
// does hold:
//
// - Push/merge restriction (guards 2, 3, 5 in this card's original numbering): as of a
//   2026-09-07 read-back of `gh api repos/odjhey/orc-werk/branches/master/protection
//   --jq '[.restrictions, .required_pull_request_reviews.required_approving_review_count]'`
//   (`[null, 0]`), server-side GitHub branch protection genuinely stops any identity
//   from writing directly to `master` -- a real, BRANCH-scoped rung. It does not, and
//   cannot, carry a SEAT-scoped rule (e.g. "verify specifically may not push") at all:
//   `restrictions` is the one field that binds a push/merge restriction to a specific
//   actor, it reads `null` here, and even populated it keys on GitHub user/team/app
//   identity, never on the agent-role of the one shared credential every seat in this
//   repo authenticates as. That per-seat restriction has no enforcing rung at all: it is
//   policy (`ship.md`/`verify.md`) plus after-the-fact ledger/PR-history audit, nothing
//   else. Re-run the `gh api` call above before relying on this paragraph; it is a
//   configuration read-back, not a standing fact.
// - Record-before-yield needs no hook at all: the orc state machine itself is the
//   genuinely enforcing rung here -- a work with no recorded `FACT-EXEC-SETTLED` stays
//   non-terminal and the run cannot reach a terminal state, independent of anything a
//   session's own tool calls do or don't do. This is a kernel/state-machine property,
//   not a `tool_call`-hook claim, so issue #297's finding does not touch it.
//
// What remains below -- the worktree fence -- is a tripwire against naive and
// accidental violations, live-audited across five attempts: four it blocked
// sibling-worktree and primary-checkout writes on while permitting a seat's own (see
// this card's PR body for the live commands and observed denials/allows), and a fifth
// (#297) that defeated it structurally, addressed above. Its limits, stated plainly: it
// decides on `ctx.cwd` and the tool call's OWN declared path/edit-target input, resolved
// to a local filesystem path. It has no visibility into a write that reaches the
// filesystem through any channel this hook never sees a local path for (a bash-invoked
// script), it now denies rather than silently permits a target it cannot resolve to a
// local path at all (`ssh://`, fixed below), and it cannot distinguish a hardlinked name
// inside the seat's own worktree from the sibling-worktree file it silently aliases
// (disclosed, not fixed, at the realpath comparison below). Deliberate evasion defeats
// it; it only ever caught the naive and the accidental.

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import fs from "node:fs";
import path from "node:path";

// ---------------------------------------------------------------------------------------
// The role signal (per-session, memoized) -- `session_init.agent`, the literal role name
// (ship/verify/scout) a subagent session was spawned with, read from its own transcript.
// A root/top-level session carries no `session_init` entry, so this reliably returns
// `undefined` there. Confirmed live from inside a real `tool_call` hook handling a
// subagent's own tool call (see this card's PR #284 body for the live citation):
//
//   ctx.sessionManager.getEntries().find(e => e.type === "session_init").agent
// ---------------------------------------------------------------------------------------

function agentFromEntries(getEntries: (() => unknown[]) | undefined): string | undefined {
  if (typeof getEntries !== "function") return undefined;
  let entries: unknown[];
  try {
    entries = getEntries();
  } catch {
    return undefined; // fail open (never guard on missing information)
  }
  if (!Array.isArray(entries)) return undefined;
  for (const entry of entries) {
    if (entry && typeof entry === "object" && (entry as Record<string, unknown>).type === "session_init") {
      const agent = (entry as Record<string, unknown>).agent;
      return typeof agent === "string" ? agent : undefined;
    }
  }
  return undefined;
}

/** A session's own `agent` never changes after `session_init`, so this is memoized per
 * session id -- purely a performance guard against re-scanning a growing entries array
 * on every tool call, not a correctness requirement (re-deriving fresh every time would
 * give the identical answer). */
export function getSessionAgent(
  state: OrcSeatState,
  sessionId: string | undefined,
  getEntries: (() => unknown[]) | undefined,
): string | undefined {
  if (!sessionId) return agentFromEntries(getEntries);
  if (state.agentBySession.has(sessionId)) return state.agentBySession.get(sessionId);
  const agent = agentFromEntries(getEntries);
  state.agentBySession.set(sessionId, agent);
  return agent;
}

export interface OrcSeatState {
  /** memoized `session_init.agent` per session id; see `getSessionAgent`. Per-session
   * closure state only -- a fresh `orcSeat(pi)` call per session means it never leaks
   * between sessions even though it is a module-level closure variable, not a state
   * object threaded explicitly through `ctx`. */
  agentBySession: Map<string, string | undefined>;
}

export function createOrcSeatState(): OrcSeatState {
  return { agentBySession: new Map() };
}

// ---------------------------------------------------------------------------------------
// Guard -- the ship seat's edits stay inside its own `.worktrees/<branch>`
//
// A literal per-role rule, per ADR-0007: "Ship works in its own worktree; never merges"
// -> "a hook fences `edit`/`write` to that path". Scoped to `agent === "ship"`
// specifically, not "any subagent with write/edit tools" -- today only `ship` declares
// those tools, but the role check is what the card actually specifies, and it stays
// correct even if a future subagent type gains write/edit tools without also being
// meant to hold this invariant.
//
// Soundness (issues #296 and #297): this predicate decides on `event.input.path`,
// structured, normalized input the hook genuinely receives for `write`/`edit` -- never
// on command text. Four defects were found live and fixed here:
//
// 1. Symlink escape: a lexical `path.resolve` string comparison never resolves
//    symlinks, so `write escape-link/x.txt` where `escape-link -> ../outside` compared
//    as "inside" while actually landing outside. `isInsideOwnWorktree` below resolves
//    the REAL (symlink-free, canonical-case) path of both the root and the target via
//    `fs.realpathSync` before comparing -- never a raw string. A `write`'s leaf commonly
//    does not exist yet, and `fs.realpathSync` throws on a path that does not exist, so
//    `realOf` walks up to the nearest EXISTING ancestor first (`nearestExistingAncestor`),
//    resolves THAT ancestor's real path, and re-appends the (lexical, not-yet-real)
//    remainder -- correct because only the existing prefix can carry a symlink, and a
//    non-existent tail literally cannot yet be one.
// 2. Colon/scheme escape: the old extractor dropped everything after a path's first
//    `:` (the archive-member/SQLite-selector reading OMP's `write`/`edit` also accept,
//    e.g. `archive.zip:inner/path`, `db.sqlite:table`) and skipped any path containing
//    `://` outright, so `./safe:/../../outside/x.txt` and
//    `./colon://../../outside/x.txt` both slipped through unresolved. Per issue #296's
//    rule ("do not guess which reading is intended: evaluate every plausible
//    interpretation and block if any resolves outside"), `pathReadings` below returns
//    BOTH the literal full string and, when a `:` is present, the substring before it --
//    every candidate is checked, and any one escaping is a block. Only a small, explicit
//    allowlist of recognized internal-URI schemes (the schemes the `read`/`write` tools
//    themselves document, e.g. `local://`) is exempted from filesystem comparison at
//    all; an unrecognized `://`-prefixed string is never assumed to be a safe internal
//    reference.
// 3. Case false-denial: on a case-insensitive filesystem (APFS default), a legitimate
//    own-worktree path reached via different case (e.g. `/users/...` for a worktree
//    actually mounted at `/Users/...`) was denied as outside, because the old check
//    compared path strings verbatim. The same `realOf` resolution that fixes (1) fixes
//    this for free: `fs.realpathSync`/`fs.existsSync` resolve the SAME on-disk entry
//    regardless of the case used to reach it and return it in its ONE canonical case, so
//    the two real paths this guard compares always agree on case when they name the
//    same real file -- no separate case-normalization step is needed, attempted, or
//    assumed to apply globally here.
// 4. Unresolvable-target ALLOW (issue #297): zero path readings used to mean "nothing
//    to check" unconditionally -- including for `ssh://`, which the old table listed
//    alongside `local://` as "never touches the filesystem". True for `local://`;
//    false for `ssh://`, which the tool surface documents as genuinely writable, to a
//    REMOTE filesystem this guard has no local path to compare at all. `ssh` now sits
//    in its own `UNRESOLVABLE_URI_SCHEMES` table below; `extractUnresolvableTargets`
//    surfaces it separately from `extractCandidatePaths`, and
//    `evaluateWorktreeFenceGuard` denies on any unresolvable target before it ever
//    reaches the path comparison -- "cannot resolve this to a local path" is now a
//    DENY, never a silent ALLOW.
//
// Root and target are each resolved independently to one canonical real path, then
// compared with a single `path.relative` (never a walk comparing inode identity up two
// separate ancestor chains) -- which stays sound even when NEITHER path exists on disk
// at all (both `realOf` calls degrade to their own lexical input unchanged, reproducing
// the pre-#296 lexical comparison exactly), so this fix is additive: every path this
// guard already decided correctly, it still decides identically.
// ---------------------------------------------------------------------------------------

const WORKTREES_SEGMENT = ".worktrees";

/** Internal-URI schemes the `read`/`write` tools themselves document (their own tool
 * descriptions) as never touching any real filesystem at all -- `local://plan.md` and
 * similar resolve against an internal store, not `fs`, so a `write`/`edit` naming one
 * of these performs no filesystem write anywhere, local or remote, for this guard to
 * compare. These contribute NEITHER a path reading NOR an unresolvable-target one --
 * there is genuinely nothing to check. */
const IGNORED_URI_SCHEMES: Record<string, true> = {
  local: true,
  memory: true,
  artifact: true,
  history: true,
  agent: true,
  rule: true,
  skill: true,
  mcp: true,
  issue: true,
  pr: true,
  omp: true,
};

/** Internal-URI schemes the tool surface documents as performing a REAL filesystem
 * write this guard cannot resolve to a comparable local path -- today, only
 * `ssh://host/<path>` ("writable with write"), which writes to a remote host's
 * filesystem. Issue #297: `ssh` used to sit in the ignored-schemes table above, so a
 * `write`/`edit` naming it produced zero readings and the old
 * `candidates.length === 0` check at the foot of this file treated "nothing to
 * compare" as ALLOW -- reproduced live as `{"result":"ALLOW"}` against a real
 * `ssh://tiny/tmp/orc-seat-escape.txt` write. A scheme in THIS table is the opposite
 * of ignored: `extractUnresolvableTargets` below surfaces it, and
 * `evaluateWorktreeFenceGuard` denies on it before ever reaching the path-candidate
 * comparison. */
const UNRESOLVABLE_URI_SCHEMES: Record<string, true> = {
  ssh: true,
};

const INTERNAL_URI_SCHEME_RE = /^([a-zA-Z][a-zA-Z0-9+.-]*):\/\//;

/** One raw `write`/`edit` path-candidate string, classified as either `"path"`
 * (evaluate as a filesystem path) or `"unresolvable"` (a recognized scheme performing
 * a real write this guard cannot resolve to a local path -- issue #297). A recognized
 * `IGNORED_URI_SCHEMES` scheme produces neither: nothing to check. Any OTHER
 * `scheme://...`-shaped string (e.g. an attacker-chosen `colon://...`) is in neither
 * table and is therefore evaluated as a plain `"path"` candidate -- unlike the prior,
 * unconditional `://` skip issue #296 found bypassable. For a `"path"` reading: the
 * literal string itself, and -- since OMP's own `write`/`edit` accept
 * `archive.ext:inner/path`/`db.sqlite:table` selector syntax -- the substring before
 * its first `:`, when one is present. Never guesses which reading is "the" intended
 * one; the caller checks all of them and blocks if any escapes (issue #296). */
type Reading = { kind: "path" | "unresolvable"; value: string };

function classifyRaw(raw: string): Reading[] {
  const schemeMatch = INTERNAL_URI_SCHEME_RE.exec(raw);
  if (schemeMatch) {
    const scheme = schemeMatch[1].toLowerCase();
    if (IGNORED_URI_SCHEMES[scheme]) return [];
    if (UNRESOLVABLE_URI_SCHEMES[scheme]) return [{ kind: "unresolvable", value: raw }];
  }
  const readings = new Set<string>([raw]);
  const colonIdx = raw.indexOf(":");
  if (colonIdx !== -1) readings.add(raw.slice(0, colonIdx));
  return [...readings].map((value): Reading => ({ kind: "path", value }));
}

/** Every raw `write`/`edit` path-candidate string this hook genuinely receives for a
 * call, before scheme classification: `write`'s own `path` field, or every hashline
 * header (`[<path>#<TAG>]`) `edit`'s own `input` text carries. */
function rawCandidates(toolName: string, input: unknown): string[] {
  if (!input || typeof input !== "object") return [];
  if (toolName === "write") {
    if (!("path" in input)) return [];
    const raw = (input as Record<string, unknown>).path;
    return typeof raw === "string" ? [raw] : [];
  }
  if (toolName === "edit") {
    if (!("input" in input)) return [];
    const raw = (input as Record<string, unknown>).input;
    if (typeof raw !== "string") return [];
    return [...raw.matchAll(/\[([^\]#\n]+)#[0-9A-Fa-f]{4}\]/g)].map((match) => match[1]);
  }
  return [];
}

/** Every plausible filesystem-path reading (issue #296) of this call's candidates --
 * never an unresolvable one; see `extractUnresolvableTargets` for those. */
export function extractCandidatePaths(toolName: string, input: unknown): string[] {
  return rawCandidates(toolName, input)
    .flatMap(classifyRaw)
    .filter((r) => r.kind === "path")
    .map((r) => r.value);
}

/** Every candidate this call names that performs a real write this guard cannot
 * resolve to a local path to compare (issue #297) -- today, an `ssh://` target.
 * Non-empty here means `evaluateWorktreeFenceGuard` denies before ever reaching the
 * path comparison: unknown is a DENY, never a silent ALLOW. */
export function extractUnresolvableTargets(toolName: string, input: unknown): string[] {
  return rawCandidates(toolName, input)
    .flatMap(classifyRaw)
    .filter((r) => r.kind === "unresolvable")
    .map((r) => r.value);
}

/** The seat's OWN worktree root, derived from its own `cwd` -- never merely "some path
 * containing a `.worktrees` segment" (an earlier defect: a ship at
 * `/repo/.worktrees/task-x` could write into `/repo/.worktrees/sibling/file.ts`, and a
 * guard checking only for the *presence* of a `.worktrees` segment anywhere in the
 * resolved path allowed it -- proven both by a factory probe and by a live ship session
 * writing into a verifier's own outer `.worktrees/verify-m5-005-r2`). `cwd` for a real
 * ship session is always inside its own `.worktrees/<branch>` (`ship.md`'s own protocol:
 * "Work only inside `.worktrees/<branch>`"), so the branch segment immediately following
 * `.worktrees` in `cwd` IS the seat's own worktree root. Returns `undefined` when `cwd`
 * itself is not inside any `.worktrees` directory -- a ship session should never be
 * running from outside one, so this fails CLOSED (every candidate path is treated as
 * escaping) rather than open, preserving the existing primary-checkout denial. This
 * function stays purely lexical (string splitting on `cwd`); the FILESYSTEM identity
 * resolution that makes the comparison sound against symlinks and case happens in
 * `isInsideOwnWorktree` below, once, for both sides of the comparison. */
function ownWorktreeRoot(cwd: string): string | undefined {
  const segments = cwd.split(path.sep);
  const idx = segments.indexOf(WORKTREES_SEGMENT);
  if (idx === -1 || idx + 1 >= segments.length) return undefined;
  return segments.slice(0, idx + 2).join(path.sep) || path.sep;
}

/** Walks `p` up to the nearest ancestor that actually exists on disk -- a `write`'s
 * target commonly does not (it is about to be created), sometimes several directory
 * levels deep, and `fs.realpathSync` can only resolve a path that exists. */
function nearestExistingAncestor(p: string): string {
  let current = p;
  while (true) {
    if (fs.existsSync(current)) return current;
    const parent = path.dirname(current);
    if (parent === current) return current; // filesystem root; nothing exists above it
    current = parent;
  }
}

/** The ONE canonical real path for `p`: `fs.realpathSync` of the nearest EXISTING
 * ancestor (resolves symlinks and normalizes to the on-disk case, throughout that
 * existing prefix), with the non-existent remainder re-appended lexically -- a
 * not-yet-created `write` leaf cannot itself be a symlink or reached via a case
 * variant, so nothing is lost by leaving that tail as-is. When `p` has NO existing
 * ancestor at all beyond the filesystem root (a fabricated path, e.g. in a unit test
 * that never touches disk), `fs.realpathSync` of that root is the root itself, so this
 * degrades to returning `p` unchanged -- the exact pre-#296 lexical string, preserving
 * every decision this guard already made correctly.
 *
 * Disclosed limitation (issue #297), NOT fixed here: `fs.realpathSync` resolves
 * SYMLINKS, never HARDLINKS. A name hardlinked inside the seat's own worktree that
 * shares an inode with a file in a sibling worktree resolves, via this function, to a
 * real path that stays INSIDE the seat's own worktree -- a hardlink has no separate
 * "canonical" target name the way a symlink does, so this comparison cannot see the
 * aliasing at all. Reproduced live: `os.link(<sibling worktree>/outside.txt, <own
 * worktree>/alias.txt)` gave `nlink=2` with both names sharing one inode; this guard
 * ALLOWed a write to the inside name (`alias.txt`); that write changed the sibling
 * file's own content. Sound detection would require stat-ing every file in every
 * sibling worktree and comparing inodes on every call -- unbounded, and racy (a
 * hardlink can be created between the sweep and the write) -- so it is not attempted.
 * This is a genuine, disclosed gap in the tripwire, not a claim that it is closed. */
function realOf(p: string): string {
  const existing = nearestExistingAncestor(p);
  const real = fs.realpathSync(existing);
  const tail = path.relative(existing, p);
  return tail === "" ? real : path.join(real, tail);
}

/** Is the lexically-resolved candidate `resolvedTarget` inside `root` (the seat's own
 * worktree root)? Resolves EACH side independently to its own canonical real path
 * (`realOf`, symlinks followed, case normalized) and compares with a single
 * `path.relative` -- never a walk comparing filesystem identity up two separate
 * ancestor chains, which is unsound when neither path exists on disk at all (both
 * chains would converge on the same real filesystem root by coincidence, not because
 * either path is actually inside the other). */
function isInsideOwnWorktree(root: string, resolvedTarget: string): boolean {
  const realRoot = realOf(root);
  const realTarget = realOf(resolvedTarget);
  const rel = path.relative(realRoot, realTarget);
  return rel !== ".." && !rel.startsWith(".." + path.sep) && !path.isAbsolute(rel);
}

function escapesOwnWorktree(root: string | undefined, resolvedTarget: string): boolean {
  if (!root) return true;
  return !isInsideOwnWorktree(root, resolvedTarget);
}

export function evaluateWorktreeFenceGuard(
  agent: string | undefined,
  toolName: string,
  input: unknown,
  cwd: string,
): { block: true; reason: string } | undefined {
  if (agent !== "ship" || (toolName !== "write" && toolName !== "edit")) return undefined;
  const unresolvable = extractUnresolvableTargets(toolName, input);
  if (unresolvable.length > 0) {
    return {
      block: true,
      reason:
        `orc-seat: ${toolName} targets ${unresolvable.join(", ")}, which this guard cannot resolve to any ` +
        "local path to compare against this ship seat's own worktree; an unresolvable target is denied, " +
        "never silently allowed (issue #297).",
    };
  }
  const candidates = extractCandidatePaths(toolName, input);
  if (candidates.length === 0) return undefined;
  const root = ownWorktreeRoot(cwd);
  const escaping = candidates.filter((raw) => escapesOwnWorktree(root, path.resolve(cwd, raw)));
  if (escaping.length === 0) return undefined;
  return {
    block: true,
    reason:
      `orc-seat: ${toolName} targets ${escaping.join(", ")}, outside this ship seat's own worktree` +
      `${root ? ` (${root})` : ""}; edits must stay inside the seat's own \`.worktrees/<branch>\`, never a sibling's.`,
  };
}

// ---------------------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------------------

export default function orcSeat(pi: ExtensionAPI): void {
  const state = createOrcSeatState();

  pi.on("tool_call", async (event, ctx) => {
    if (event.toolName !== "write" && event.toolName !== "edit") return undefined;
    const sessionId = ctx.sessionManager?.getSessionId?.();
    const agent = getSessionAgent(state, sessionId, () => ctx.sessionManager?.getEntries?.() ?? []);
    const cwd = ctx.cwd ?? process.cwd();
    return evaluateWorktreeFenceGuard(agent, event.toolName, event.input, cwd);
  });
}
