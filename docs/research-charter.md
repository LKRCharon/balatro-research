# Research charter

## Questions

1. Which observable state variables explain Blue Deck / Gold Stake survival?
2. Can a small set of explicit strategy routes achieve robust results without per-action LLM decisions?
3. Which card effects create useful decisions, and which become dominated after accounting for acquisition timing, price, rarity, and synergies?
4. How do expected-score policies differ from policies that limit the probability of an early loss?

## First experiment

Evaluate one frozen scripted candidate on a preregistered validation cohort. The final test partition remains untouched. The first cohort diagnoses failure modes and harness accuracy; it is too small to establish long-streak reliability.

Each run should retain public observations, actions, decision explanations, predicted versus actual score, round/ante, economy trajectory, shop/voucher/pack exposures, and terminal outcome. Private scheduling information remains outside the policy input and outside the public source export.

## Interpretation

For approximately independent runs with success probability p, a prespecified streak of length k has probability p^k. This simple model emphasizes tail risk, but does not imply that blind outcomes within one run are independent, or that a longest streak observed after many attempts has that probability.

Report assigned-job success, game outcomes, technical failures, truncations, uncertainty intervals, and preregistered-order streaks separately. Count every scheduled attempt in the primary denominator. Do not infer a card's causal value from the win rate of runs that bought it; acquisition is selected by the policy and available shops.

Prefer paired training seeds for policy comparisons, grouped seed splits for validation, and explicit ablation experiments for card/route hypotheses. Repeated play of a known seed is development data, not a new independent fresh-seed result. Quantitative balance findings should be distinguished from player experience and fun, which require their own measurements.

## Engineering direction

Keep the original engine as a differential oracle. Extend isolated CLI workers and event logging before replacing core game logic. Extract rules incrementally and test interactions against the reference implementation. Parallelize whole games with independent processes, ports, RNG state, logs, and save identities; do not share global Lua state between workers.
