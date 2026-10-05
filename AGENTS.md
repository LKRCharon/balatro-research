# Research iteration workflow

The repository owner explicitly requests publication after each completed iteration.

1. Keep changes scoped and protect unrelated local work.
2. Never commit game source, assets, binaries, player profiles, credentials, raw reserved seeds, or private experiment databases. Keep local engine instances and raw data under ignored `work/`.
3. Separate training, validation, and final held-out test seeds. Do not tune from final-test results. Preserve failed, interrupted, and truncated attempts.
4. Freeze policy/configuration and publish preregistered commitments before a formal evaluation starts. Never modify a frozen snapshot in place or silently restart a run.
5. Label scripted policies as scripted. Mechanism coverage is not evidence of exact scoring or an established win rate. A reference-engine CLI is not a complete pure headless reimplementation.
6. Run checks appropriate to the change; review the staged diff for data leakage, copied game content, and inflated claims.
7. Commit and push each completed, tested iteration to the existing remote. Report the commit and results honestly. Do not force push or rewrite published preregistration history.

The public source export is produced by `tools/export_public.py`; changes in the private workspace must be exported deliberately. Formal public policy snapshots must remain byte-identical to their published hashes. Portable changes belong in a new iteration.
