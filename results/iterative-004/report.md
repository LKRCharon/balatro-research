# TRAIN iteration comparison

| Iteration | Complete | Wins | Actions | Mean terminal ante | Exact checks | Mismatches | Uncertain |
|---|---:|---:|---:|---:|---:|---:|---:|
| r1 | 13/13 | 0 | 1010 | 3.692 | 264 | 0 | 48 |
| r2b | 13/13 | 0 | 797 | 3 | 311 | 0 | 14 |
| r3 | 13/13 | 0 | 915 | 3.154 | 258 | 0 | 58 |

Per-seed entries: outcome / terminal ante / actions.

| TRAIN ID | r1 | r2b | r3 |
|---|---|---|---|
| 32 | loss / 5 / 102 | loss / 1 / 22 | loss / 1 / 25 |
| 33 | loss / 4 / 87 | loss / 4 / 90 | loss / 5 / 103 |
| 34 | loss / 5 / 110 | loss / 3 / 56 | loss / 4 / 91 |
| 36 | loss / 3 / 66 | loss / 3 / 63 | loss / 3 / 67 |
| 37 | loss / 5 / 104 | loss / 5 / 98 | loss / 1 / 13 |
| 38 | loss / 3 / 53 | loss / 2 / 33 | loss / 2 / 35 |
| 40 | loss / 3 / 66 | loss / 3 / 61 | loss / 5 / 121 |
| 41 | loss / 3 / 61 | loss / 5 / 92 | loss / 5 / 118 |
| 42 | loss / 5 / 95 | loss / 4 / 96 | loss / 4 / 101 |
| 43 | loss / 3 / 65 | loss / 2 / 49 | loss / 2 / 50 |
| 44 | loss / 2 / 45 | loss / 2 / 40 | loss / 4 / 74 |
| 45 | loss / 4 / 89 | loss / 4 / 89 | loss / 3 / 74 |
| 46 | loss / 3 / 67 | loss / 1 / 8 | loss / 2 / 43 |

- Repeated TRAIN data, not independent win-rate evidence.
- Cash averages are action-snapshot weighted, not equal-round causal measures.
- Scorer matches cover only observed chosen actions; uncertain cases excluded.
- Aggregates complement an integrity audit; they do not themselves prove no-save/load.
