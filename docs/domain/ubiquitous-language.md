---
id: DOMAIN-LANGUAGE
type: glossary
status: current
authority: normative
description: Canonical product vocabulary and non-equivalences.
---

# Ubiquitous language

| Term | Canonical meaning |
|---|---|
| `DeliveryRun` | One orchestration attempt to drive an intent to a verified terminal outcome. |
| `Intent` | The operator's requested outcome. |
| `Work` | One logical deliverable unit in the authoritative work topology. |
| `Execution` | One delegated work-producing run for one Work item. |
| `Candidate` | The exact result subject eligible for assurance. |
| `AssuranceRun` | One evaluation of one exact Candidate. |
| `Evidence` | Candidate-bound proof or finding produced by assurance. |
| `Decision` | An attributable orchestration choice based on observed facts. |
| `Fact` | An immutable canonical observation about what happened. |
| `Effect` | A requested mutation delegated to a port/adapter. |
| `Capability` | A semantic guarantee an adapter declares it can provide. |
| `Provider` | External system behind an adapter. |

## Required non-equivalences

```text
Execution != Work
Execution settled != Work accepted
Candidate != Execution
Evidence != Assurance verdict
Observed != Handled
Handled != Accepted
Retry != Replan
Provider ID != Domain ID
Provider state != canonical state
```
