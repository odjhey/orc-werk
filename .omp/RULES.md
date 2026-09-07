# orc-werk seat invariants (sticky; mechanics in `.omp/agents/*.md`)

1. No agent records an assurance verdict on its own settlement/candidate.
2. `verify` never pushes, commits, comments, or merges.
3. `ship` edits only inside its own `.worktrees/<branch>`; never merges.
4. Record the outcome before yielding; an unrecorded yield is a failure.
5. One session dispatches a given `orc` run at a time.
