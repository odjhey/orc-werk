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
// `task-m5-005-guards` seq 36, against head `ef093a3`) defeated THIS guard too, two
// further structural ways: a `write`/`edit` whose target carries no local path at all
// (`ssh://host/<path>`, which the harness tool surface documents as genuinely writable)
// fell through the old "zero candidates means nothing to check" default and returned
// ALLOW; and a hardlinked name created inside the seat's own worktree shares an inode
// with a sibling worktree's file while its OWN `realpath` stays inside -- `realpath`
// resolves symlinks, never hardlinks, so this comparison cannot see that aliasing at
// all (see the comment at the realpath comparison below). The hardlink defect is
// disclosed, not fixed -- sound detection would need an unbounded, racy inode sweep of
// every sibling worktree on every call, and is not attempted here.
//
// The unresolvable-target defect (issue #297) went through TWO delivered fixes, not
// one, and the difference matters for future maintainers:
//
// - Attempt 1 of this run (`task-m5-005-sensor`, head `623f2cf`) special-cased `ssh` --
//   the one scheme named in issue #297's own example -- into its own
//   `UNRESOLVABLE_URI_SCHEMES` table, alongside an `IGNORED_URI_SCHEMES` table of eleven
//   OTHER recognized schemes (`local`, `memory`, `artifact`, `history`, `agent`, `rule`,
//   `skill`, `mcp`, `issue`, `pr`, `omp`) that produced zero readings and therefore
//   ALLOWed unconditionally, on the unverified assumption that the tool surface's own
//   documentation of them as "never touches a real filesystem" was exhaustive and
//   permanent. An independent verify seat (ledger `task-m5-005-sensor` seq 16, REJECT
//   finding 1) reproduced live, via a real `bun run` fixture probe, that all eleven
//   still returned `paths=[], unresolvable=[], ALLOW` -- the EXACT failure class #297
//   filed, just not yet closed for eleven of twelve schemes -- and that `write {}`, a
//   non-string `path`, `edit` with no hashline header, and an empty/blank `path` ALL
//   ALLOWed too, for the identical reason: each produced zero readings, and zero
//   readings meant "nothing to check" rather than "nothing this guard could verify is
//   safe". A scheme table is a blacklist/whitelist of names, and #290's own root-cause
//   finding about the command-text guards applies here too, one level removed: a table
//   of known names cannot fail closed against a name nobody has added to it yet.
// - Attempt 2 (this delivery) replaces BOTH tables with one structural rule that needs
//   no scheme enumeration at all: a `write`/`edit` call is evaluated by whether it
//   yields at least one candidate string this guard can actually resolve to a
//   comparable LOCAL FILESYSTEM path -- never by whether its scheme name appears on a
//   list. Any `scheme://...`-shaped target (recognized or not, `local://` and `ssh://`
//   alike) is, by construction, a reference into an address space this guard has no
//   local path for -- an internal store, an MCP resource, a remote host -- so it never
//   contributes a path candidate. A blank (empty or all-whitespace) string, a missing
//   `path` field, a non-string `path`, and an `edit` input with no `[<path>#<TAG>]`
//   hashline all likewise contribute zero candidates, for the same underlying reason:
//   there is no local path here to derive. `evaluateWorktreeFenceGuard` denies whenever
//   the derived candidate set is empty, full stop -- a scheme invented tomorrow, or an
//   argument shape nobody anticipated, fails closed automatically, without anyone
//   touching this file. See the `Guard` section and `classifyRaw` below for the
//   mechanism, and this card's PR body for the over-denial measurement (grepping every
//   seat definition in this repo for a `write`/`edit` call naming an internal URI as its
//   target) that backs treating this as a safe default rather than a breaking one.
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
// (#297) that defeated it structurally, addressed above (twice: attempt 1 closed it for
// one named scheme, attempt 2 closes it structurally for every scheme and every
// zero-reading argument shape). Its limits, stated plainly: it decides on `ctx.cwd` and
// the tool call's OWN declared path/edit-target input, resolved to a local filesystem
// path. It has no visibility into a write that reaches the filesystem through any
// channel this hook never sees a local path for (a bash-invoked script), it denies
// rather than silently permits any target it cannot derive to a local path at all
// (fixed structurally below, not by scheme name), and it cannot distinguish a hardlinked
// name inside the seat's own worktree from the sibling-worktree file it silently
// aliases (disclosed, not fixed, at the realpath comparison below). Deliberate evasion
// defeats it; it only ever caught the naive and the accidental.

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
// Guard (tripwire, not enforcement -- see the file header above) -- the ship seat's
// edits stay inside its own `.worktrees/<branch>`
//
// A literal per-role rule, per ADR-0007: "Ship works in its own worktree; never merges"
// -> "a hook fences `edit`/`write` to that path". This section documents that TRIPWIRE,
// not an enforcement claim: it catches the naive and the accidental case it can see
// (`ctx.cwd` and the call's own declared path input), and nothing more -- deliberate
// evasion through a channel this hook has no visibility into is out of scope by
// construction, per the file header's own disclosure. Scoped to `agent === "ship"`
// specifically, not "any subagent with write/edit tools" -- today only `ship` declares
// those tools, but the role check is what the card actually specifies, and it stays
// correct even if a future subagent type gains write/edit tools without also being
// meant to hold this invariant.
//
// Soundness (issues #296 and #297): this predicate decides on `event.input.path`,
// structured, normalized input the hook genuinely receives for `write`/`edit` -- never
// on command text. Five defects were found live and fixed here:
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
//    every candidate is checked, and any one escaping is a block. A candidate that is
//    itself `scheme://...`-shaped is never given a filesystem-path reading at all (see
//    defect 4 below) -- it is opaque to this guard by construction, not exempted by an
//    allowlist.
// 3. Case false-denial: on a case-insensitive filesystem (APFS default), a legitimate
//    own-worktree path reached via different case (e.g. `/users/...` for a worktree
//    actually mounted at `/Users/...`) was denied as outside, because the old check
//    compared path strings verbatim. The same `realOf` resolution that fixes (1) fixes
//    this for free: `fs.realpathSync`/`fs.existsSync` resolve the SAME on-disk entry
//    regardless of the case used to reach it and return it in its ONE canonical case, so
//    the two real paths this guard compares always agree on case when they name the
//    same real file -- no separate case-normalization step is needed, attempted, or
//    assumed to apply globally here.
// 4. Zero-derivable-path ALLOW (issue #297, closed structurally at attempt 2): zero
//    candidate readings used to mean "nothing to check", unconditionally -- true for a
//    call this guard genuinely cannot form an opinion about, false for a call whose
//    target simply isn't a local path at all. `classifyRaw` below never asks "is this
//    scheme's name on a list" -- it asks "does this string look like a local filesystem
//    path at all", structurally: a `scheme://...`-shaped string (ANY scheme, not an
//    enumerated set), a blank string, or a raw-candidate list that is empty to begin
//    with (a missing `path` field, a non-string `path`, an `edit` with no hashline
//    header) all produce zero path readings, and `evaluateWorktreeFenceGuard` denies on
//    zero readings, naming the raw input, before it ever reaches a path comparison.
//    Adding a scheme to OMP tomorrow needs no edit here: an unrecognized `scheme://...`
//    was already opaque to this guard before it had a name.
// 5. Blank/malformed-argument ALLOW (issue #297, attempt 2): `write {}`, a non-string
//    `path`, an `edit` whose `input` text carries no `[<path>#<TAG>]` header, and an
//    empty or all-whitespace `path` string each used to produce zero raw candidates and
//    therefore ALLOW, for the identical reason as (4) -- there is no local path to
//    derive. These now deny for the same structural reason, not as special cases.
//
// Root and target are each resolved independently to one canonical real path, then
// compared with a single `path.relative` (never a walk comparing inode identity up two
// separate ancestor chains) -- which stays sound even when NEITHER path exists on disk
// at all (both `realOf` calls degrade to their own lexical input unchanged, reproducing
// the pre-#296 lexical comparison exactly), so this fix is additive: every path this
// guard already decided correctly, it still decides identically.
// ---------------------------------------------------------------------------------------

const WORKTREES_SEGMENT = ".worktrees";

const INTERNAL_URI_SCHEME_RE = /^([a-zA-Z][a-zA-Z0-9+.-]*):\/\//;

/** One raw `write`/`edit` path-candidate string, classified `"path"` (evaluate as a
 * filesystem path) or `"unresolvable"` (this guard cannot derive any local filesystem
 * path from it -- issue #297). A candidate is `"unresolvable"` when it is blank (empty
 * or all-whitespace -- there is no leaf name to derive a path from) or shaped like
 * `scheme://...` for ANY scheme, recognized or not: such a string names an address
 * space this guard has no local path for (an internal store, an MCP resource, a remote
 * host, or a scheme nobody has invented yet), by construction, never by membership in
 * an enumerated table. There is no allowlist of "known-safe" schemes here -- see the
 * file header's account of why attempt 1's `IGNORED_URI_SCHEMES` table was itself the
 * defect: a scheme absent from a table is indistinguishable, to a table lookup, from a
 * scheme that is merely new. A `"path"` reading is the literal string itself, and --
 * since OMP's own `write`/`edit` accept `archive.ext:inner/path`/`db.sqlite:table`
 * selector syntax -- the substring before its first `:`, when one is present and
 * non-empty. Never guesses which reading is "the" intended one; the caller checks all
 * of them and blocks if any escapes (issue #296). */
type Reading = { kind: "path" | "unresolvable"; value: string };

function classifyRaw(raw: string): Reading[] {
  if (raw.trim() === "") return [{ kind: "unresolvable", value: raw === "" ? "(empty path)" : "(blank path)" }];
  if (INTERNAL_URI_SCHEME_RE.test(raw)) return [{ kind: "unresolvable", value: raw }];
  const readings = new Set<string>([raw]);
  const colonIdx = raw.indexOf(":");
  if (colonIdx > 0) readings.add(raw.slice(0, colonIdx));
  return [...readings].map((value): Reading => ({ kind: "path", value }));
}

/** Every raw `write`/`edit` path-candidate string this hook genuinely receives for a
 * call, before scheme classification: `write`'s own `path` field, or every hashline
 * header (`[<path>#<TAG>]`) `edit`'s own `input` text carries. An empty array here (a
 * missing/non-string `write` `path`, or an `edit` `input` with no hashline match) is
 * itself a zero-derivable-path call -- `evaluateWorktreeFenceGuard` denies on it, not
 * merely on a raw string that turned out unresolvable. */
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

/** Every plausible LOCAL filesystem-path reading (issue #296) of this call's raw
 * candidates -- never an unresolvable one; see `extractUnresolvableTargets` for those.
 * An empty result means this call has zero derivable local paths, for any reason:
 * `evaluateWorktreeFenceGuard` denies whenever this is empty (issue #297). */
export function extractCandidatePaths(toolName: string, input: unknown): string[] {
  return [
    ...new Set(
      rawCandidates(toolName, input)
        .flatMap(classifyRaw)
        .filter((r) => r.kind === "path")
        .map((r) => r.value),
    ),
  ];
}

/** Every raw candidate (or a description of a missing one) this call names that this
 * guard cannot derive to a local path to compare -- an internal-URI-shaped target of
 * any scheme, or a blank string (issue #297). Does NOT include the case where
 * `rawCandidates` itself returned nothing at all (a missing/malformed argument shape);
 * `evaluateWorktreeFenceGuard`'s own deny path names that case separately, since there
 * is no raw string to report here. */
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

/** A human-readable name for a call that produced zero RAW candidate strings at all --
 * `write` with no `path` key (or a non-string one), or `edit` whose `input` text
 * carries no `[<path>#<TAG>]` hashline header. There is no raw target string to quote
 * in this case (unlike an unresolvable one, which names itself), so this names the
 * call's own input shape instead, bounded, so the deny reason still says what was
 * denied and why. */
function describeMissingTarget(toolName: string, input: unknown): string {
  let repr: string;
  try {
    repr = JSON.stringify(input) ?? String(input);
  } catch {
    repr = String(input);
  }
  if (repr.length > 200) repr = `${repr.slice(0, 200)}…`;
  const expected = toolName === "write" ? "no string `path` field" : "no `[<path>#<TAG>]` hashline target";
  return `${expected} (raw ${toolName} input: ${repr})`;
}

export function evaluateWorktreeFenceGuard(
  agent: string | undefined,
  toolName: string,
  input: unknown,
  cwd: string,
): { block: true; reason: string } | undefined {
  if (agent !== "ship" || (toolName !== "write" && toolName !== "edit")) return undefined;
  const raw = rawCandidates(toolName, input);
  const readings = raw.flatMap(classifyRaw);
  const unresolvable = readings.filter((r) => r.kind === "unresolvable").map((r) => r.value);
  const candidates = [...new Set(readings.filter((r) => r.kind === "path").map((r) => r.value))];
  if (candidates.length === 0) {
    const named = unresolvable.length > 0 ? unresolvable.join(", ") : describeMissingTarget(toolName, input);
    return {
      block: true,
      reason:
        `orc-seat: ${toolName} names ${named}, which this guard cannot derive to any local filesystem path to ` +
        "compare against this ship seat's own worktree; a write/edit with zero derivable local paths is denied, " +
        "never silently allowed (issue #297) -- derivability drives this decision, never an enumerated scheme list.",
    };
  }
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
