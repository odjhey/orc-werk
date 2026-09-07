// TASK-M5-005 -- .omp/extensions/orc-seat.ts
//
// What this hook enforces, and only this: a `ship` seat's `write`/`edit` tool calls stay
// inside its OWN `.worktrees/<branch>` directory -- never a sibling seat's worktree,
// never the primary checkout. This is the sole guard, of ADR-0007's original four-guard
// design (record-before-yield, no subagent `gh pr merge`, verify push/commit/comment/
// review denial, ship worktree fence), that survived four adversarial audit attempts
// unmodified: it decides on `ctx.cwd`, structural context this hook genuinely receives,
// never on the text of a command.
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
// another.
//
// Per the operator's 2026-09-07 descope ruling (recorded on this task card, citing run
// `task-m5-005-guards` seq 16 and issue #290), this hook does not re-attempt any of the
// four. The controls move to where the structural information they need actually lives,
// outside a `tool_call` hook's reach:
//
// - Push/merge restriction: as of a 2026-09-07 read-back of `gh api
//   repos/odjhey/orc-werk/branches/master/protection --jq '[.restrictions,
//   .required_pull_request_reviews.required_approving_review_count]'`
//   (`[null, 0]`), server-side GitHub branch protection blocks any identity
//   from writing directly to `master` -- but it cannot enforce a SEAT-scoped
//   rule (no subagent `gh pr merge`; verify cannot push/commit/comment/
//   review) at all: `restrictions` is the one field that binds a push/merge
//   restriction to a specific actor, it reads `null` here, and even
//   populated it keys on GitHub user/team/app identity, never on the
//   agent-role of the one shared credential every seat in this repo
//   authenticates as. Per `ADR-0007`'s dated amendment (PR #292, rung 4),
//   that per-seat restriction is an open, unenforced residue -- prose
//   (`ship.md`/`verify.md`) plus after-the-fact ledger/PR-history
//   detection, never this hook and never branch protection. Re-run the
//   `gh api` call above before relying on this paragraph; it is a
//   configuration read-back, not a standing fact.
// - Record-before-yield needs no hook at all: the orc state machine already enforces it
//   structurally -- a work with no recorded `FACT-EXEC-SETTLED` stays non-terminal and
//   the run cannot reach a terminal state, independent of anything a session's own tool
//   calls do or don't do.
//
// What remains below -- the worktree fence -- was verified live across all four attempts
// to deny sibling-worktree and primary-checkout writes while permitting a seat's own
// (see this card's PR body for the live commands and observed denials/allows). Its own
// limit, stated plainly: it decides on `ctx.cwd` and the tool call's OWN declared
// path/edit-target input. It has no visibility into a write that reaches the filesystem
// through any channel this hook never sees a path for (for example a bash-invoked
// script, as opposed to the `write`/`edit` tools themselves).

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
// Soundness (issue #296): this predicate decides on `event.input.path`, structured,
// normalized input the hook genuinely receives for `write`/`edit` -- never on command
// text. Three defects were found live and fixed here, all in HOW that path is compared,
// never in the decision to compare it at all:
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
 * descriptions) as never denoting a real filesystem path -- `local://plan.md` and
 * similar resolve against an internal store, not `fs`, so they are the one class of
 * `:`-containing candidate this guard does not evaluate as a filesystem path. Any OTHER
 * `scheme://...`-shaped string (e.g. an attacker-chosen `colon://...`) is NOT in this
 * table and therefore IS evaluated -- unlike the prior, unconditional `://` skip issue
 * #296 found bypassable. */
const INTERNAL_URI_SCHEMES: Record<string, true> = {
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
  ssh: true,
  omp: true,
};

const INTERNAL_URI_SCHEME_RE = /^([a-zA-Z][a-zA-Z0-9+.-]*):\/\//;

/** Every plausible filesystem-path reading of a raw `write`/`edit` path candidate
 * (issue #296): the literal string itself, and -- since OMP's own `write`/`edit` accept
 * `archive.ext:inner/path` and `db.sqlite:table` selector syntax -- the substring before
 * its first `:`, when one is present. Never guesses which reading is "the" intended one;
 * the caller checks all of them and blocks if any escapes. Recognized internal-URI
 * schemes (`local://`, ...) are the one exemption: they never touch the filesystem, so
 * they contribute no reading at all. */
function pathReadings(raw: string): string[] {
  const schemeMatch = INTERNAL_URI_SCHEME_RE.exec(raw);
  if (schemeMatch && INTERNAL_URI_SCHEMES[schemeMatch[1].toLowerCase()]) return [];
  const readings = new Set<string>([raw]);
  const colonIdx = raw.indexOf(":");
  if (colonIdx !== -1) readings.add(raw.slice(0, colonIdx));
  return [...readings];
}

export function extractCandidatePaths(toolName: string, input: unknown): string[] {
  if (!input || typeof input !== "object") return [];
  if (toolName === "write") {
    if (!("path" in input)) return [];
    const raw = (input as Record<string, unknown>).path;
    if (typeof raw !== "string") return [];
    return pathReadings(raw);
  }
  if (toolName === "edit") {
    if (!("input" in input)) return [];
    const raw = (input as Record<string, unknown>).input;
    if (typeof raw !== "string") return [];
    return [...raw.matchAll(/\[([^\]#\n]+)#[0-9A-Fa-f]{4}\]/g)]
      .map((match) => match[1])
      .flatMap((candidate) => pathReadings(candidate));
  }
  return [];
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
 * every decision this guard already made correctly. */
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
