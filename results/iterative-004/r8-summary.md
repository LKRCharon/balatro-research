# TRAIN iteration comparison

| Iteration | Complete | Wins | Actions | Mean terminal ante | Exact checks | Mismatches | Uncertain |
|---|---:|---:|---:|---:|---:|---:|---:|
| r8 | 13/13 | 0 | 1124 | 3.692 | 297 | 1 | 56 |

Per-seed entries: outcome / terminal ante / actions.

| TRAIN ID | r8 |
|---|---|
| 32 | loss / 5 / 128 |
| 33 | loss / 5 / 104 |
| 34 | loss / 3 / 70 |
| 36 | loss / 3 / 68 |
| 37 | loss / 4 / 89 |
| 38 | loss / 1 / 23 |
| 40 | loss / 5 / 122 |
| 41 | loss / 4 / 92 |
| 42 | loss / 4 / 101 |
| 43 | loss / 4 / 98 |
| 44 | loss / 4 / 81 |
| 45 | loss / 4 / 105 |
| 46 | loss / 2 / 43 |

- Repeated TRAIN data, not independent win-rate evidence.
- Cash averages are action-snapshot weighted, not equal-round causal measures.
- Scorer matches cover only observed chosen actions; uncertain cases excluded.
- Aggregates complement an integrity audit; they do not themselves prove no-save/load.
