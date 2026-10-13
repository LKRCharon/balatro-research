# v14/v15 and capacity v3 development scope

These modules are published as tested development code, separately from the r8 evaluation. r8 used combat v12 and growth v13 with capacity v2; exporting v14/v15 does not retroactively change that policy or establish a result for a later run.

Capacity v3 models four held combat Tarots (Empress, Hierophant, Justice, Chariot). It calls the same held-action target planner on each currently visible hypothetical hand. It does not select targets from the unseen tail. Public deck updates match the complete pre-enhancement token, including permanent bonus; identical duplicate tokens are interchangeable and only selected copies change. Perkeo template reservation remains active.

The v15 shop action buys a supported Tarot to hold without a use flag or target indices. Actual targets are selected only after a real hand is observed. The reference engine endpoint supports ordinary buy-to-inventory, but unit tests are not a new live-engine success result.

Planet projection consumes exactly one visible offer or inventory item and increments each physical active Constellation once. Blueprint/Brainstorm copy the resulting scoring ability and do not add extra persistent increments. Removing the consumed item prevents crediting the same item twice as future growth.

Limitations: glass attrition is not modeled; other held consumables are explicitly unmodeled; hypothetical whole-round outcomes remain approximate, not calibrated win probabilities. Passing local tests does not show that a strategy can win Gold Stake.
