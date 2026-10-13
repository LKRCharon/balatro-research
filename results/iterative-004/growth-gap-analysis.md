# Growth and execution gaps after r6

r6 completed 13 TRAIN episodes with zero wins. This is a development regression,
not independent win-rate evidence. Verified score reconstruction on executed
deterministic actions does not verify the forward strategy model.

## Observed resource trajectory

Each observed blind receives equal weight. Later antes contain survivors only.

| Ante | Blinds observed | Clears | Mean entry cash | Mean Jokers | Mean plays | Mean discards |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 36 | 33 | 4.97 | 0.83 | 2.25 | 1.42 |
| 2 | 30 | 30 | 6.40 | 3.00 | 1.63 | 0.73 |
| 3 | 28 | 26 | 5.79 | 4.07 | 2.29 | 0.64 |
| 4 | 24 | 22 | 6.33 | 4.71 | 3.33 | 1.17 |
| 5 | 10 | 4 | 5.90 | 4.60 | 4.90 | 1.20 |

Slots fill, but scoring demand consumes almost all hands by Ante 5. Low cash
also limits later purchases. This identifies a growth/resource-management gap;
it does not prove which individual purchase would have prevented a loss.

The separate solver audit found no remaining last-hand redraw violation in the
12-terminal snapshot. However, 303 of 419 solver records ended with the v9
immediate-score override; saved rollout diagnostics must not be counted as
executed planning. The cautious growth branch did not become a final action.

## Missing future value

The previous projected-growth function covered only six growers. A Constellation
or Hologram starting at x1 could receive zero projected gain even with public
trigger opportunities. That is a model-coverage defect, not evidence of weakness.

New development candidates separately address:

- Copier ordering during shop capacity estimation and after blind-entry effects.
- Public resource losses from perishing passive Jokers and Turtle Bean decay.
- Repeated retained-core growth, including the public refill count cost to Blue Joker.
- Same-calculation shop diagnostics with explicit rejected-candidate reasons.
- Limited opportunities for Constellation, Hologram, Vampire, Madness, Yorick and Wee.

## Mathematical interpretation

For score S=C*M*X, a chips increment dC has fractional effect dC/C; a flat
multiplier increment dM has effect dM/M. Compare these marginal gains at the
actual scoring stage, then include repetitions, card order and Boss constraints.
A high nominal multiplier is not automatically more useful than missing chips.

Future value also needs an execution plan: a trigger, its resource cost, a
survival window and an alternative use of the slot/cash. Crediting growth
without scheduling its triggers overvalues the card; omitting known available
triggers undervalues it. The new opportunity projections expose this distinction
but do not solve the complete stochastic control problem.

Four-world shop estimates and bounded combat rollouts remain approximate.
Unsupported Boss estimates receive an explicitly heuristic discount. None of
these quantities is a calibrated survival probability or a safety certificate.

## Data interpretation

The analysis tool deduplicates shop offers by game-assigned card id, counts only
completed purchase transitions, and retains the final winning Boss even when
there is no cash-out action. Idless observations are reported as omissions.
Exposure and purchase frequencies describe this policy's decisions; they cannot
establish causal card balance. That requires controlled comparisons and later
held-out validation after the policy is frozen.
