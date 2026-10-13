# TRAIN iteration comparison

| Iteration | Complete | Wins | Actions | Mean terminal ante | Exact checks | Mismatches | Uncertain |
|---|---:|---:|---:|---:|---:|---:|---:|
| r9 | 13/13 | 0 | 1184 | 3.846 | 305 | 0 | 57 |

Per-seed entries: outcome / terminal ante / actions.

| TRAIN ID | r9 |
|---|---|
| 32 | loss / 4 / 110 |
| 33 | loss / 4 / 94 |
| 34 | loss / 3 / 70 |
| 36 | loss / 3 / 65 |
| 37 | loss / 5 / 102 |
| 38 | loss / 1 / 23 |
| 40 | loss / 5 / 110 |
| 41 | loss / 4 / 93 |
| 42 | loss / 4 / 101 |
| 43 | loss / 4 / 98 |
| 44 | loss / 4 / 95 |
| 45 | loss / 4 / 101 |
| 46 | loss / 5 / 122 |

- Repeated TRAIN data, not independent win-rate evidence.
- Cash averages are action-snapshot weighted, not equal-round causal measures.
- Scorer matches cover only observed chosen actions; uncertain cases excluded.
- Aggregates complement an integrity audit; they do not themselves prove no-save/load.
