# r8 completed TRAIN audit

All 13 assigned episodes ended naturally in losses: 1,124 gameplay actions, no missing episodes or pending intents. r8 used combat v12, growth v13, capacity v2 and the v4 shard runner. This is repeated TRAIN development, not an independent win-rate or streak result.

- 353 predictions: 297 checkable, **1 mismatch**, 56 uncertain. The 296 matching predictions validate only those observed chosen actions.
- The mismatch on TRAIN 45 transition 84 was 6,696 predicted versus 420 actual. Certificate queued an asynchronous card creation and hand sort after the old observation endpoint returned. Valid numeric indices then selected different card identities. The original mismatch remains recorded; later readiness changes do not repair this historical run.
- Source/engine hash checks passed for each shard; source bytes are archived by SHA256. Four original player-save files remain unchanged. TEST campaigns remain zero.
- Shop diagnostic joins passed for all 13 terminal episodes; see the aggregate for counts. Joined logs do not prove that all strategically useful options were considered.

The Joker ablation aggregate disables one physical Joker in place on 296 engine-matching observed plays. It fixes slots, money and chosen cards. Debuffing also removes edition scoring, so edition counts are included. This does not simulate selling, future economy, card acquisition, changed strategy or causal card strength. Interactions can be counted more than once. Zero immediate contribution is not evidence of a badly designed card.

Published v14/v15 and capacity v3 are separately tested development modules, not the policy evaluated here. Frozen r8 sources and historical results were not modified. Source hashes do not certify every runtime import or operating-system action.
