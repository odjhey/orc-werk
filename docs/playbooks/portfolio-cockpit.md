---
id: PLAYBOOK-PORTFOLIO-COCKPIT
type: playbook
status: current
authority: informative
description: Sanctioned cross-project cockpit using bd over one shared, write-only Beads mirror workspace.
---

# Portfolio cockpit

This playbook defines Orc Werk's sanctioned cross-project view. Multiple repositories write delivery projections to one shared Beads board; operators read that board with `bd`'s own CLI. Orc Werk has no cross-project read command and will not gain one.

## Boundary: Orc writes; bd reads

The Beads mirror is **write-only**. Orc projects each delivery's desired state to the configured board, but never reads board state back into delivery policy, canonical state, or an Orc reporting command. This preserves the provider quarantine in `INV-014`: Beads vocabulary and behavior remain in the adapter rather than entering the generic core.

This is also the mechanism/policy split of `P-007`. Mirroring is an adapter effect—a mechanism for projecting state. The board is not an input to policy and cannot decide or alter delivery state. A cockpit reader inside Orc, especially one scanning several journal directories or consuming Beads state, would blur both boundaries. It is deliberately absent.

The pattern graduates the dormant shared-portfolio convention recorded by `M3-HARDEN-THE-LOOP`: one `bd` workspace plus repository-local journals selected by `ORC_JOURNAL_DIR`. It does not graduate the dormant multi-repo registry/profile feature and does not create a new Orc command.

## Shared-workspace convention

Choose one Beads workspace for the portfolio, for example `~/orc-portfolio`. Every participating repository configures that **same** `mirror.workspace`, while assigning its own distinct `mirror.project` in `.orc/profile.json`:

```json
{
  "mirror": {
    "adapter": "beads",
    "workspace": "/home/alice/orc-portfolio",
    "project": "payments"
  }
}
```

A second repository uses the same workspace and a different project value, for example `"project": "catalog"`. Use stable, unique project names; they become board labels and are the portfolio's project keys.

Each repository still owns its own Orc journal. Set `ORC_JOURNAL_DIR` to that repository's local journal directory (normally its `.orc` directory), or rely on the `./.orc` default while running from the repository root:

```bash
cd ~/src/payments
export ORC_JOURNAL_DIR="$PWD/.orc"
orc dispatch "deliver payment change"
```

Sharing `mirror.workspace` shares only the projection board. It does not combine, relocate, or authorize cross-reading of journals. Both `project:NAME` and `run:RUNID` labels are emitted by Orc's mirror on `bd create`; the former comes from `mirror.project`, and the latter identifies the delivery run.

## Read-back recipes

Run these commands in the shared Beads workspace. The output is adapter-native board data, not canonical Orc journal state:

```bash
cd ~/orc-portfolio
```

One project's complete slice:

```bash
bd list --label project:payments --status all
```

All projects on the shared board:

```bash
bd list --status all
```

One delivery group, using its `run:RUNID` label:

```bash
bd list --label run:RUNID --status all
```

For a per-project view grouped by delivery, first list the project slice, then run the `run:RUNID` command for each run label represented in that slice. The `project:` label answers which repository owns the projection; the `run:` label groups all mirrored work for one delivery.

These are the read surface. Do not replace them with an Orc command over the board or with an Orc reader that searches many journal directories. For authoritative details about one delivery, enter its owning repository and use its normal single-journal Orc commands.

## Related

- `INV-014`
- `P-007`
- `ADAPTER-BEADS-MAPPING`
- `PRODUCT-ADOPTION`
- `CLI-REFERENCE`
- `M3-HARDEN-THE-LOOP`
- `M4-COCKPIT-AND-CLARITY`
