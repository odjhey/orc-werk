// Colocated test for `orc-seat.ts` (TASK-M5-005). Run with:
//   bun test ./.omp/extensions/__tests__/orc-seat.test.ts
//
// Lives in a `__tests__/` subdirectory, not directly under `.omp/extensions/`, so native
// `omp` extension auto-discovery never loads it as a production extension: per
// `omp://extension-loading.md`, native discovery scans the extensions root for direct
// `*.ts` files and descends only one level into a subdirectory for `index.ts` or
// `package.json` -- neither applies to a differently-named file one level down. (Prior
// to this move, every native repo-root `omp -p` startup emitted a real extension-load
// failure -- `Cannot use describe outside of the test runner` -- because the flat
// `orc-seat.test.ts` sat directly in the scanned directory.)
//
// This suite proves the retained worktree-fence guard red-then-green at the *wiring*
// level: it installs the real, unmodified `orcSeat` factory behind a minimal fake
// `ExtensionAPI` and drives the exact event/ctx shapes captured from real
// `omp -p --tools task` spawns against the shipped `.omp/extensions/orc-seat.ts` (see
// this card's PR body for the live-process commands and raw output -- the strongest
// form of this proof; this file is the fast, deterministic, CI-repeatable form of the
// same claim).
//
// The harness, `attempt`: it runs the tool call through the guard (or through no guard
// at all, for red), and if -- and only if -- the guard does not block, it performs the
// operation's OBSERVABLE SIDE EFFECT by appending to a `sink` array standing in for "OMP
// actually executed this call for real" (writing a file). Red proves the violating
// write's side effect actually lands with no guard in the way. Green proves the
// identical write's side effect never lands once the real `orcSeat(pi)` factory is
// installed, and that the block carries the guard's own reason. A regression that
// silently stops denying (e.g. the guard accidentally returning `undefined`) fails the
// green assertion on `sink`, not merely on the block's shape -- this is what makes the
// pair non-hollow.
//
// This guard keys off `session_init.agent`, read via a fake `ctx.sessionManager` below
// -- exactly the shape a real `ctx.sessionManager` returns (confirmed against real
// session transcript files; see the block comment at the top of `../orc-seat.ts` and
// this card's PR body for the live citation).
//
// This file imports ONLY the four symbols `../orc-seat.ts` has exported since before
// this card's own attempt 1 (`evaluateWorktreeFenceGuard`, `extractCandidatePaths`,
// `extractUnresolvableTargets`, the default `orcSeat` factory) -- never an internal
// helper (`classifyRaw`, `rawCandidates`, the removed scheme tables/regexes). This is
// what makes the swap below EXECUTABLE: this exact test file's module load succeeds
// against any of these revisions, so the swap proves a real assertion-level diff, never
// a module-load crash standing in for one (ledger `task-m5-005-sensor` seq 16, REJECT
// finding 2 -- the prior attempt's swap target, `git show ef093a3:...`, predates
// `extractUnresolvableTargets`'s introduction entirely and was never loadable; the
// correct "pre-change" baseline for attempt 2's own fix is this run's own attempt 1,
// head `623f2cf`, which already exports all four symbols this file uses). Reproduce
// the full attempt-1-to-HEAD swap yourself (see this card's PR body for the exact
// counts, dated):
//
//   git show 623f2cf:.omp/extensions/orc-seat.ts | sponge .omp/extensions/orc-seat.ts
//   bun test ./.omp/extensions/__tests__/orc-seat.test.ts   # RED
//   git checkout HEAD -- .omp/extensions/orc-seat.ts        # or: git show <this commit>:... | sponge ...
//   bun test ./.omp/extensions/__tests__/orc-seat.test.ts   # GREEN
//
// This delivery (attempt 3) additionally fixes an over-denial in attempt 2's own fix
// (ledger `task-m5-005-sensor` seq 26, REJECT finding 1): the dedicated swap for THAT
// fix uses attempt 2's own head, `6d44ff4`, as the RED baseline instead (see this card's
// PR body for the exact counts, dated):
//
//   git show 6d44ff4:.omp/extensions/orc-seat.ts | sponge .omp/extensions/orc-seat.ts
//   bun test ./.omp/extensions/__tests__/orc-seat.test.ts   # RED (exactly the 3 conflict/local tests below fail)
//   git checkout HEAD -- .omp/extensions/orc-seat.ts
//   bun test ./.omp/extensions/__tests__/orc-seat.test.ts   # GREEN

import { describe, expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import orcSeat, { evaluateWorktreeFenceGuard, extractCandidatePaths, extractUnresolvableTargets } from "../orc-seat.ts";

type Handler = (event: unknown, ctx: unknown) => Promise<{ block: true; reason: string } | undefined>;

/** Installs the real `orcSeat` factory behind a fake `pi.on`, capturing its `tool_call`
 * handler. A test double only for `.on`, the one method `orcSeat` calls -- justified
 * cast, no broader shape is claimed or read. */
function installOrcSeat(): { toolCall: Handler } {
  const handlers = new Map<string, Handler>();
  const pi = { on: (name: string, handler: Handler) => handlers.set(name, handler) } as unknown as ExtensionAPI;
  orcSeat(pi);
  const toolCall = handlers.get("tool_call");
  if (!toolCall) throw new Error("orcSeat did not register a tool_call handler");
  return { toolCall };
}

// Subagent session-file shape, exactly as captured live (see the block comment at the
// top of `../orc-seat.ts` for the full citation).
const SUBAGENT_SESSION_FILE =
  "/Users/x/.omp/agent/sessions/-proj-repo/2026-09-07T01-39-51-553Z_01a07985-9081-7610-846b-08eb4845778b/MobileGuan.jsonl";

/** `agent` mirrors the real `session_init.agent` field found on a subagent's own
 * transcript entries (see orc-seat.ts's header comment for the live citation); pass
 * `undefined` for a root session, which carries no `session_init` entry at all. */
function ctxFor(sessionFile: string, sessionId: string, cwd: string, agent?: string) {
  return {
    cwd,
    sessionManager: {
      getSessionId: () => sessionId,
      getSessionFile: () => sessionFile,
      getEntries: () => (agent === undefined ? [] : [{ type: "session_init", agent }]),
    },
  };
}

/** Shared red/green harness (see the file header for the full rationale): runs `event`
 * through `toolCall` (or through nothing, for red, when `toolCall` is `undefined`), and
 * appends `effect` to `sink` only when the call is NOT blocked -- i.e. only when OMP
 * would actually have gone on to perform the real operation. */
async function attempt(
  toolCall: Handler | undefined,
  event: unknown,
  ctx: unknown,
  sink: string[],
  effect: string,
): Promise<{ block: true; reason: string } | undefined> {
  const result = toolCall ? await toolCall(event, ctx) : undefined;
  if (!result) sink.push(effect);
  return result;
}

describe("worktree fence: the ship seat's write/edit fence (own worktree, not any worktree)", () => {
  const writeEvent = { toolName: "write", input: { path: "/repo/.worktrees/sibling/file.ts" } };
  const shipCtx = ctxFor(SUBAGENT_SESSION_FILE, "r4", "/repo/.worktrees/task-x", "ship");

  test("RED — a ship seat's write into a sibling worktree actually lands with no guard installed", async () => {
    const sink: string[] = [];
    const result = await attempt(undefined, writeEvent, shipCtx, sink, "wrote");
    expect(result).toBeUndefined();
    expect(sink).toEqual(["wrote"]);
  });

  test("GREEN — orc-seat denies a ship seat's write into a *sibling* worktree, not just outside all worktrees", async () => {
    // an earlier defect: the old guard only checked for the presence of a `.worktrees`
    // segment anywhere in the resolved path, so a ship at `/repo/.worktrees/task-x`
    // could write into `/repo/.worktrees/sibling/file.ts`.
    const { toolCall } = installOrcSeat();
    const sink: string[] = [];
    const result = await attempt(toolCall, writeEvent, shipCtx, sink, "wrote");
    expect(result).toEqual({ block: true, reason: expect.stringContaining("own worktree") });
    expect(sink).toEqual([]);
  });

  test("GREEN — orc-seat denies a ship seat's write into the primary checkout", async () => {
    const primaryCtx = ctxFor(SUBAGENT_SESSION_FILE, "r4b", "/repo/.worktrees/task-x", "ship");
    const escapeEvent = { toolName: "write", input: { path: "/repo/src/foo.ts" } };
    const { toolCall } = installOrcSeat();
    const sink: string[] = [];
    const result = await attempt(toolCall, escapeEvent, primaryCtx, sink, "wrote");
    expect(result).toEqual({ block: true, reason: expect.stringContaining("own worktree") });
    expect(sink).toEqual([]);
  });

  test("GREEN — a ship seat's write outside any .worktrees/<branch> directory is denied", () => {
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "/tmp/outside.txt" }, "/repo/.worktrees/x");
    expect(result).toEqual({ block: true, reason: expect.stringContaining(".worktrees") });
  });

  test("a ship whose cwd is the primary checkout (no derivable own worktree) is fenced from everything", () => {
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "src/foo.ts" }, "/repo");
    expect(result).toEqual({ block: true, reason: expect.stringContaining("own worktree") });
  });

  test("ALLOWED — a ship seat's write inside its own .worktrees/<branch> is not blocked", async () => {
    const insideEvent = { toolName: "write", input: { path: "inside.txt" } };
    const insideCtx = ctxFor(SUBAGENT_SESSION_FILE, "r4c", "/repo/.worktrees/task-x", "ship");
    const { toolCall } = installOrcSeat();
    const sink: string[] = [];
    const result = await attempt(toolCall, insideEvent, insideCtx, sink, "wrote");
    expect(result).toBeUndefined();
    expect(sink).toEqual(["wrote"]);
  });

  test("ALLOWED — a nested path still inside the seat's own worktree is not blocked", () => {
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "src/deep/file.ts" }, "/repo/.worktrees/task-x");
    expect(result).toBeUndefined();
  });

  test("edit targets are read from the hashline header, not the patch body text", () => {
    const input = { input: "[/tmp/outside.ts#A1B2]\nPUT 1.=1:\n+x\n" };
    expect(extractCandidatePaths("edit", input)).toEqual(["/tmp/outside.ts"]);
    const escaping = evaluateWorktreeFenceGuard("ship", "edit", input, "/repo/.worktrees/task-x");
    expect(escaping).toEqual({ block: true, reason: expect.stringContaining("/tmp/outside.ts") });
  });

  test("a root session is never subject to this guard", async () => {
    const rootCtx = ctxFor(SUBAGENT_SESSION_FILE, "r4d", "/repo/.worktrees/x", undefined);
    const outsideEvent = { toolName: "write", input: { path: "/tmp/outside.txt" } };
    const { toolCall } = installOrcSeat();
    const sink: string[] = [];
    const result = await attempt(toolCall, outsideEvent, rootCtx, sink, "wrote");
    expect(result).toBeUndefined();
    expect(sink).toEqual(["wrote"]);
  });

  test("a non-ship seat's write is not this guard's concern (scout/verify hold no write/edit tool today)", () => {
    expect(evaluateWorktreeFenceGuard("verify", "write", { path: "/tmp/outside.txt" }, "/repo/.worktrees/x")).toBeUndefined();
  });

  test("extractCandidatePaths never treats an internal-URI-shaped target as a filesystem path", () => {
    expect(extractCandidatePaths("write", { path: "local://plan.md" })).toEqual([]);
  });

  test("a bash tool call is never this guard's concern (it only fences write/edit)", async () => {
    const bashEvent = { toolName: "bash", input: { command: "git push origin +master" } };
    const { toolCall } = installOrcSeat();
    const sink: string[] = [];
    const result = await attempt(toolCall, bashEvent, shipCtx, sink, "ran");
    expect(result).toBeUndefined();
    expect(sink).toEqual(["ran"]);
  });
});

// ---------------------------------------------------------------------------------------
// Soundness regressions (issue #296): each test below drives `evaluateWorktreeFenceGuard`
// against a REAL, on-disk fixture (symlinks and mixed-case directories only exist as
// real filesystem objects, never as string literals the guard is fed without a matching
// disk object) so the assertion is a genuine filesystem-identity claim, not a string
// comparison. Each one FAILS against the pre-#296 implementation (`git show
// 37b8596:.omp/extensions/orc-seat.ts`, this card's own attempt-2 delivery, which
// compared lexical `path.resolve` strings, dropped everything after a path's first
// `:`, and skipped any `://`-containing string outright) and PASSES against the fixed
// one below -- verified by literally swapping this file's sibling `../orc-seat.ts` for
// each revision and re-running `bun test ./.omp/extensions/__tests__/orc-seat.test.ts`
// (see this card's PR body for both raw runs and their pass/fail counts).
// ---------------------------------------------------------------------------------------

describe("worktree fence soundness (issue #296): symlinks, colon/scheme selectors, case", () => {
  function makeShipWorktree(branch: string): { tmpRoot: string; shipCwd: string } {
    const tmpRoot = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "orc-seat-sound-")));
    const shipCwd = path.join(tmpRoot, "repo", ".worktrees", branch);
    fs.mkdirSync(shipCwd, { recursive: true });
    return { tmpRoot, shipCwd };
  }

  test("RED-then-GREEN — a write through a symlink whose real target is outside the seat's own worktree is denied", () => {
    const { tmpRoot, shipCwd } = makeShipWorktree("task-x");
    const outside = path.join(tmpRoot, "outside-probe");
    fs.mkdirSync(outside);
    fs.symlinkSync(outside, path.join(shipCwd, "escape-link"));
    // A lexical `path.resolve(shipCwd, "escape-link/x.txt")` stays textually under
    // `shipCwd` and never resolves the symlink -- the pre-#296 implementation allowed
    // this (verified: `evaluateWorktreeFenceGuard` from `37b8596` returns `undefined`
    // here). The fixed guard resolves `escape-link` to `outside-probe`'s own identity
    // via `fs.statSync` and denies it.
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "escape-link/x.txt" }, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining("own worktree") });
  });

  test("RED-then-GREEN — a colon-split path (archive/table-selector reading) that escapes via its literal reading is denied", () => {
    const { shipCwd } = makeShipWorktree("task-x");
    // The pre-#296 extractor kept only `raw.split(":")[0]` ("./safe", which stays
    // inside `shipCwd` and hides the escape); this raw string is this card's own
    // §296 example. The fixed `pathReadings` also evaluates the literal full string,
    // which resolves to the `.worktrees` sibling `outside-probe` -- outside this
    // seat's own worktree -- and blocks on that reading.
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "./safe:/../../outside-probe/x.txt" }, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining("own worktree") });
  });

  test("RED-then-GREEN — a path whose full string is not scheme-shaped (leading `./`) is still evaluated as a filesystem path", () => {
    const { shipCwd } = makeShipWorktree("task-x");
    // The pre-#296 extractor skipped any candidate containing `://` outright
    // (`raw.includes("://")`), so this candidate produced zero readings and the guard
    // never even ran a comparison. `INTERNAL_URI_SCHEME_RE` is anchored at the string's
    // START (`^scheme://`); this raw string starts with `./`, not a scheme, so it is
    // never classified `"unresolvable"` at all -- it is an ordinary (if odd-looking)
    // filesystem path, and the fixed extractor still evaluates it and finds the literal
    // reading resolves to the `.worktrees` sibling `outside-probe`.
    const result = evaluateWorktreeFenceGuard(
      "ship",
      "write",
      { path: "./colon://../../outside-probe/scheme-skip-escape.txt" },
      shipCwd,
    );
    expect(result).toEqual({ block: true, reason: expect.stringContaining("own worktree") });
  });

  test("RED-then-GREEN — a genuinely-inside path reached via different case is permitted, not falsely denied", () => {
    const { shipCwd } = makeShipWorktree("CamelBranch");
    // The pre-#296 implementation compared `path.relative(root, resolved)` as plain
    // strings: an all-lowercase reading of the same real directory does not textually
    // start with the mixed-case `root`, so `path.relative` produces a `../`-prefixed
    // result and the old guard denied a write that is genuinely inside the seat's own
    // worktree. This only exercises a real false-denial on a case-insensitive
    // filesystem (APFS default); skip harmlessly elsewhere.
    const lowercased = shipCwd.replace(/CamelBranch$/, "camelbranch");
    if (fs.existsSync(lowercased) && fs.statSync(lowercased).ino !== fs.statSync(shipCwd).ino) {
      throw new Error("fixture assumption failed: this filesystem is not case-insensitive as expected");
    }
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: path.join(lowercased, "inside.txt") }, shipCwd);
    expect(result).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------------------
// Fail-closed on zero derivable local paths (issue #297): the sole surviving guard's own
// "zero path candidates means nothing to check" default silently turned into ALLOW for a
// `write`/`edit` target this guard genuinely cannot resolve to a local path. Attempt 1 of
// this run (head `623f2cf`) closed this for `ssh://` alone, via an `UNRESOLVABLE_URI_
// SCHEMES` table holding exactly that one name, while an `IGNORED_URI_SCHEMES` table of
// eleven OTHER recognized schemes -- and any zero-raw-candidate call at all (`write {}`,
// a non-string `path`, `edit` with no hashline, a blank `path`) -- still fell through to
// ALLOW: reproduced live by an independent verify seat (ledger `task-m5-005-sensor` seq
// 16, REJECT finding 1) via a real `bun run` fixture probe. Attempt 2 replaced both
// tables with one structural rule in `classifyRaw`/`evaluateWorktreeFenceGuard`: a call
// is denied whenever it yields zero candidates this guard can derive to a LOCAL
// filesystem path, regardless of why -- no scheme name is ever consulted against a list.
// That rule over-denied: an independent verify seat (ledger `task-m5-005-sensor` seq 26,
// REJECT finding 1) reproduced live, against head `6d44ff4`, that a `conflict://<id>`
// write -- OMP's own supported merge-conflict-resolution transport -- was denied
// identically to a genuine escape. Attempt 3 (this delivery) narrows the rule one more
// step: `classifyRaw` gives `local://...` and unscoped `conflict://<id>`/`conflict://*`
// a third reading kind, `"adjudicated-inside"`, on the ground that the write tool itself
// resolves and revalidates both against a real on-disk file (see `../orc-seat.ts`'s
// header for the full harness-contract citation), and
// `evaluateWorktreeFenceGuard` ALLOWs a call whose only candidates are that kind. Each
// RED-then-GREEN pair below FAILS against the implementation named in its own comment
// and PASSES against the fixed one in this delivery -- see this file's header for the
// exact swap commands and this card's PR body for both raw run outputs.
// ---------------------------------------------------------------------------------------

describe("worktree fence fail-closed on zero derivable local paths (issue #297, attempts 2-3: derivability, not a scheme list)", () => {
  function makeShipWorktree(branch: string): { shipCwd: string } {
    const tmpRoot = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "orc-seat-unresolvable-")));
    const shipCwd = path.join(tmpRoot, "repo", ".worktrees", branch);
    fs.mkdirSync(shipCwd, { recursive: true });
    return { shipCwd };
  }

  test("RED-then-GREEN — an ssh:// write target (no local path to compare) is denied, not silently allowed", () => {
    const { shipCwd } = makeShipWorktree("task-x");
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "ssh://tiny/tmp/orc-seat-escape.txt" }, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining("ssh://tiny/tmp/orc-seat-escape.txt") });
  });

  test("RED-then-GREEN — an ssh:// edit target named in the hashline header is denied, not silently allowed", () => {
    const { shipCwd } = makeShipWorktree("task-x");
    const input = { input: "[ssh://tiny/tmp/orc-seat-escape.txt#A1B2]\nPUT 1.=1:\n+x\n" };
    const result = evaluateWorktreeFenceGuard("ship", "edit", input, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining("ssh://tiny/tmp/orc-seat-escape.txt") });
  });

  test("extractUnresolvableTargets surfaces the ssh:// candidate; extractCandidatePaths does not", () => {
    const input = { path: "ssh://tiny/tmp/orc-seat-escape.txt" };
    expect(extractUnresolvableTargets("write", input)).toEqual(["ssh://tiny/tmp/orc-seat-escape.txt"]);
    expect(extractCandidatePaths("write", input)).toEqual([]);
  });

  test("ALLOWED — the seat's own genuinely-inside write is unaffected by the fail-closed check", () => {
    const { shipCwd } = makeShipWorktree("task-x");
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "inside.txt" }, shipCwd);
    expect(result).toBeUndefined();
  });

  // Every internal-URI scheme this repo's own `read`/`write`/`edit` tool surface
  // documents (`omp://internal-schemes.md`-adjacent tool descriptions: `memory://`,
  // `history://`, `agent://`, `rule://`, `skill://`, `mcp://`, `issue://`, `pr://`,
  // `omp://`) plus `artifact://` and `ssh://` -- eleven in total. `local://` is
  // deliberately NOT in this list: attempt 3 (below) moves it to ALLOW-by-adjudication,
  // the one intentional behaviour change this delivery makes -- see `../orc-seat.ts`'s
  // header for why. Attempt 1 ALLOWed all eleven of these unconditionally
  // (`IGNORED_URI_SCHEMES`); this loop proves none of them is special-cased any more.
  const ELEVEN_SCHEMES = [
    "memory",
    "artifact",
    "history",
    "agent",
    "rule",
    "skill",
    "mcp",
    "issue",
    "pr",
    "omp",
    "ssh",
  ] as const;

  for (const scheme of ELEVEN_SCHEMES) {
    test(`RED-then-GREEN — a write targeting \`${scheme}://...\` is denied for zero derivable local paths, not silently allowed`, () => {
      const { shipCwd } = makeShipWorktree(`task-scheme-${scheme}`);
      const target = `${scheme}://probe/target.txt`;
      const result = evaluateWorktreeFenceGuard("ship", "write", { path: target }, shipCwd);
      expect(result).toEqual({ block: true, reason: expect.stringContaining(target) });
      expect(extractUnresolvableTargets("write", { path: target })).toEqual([target]);
      expect(extractCandidatePaths("write", { path: target })).toEqual([]);
    });
  }

  test("RED-then-GREEN — a write targeting a novel, never-seen scheme (`zzfuture://...`) is denied, proving this is derivability-driven and not a name lookup", () => {
    // `zzfuture` names no scheme this repo's source has ever mentioned (ledger
    // `task-m5-005-sensor` seq 26, VERIFIED finding 2: an independent verify seat's own
    // repo-wide source search found no `zzfuture` occurrence anywhere). A name lookup
    // (attempt 1's tables) could only ever deny schemes someone remembered to list;
    // this guard denies it purely because it is `scheme://`-shaped and neither
    // `local://` nor a writable `conflict://` — no table entry for `zzfuture` exists or
    // is needed.
    const { shipCwd } = makeShipWorktree("task-scheme-zzfuture");
    const target = "zzfuture://probe/target.txt";
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: target }, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining(target) });
  });

  // Malformed/missing-argument shapes: attempt 1 ALLOWed each of these too, for the
  // identical underlying reason as the eleven schemes above -- `rawCandidates` (or its
  // downstream classification) produced zero readings, and zero readings meant ALLOW.
  test("RED-then-GREEN — write with an empty object (no `path` field at all) is denied, not silently allowed", () => {
    const { shipCwd } = makeShipWorktree("task-malformed-empty-object");
    const result = evaluateWorktreeFenceGuard("ship", "write", {}, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining("no string `path` field") });
  });

  test("RED-then-GREEN — write with a non-string `path` is denied, not silently allowed", () => {
    const { shipCwd } = makeShipWorktree("task-malformed-non-string");
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: 42 }, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining("no string `path` field") });
  });

  test("RED-then-GREEN — edit whose `input` text carries no `[<path>#<TAG>]` hashline header is denied, not silently allowed", () => {
    const { shipCwd } = makeShipWorktree("task-malformed-no-hashline");
    const result = evaluateWorktreeFenceGuard("ship", "edit", { input: "PUT 1.=1:\n+x\n" }, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining("no `[<path>#<TAG>]` hashline target") });
  });

  test("RED-then-GREEN — an empty-string `path` is denied, not silently allowed", () => {
    const { shipCwd } = makeShipWorktree("task-malformed-empty-string");
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "" }, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining("(empty path)") });
  });

  test("RED-then-GREEN — a whitespace-only `path` is denied, not silently allowed", () => {
    const { shipCwd } = makeShipWorktree("task-malformed-whitespace");
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "   " }, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining("(blank path)") });
  });

  test("ALLOWED — a non-blank path merely containing whitespace padding is an ordinary candidate, not denied as blank", () => {
    // Guards against the blank check above being too eager: only a string that is
    // EMPTY OR ENTIRELY whitespace (`.trim() === ""`) is treated as blank. A path with
    // real, non-whitespace content is unaffected, even with leading/trailing padding.
    const { shipCwd } = makeShipWorktree("task-whitespace-padding-ok");
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "  inside.txt" }, shipCwd);
    expect(result).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------------------
// Harness-adjudicated writable schemes (issue #297 attempt 3): `local://` and unscoped
// `conflict://<id>`/`conflict://*` are ALLOWED, not denied, on the ground that OMP's own
// `write` tool resolves and revalidates both against a real on-disk file before ever
// touching it (see `../orc-seat.ts`'s header for the full harness-contract citation: an
// independent verify seat, ledger `task-m5-005-sensor` seq 26 REJECT finding 1,
// reproduced live that attempt 2 denied `conflict://<id>` -- OMP's own supported
// merge-conflict-resolution write -- identically to a genuine escape). Each RED-then-
// GREEN pair below FAILS against attempt 2 (`git show 6d44ff4:.omp/extensions/orc-seat.ts`
// -- the just-rejected delivery this attempt corrects) and PASSES against this delivery
// -- see this card's PR body for both raw swap outputs.
// ---------------------------------------------------------------------------------------

describe("worktree fence: harness-adjudicated writable schemes (issue #297 attempt 3) are ALLOWED, not denied", () => {
  function makeShipWorktree(branch: string): { shipCwd: string } {
    const tmpRoot = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "orc-seat-adjudicated-")));
    const shipCwd = path.join(tmpRoot, "repo", ".worktrees", branch);
    fs.mkdirSync(shipCwd, { recursive: true });
    return { shipCwd };
  }

  test("RED-then-GREEN — a write targeting a writable `conflict://<id>` is ALLOWED, not denied as an unresolvable scheme", () => {
    const { shipCwd } = makeShipWorktree("task-conflict-id");
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "conflict://17" }, shipCwd);
    expect(result).toBeUndefined();
    expect(extractUnresolvableTargets("write", { path: "conflict://17" })).toEqual([]);
    expect(extractCandidatePaths("write", { path: "conflict://17" })).toEqual([]);
  });

  test("RED-then-GREEN — an edit targeting a writable `conflict://*` hashline is ALLOWED, not denied", () => {
    const { shipCwd } = makeShipWorktree("task-conflict-star");
    const input = { input: "[conflict://*#A1B2]\nPUT 1.=1:\n+x\n" };
    const result = evaluateWorktreeFenceGuard("ship", "edit", input, shipCwd);
    expect(result).toBeUndefined();
  });

  test("ALLOWED — a scoped, read-only `conflict://<id>/<scope>` target still denies as unresolvable (never a legitimate write target)", () => {
    // Per `omp://tools/write.md`'s own "Merge-conflict resolution" section, the scoped
    // form is read-only: it can never legitimately be a write target, so no
    // adjudication ground applies to it and it stays denied like any other scheme this
    // guard cannot derive to a local path.
    const { shipCwd } = makeShipWorktree("task-conflict-scoped");
    const target = "conflict://17/ours";
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: target }, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining(target) });
  });

  test("RED-then-GREEN — a write targeting `local://...` is ALLOWED, not denied as an unresolvable scheme (deliberate change from attempt 2)", () => {
    // Attempt 2 denied EVERY `scheme://...`-shaped string, `local://` included. This is
    // the one deliberate behaviour change this delivery makes: `local://` moves from
    // attempt 2's blanket DENY to ALLOW-by-adjudication, on the same harness-contract
    // ground as `conflict://` above (see `../orc-seat.ts`'s header).
    const { shipCwd } = makeShipWorktree("task-local");
    const result = evaluateWorktreeFenceGuard("ship", "write", { path: "local://plan.md" }, shipCwd);
    expect(result).toBeUndefined();
  });

  test("DENIED — an edit mixing an adjudicated candidate with a genuinely unresolvable one still denies on the unresolvable one", () => {
    // Soundness check on the guard clause itself: `unresolvable.length === 0 && adjudicated`.
    // A multi-file edit naming both a writable `conflict://<id>` hashline and an
    // `ssh://` one must not let the adjudicated candidate paper over the genuine escape.
    const { shipCwd } = makeShipWorktree("task-mixed");
    const input = {
      input: "[conflict://17#A1B2]\nPUT 1.=1:\n+x\n[ssh://host/x#C3D4]\nPUT 1.=1:\n+y\n",
    };
    const result = evaluateWorktreeFenceGuard("ship", "edit", input, shipCwd);
    expect(result).toEqual({ block: true, reason: expect.stringContaining("ssh://host/x") });
  });
});
