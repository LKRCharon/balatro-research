# TRAIN iteration comparison

| Iteration | Complete | Wins | Actions | Mean terminal ante | Exact checks | Mismatches | Uncertain |
|---|---:|---:|---:|---:|---:|---:|---:|
| r6 | 13/13 | 0 | 1006 | 3.615 | 283 | 0 | 40 |

Per-seed entries: outcome / terminal ante / actions.

| TRAIN ID | r6 |
|---|---|
| 32 | loss / 4 / 107 |
| 33 | loss / 5 / 112 |
| 34 | loss / 5 / 108 |
| 36 | loss / 5 / 118 |
| 37 | loss / 1 / 8 |
| 38 | loss / 1 / 23 |
| 40 | loss / 3 / 59 |
| 41 | loss / 5 / 107 |
| 42 | loss / 5 / 101 |
| 43 | loss / 1 / 14 |
| 44 | loss / 5 / 98 |
| 45 | loss / 4 / 91 |
| 46 | loss / 3 / 60 |

- Repeated TRAIN data, not independent win-rate evidence.
- Cash averages are action-snapshot weighted, not equal-round causal measures.
- Scorer matches cover only observed chosen actions; uncertain cases excluded.
- Aggregates complement an integrity audit; they do not themselves prove no-save/load.
