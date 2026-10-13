# r7 independent audit

All four shards pass strict completed-episode checks and merge to exactly 13 distinct TRAIN IDs: 0 wins, 13 natural losses, no missing or duplicate episodes.

- 1,151 decisions = 1,138 gameplay actions + 13 starts.
- 13 additional transitions return an already terminal prior episode to MENU before the next start; no in-episode reset.
- 351 played-hand predictions: 307 checkable, 0 mismatches, 44 uncertain. No missing play predictions or pending mutations.
- Original four player-save files match the baseline. TEST campaigns remain zero; recorded seeds are TRAIN.
- Protocol-listed source and engine hashes match. Historical manual/formal source checks pass. Source bytes were archived by SHA256 with a separate r7 protocol-to-source index.

The four per-shard artifacts are r7-audit-a.json, r7-audit-b.json, r7-audit-c.json and r7-audit-d.json; r7-audit-integrity.json provides the merge. These artifacts contain aggregate counts and TRAIN IDs, no raw seed values or card-level observations.

This is repeated TRAIN regression, not independent win-rate evidence. Scoring agreement covers chosen observed actions only and excludes uncertain predictions. Source hashes do not by themselves certify all runtime module resolution or all operating-system actions. No candidate source or active r8 episode was modified or inspected during this audit.
