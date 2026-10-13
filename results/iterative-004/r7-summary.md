# TRAIN iteration comparison

| Iteration | Complete | Wins | Actions | Mean terminal ante | Exact checks | Mismatches | Uncertain |
|---|---:|---:|---:|---:|---:|---:|---:|
| r7 | 13/13 | 0 | 1138 | 3.692 | 307 | 0 | 44 |

Per-seed entries: outcome / terminal ante / actions.

| TRAIN ID | r7 |
|---|---|
| 32 | loss / 5 / 123 |
| 33 | loss / 4 / 94 |
| 34 | loss / 4 / 86 |
| 36 | loss / 2 / 39 |
| 37 | loss / 4 / 96 |
| 38 | loss / 1 / 23 |
| 40 | loss / 5 / 122 |
| 41 | loss / 4 / 90 |
| 42 | loss / 4 / 101 |
| 43 | loss / 4 / 111 |
| 44 | loss / 3 / 58 |
| 45 | loss / 4 / 110 |
| 46 | loss / 4 / 85 |

- Repeated TRAIN data, not independent win-rate evidence.
- Cash averages are action-snapshot weighted, not equal-round causal measures.
- Scorer matches cover only observed chosen actions; uncertain cases excluded.
- Aggregates complement an integrity audit; they do not themselves prove no-save/load.
