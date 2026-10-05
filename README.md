# Balatro Risk Lab

Research into Blue Deck / Gold Stake strategy, risk-sensitive decisions, and card balance. The long-term goal is to explain reliable strategies with mathematical models and reproducible experiments, rather than treating an agent's occasional win as evidence of strength.

## Current status

**Hybrid pilot:** assistant-controlled growth plus frozen script combat is implemented and completed one TRAIN game. It lost at Ante 3 Big Blind, 4679/4800; all 18 observed play predictions matched the engine. This validates the handoff/data path, not improved win rate. [Pilot report (中文)](results/hybrid-pilot-001/report.zh-CN.md).

**Combat-only TRAIN comparison:** four reused training seeds, two frozen policies, eight completed losses and no technical errors. Failure Antes were v3 `8/1/6/4` versus v4 `5/2/6/5`; the bounded lookahead searched only 30 of 182 combat decisions. This does not establish improved win rate or optimal combat. [Independent report (中文)](results/combat-compare-001/independent-report.zh-CN.md) · [Results](results/combat-compare-001/summary.json) · [Collected data and limits (中文)](docs/data-coverage.md).

**Repair iteration:** [repair report and training checks (中文)](results/repair-001/report.zh-CN.md). The consumable readiness barrier reproduces the old failure and verifies cash-out/pack/sell-to-buy-use transitions without retries. [route_v3 shop planning](docs/route-v3-acquisition.md) compares immediate lineup/planet gains before speculative purchases. Two training checks ended in losses at Ante 8 and 1, with 269 successful actions and no interface errors; this is not evidence of improved win rate. The formal baseline result below remains unchanged.

**First formal validation completed:** 16 assigned Blue/Gold tasks → **0 wins, 14 actual game losses, 2 technical errors** in 13m16s. All attempts are retained; no failed seed was retried. The untouched final test has zero assigned jobs. [Results and diagnosis (中文)](results/formal-validation-001/report.zh-CN.md) · [Machine-readable results](results/formal-validation-001/summary.json) · [Audit](results/formal-validation-001/audit-result.json).

This is an experimental **scripted policy baseline**, not a demonstrated LLM winstreak. The policy uses public observations and approximate scoring; coverage of every Joker does not imply that every interaction is correct. Blueprint / Brainstorm copying and consumable decisions are modeled, with remaining discrepancies recorded rather than hidden.

The full-game backend still uses a locally installed, isolated reference game engine. A JSON-RPC / JSONL interface avoids per-action command startup; independent workers own independent processes, ports, and saves. This is **not yet a fully renderer-free Balatro implementation**. The small Lua mechanics service extracts functions from the user's own local source at runtime.

## Evaluation protocol

- Blue Deck, Gold Stake; victory requires completing the Ante 8 boss.
- Freeze policy and configuration before evaluation. No mid-run restart or human action selection.
- Keep training, validation, and final test seeds separate. Raw reserved seeds and private registry databases are excluded from this repository.
- Publish commitments before running. Policy receives public observations, not the seed or future draw order.
- Report every assigned run, including technical failures and truncations. Compute streaks in preregistered seed order, never completion order.
- Treat the first small validation cohort as diagnostic evidence, not a precise win-rate estimate or a final held-out test.

Formal preregistration and reports live under `results/` when available. A validation cohort is not automatically a fresh-seed LLM streak benchmark.

First preregistered cohort: [16-game validation protocol](results/formal-validation-001/protocol.json), published before play in commit `6b8c3e1`. [Research charter (中文)](docs/research-charter.md) explains strategy, balance and fun as distinct research questions; [independent audit](docs/evaluation-validity-audit.md) records the protocol's checks and limits.

## Layout and local requirements

`outputs/balatro-lab/` preserves the original research workspace layout: `cli/` contains observation/telemetry tools, `experiments/` contains policies and the seed registry, and `headless/` contains transport and isolation adapters.

Python 3.12+ is recommended. Most harness modules use the standard library. Full-game execution additionally requires a lawful local copy of Balatro and the private CLI adapter expected by `headless/isolation.py`; this public export does **not** include a complete turnkey game backend. Do not download game source or assets from this repository: none are supplied. Pure transport/protocol tests can run without the game.

```sh
python -m unittest discover -s outputs/balatro-lab/headless -p test_transport.py
python -m unittest discover -s outputs/balatro-lab/experiments -p test_protocol.py
```

These 16 tests passed for the initial export; they verify transport and registry behavior, not complete game-rule accuracy. Other tests may require the private engine or local trajectories.

Legacy frozen Python files can contain non-secret local Windows runtime defaults. Override `BALATRO_LAB_PYTHON`, `BALATRO_LAB_REPO`, and `BALATRO_LAB_JUST` for your installation. Never point experiments at your normal player profile. Independent save identities and mute settings must be verified before starting workers.

Run the supported game-free checks from the repository root, each in its own process:

```powershell
python -m unittest discover -s outputs/balatro-lab/experiments -p test_protocol.py -v
python -m unittest discover -s outputs/balatro-lab/experiments -p test_formal_eval.py -v
python -m unittest discover -s outputs/balatro-lab/headless -p test_transport.py -v
python -m unittest discover -s outputs/balatro-lab/headless -p test_environment.py -v
```

GitHub Actions runs these checks on Windows/Python 3.12. They validate the harness, not full-game strategy strength. `.gitattributes` disables line-ending conversion so frozen file hashes survive checkout.

The readiness Lua tests additionally use `lupa==2.8`; CI installs it explicitly. Run `python -m unittest discover -s tools -p test_readiness_patch.py -v` for those checks. The supplied `tools/readiness_v2.lua` and `readiness_v3.lua` are original transport wrappers, not copied game source. Install into a **new, never-launched isolated instance** with `python tools/readiness_patch.py path/to/instance.json` before launching; v3 is the default. Existing game/engine installations are not patched by this command.

## Publication and reproducibility

`tools/export_public.py` refreshes the allowlisted harness export from a private research workspace. It never exports player saves, game binaries/assets/source, raw experiment registries, raw seeds, credentials, or arbitrary result directories. Review the diff and run relevant tests before every iteration is committed and pushed.

Formal `formal_public_route_v2_*` policy snapshots are retained byte-for-byte: unused localized name/description fields were removed before freezing. Their source and exported hashes must match the preregistration. The working `route_v2` metadata export is reduced to factual mechanics, with original and exported hashes recorded separately in `export-manifest.json`; it is not the frozen candidate. Never substitute working-copy hashes for evaluation commitments.

## Research scope

Planned analyses include round-by-round economy, shop rarity exposure, voucher/pack decisions, paired-seed policy comparisons, and tail failure risk. Card purchase win rates are confounded by availability, price, timing, and the state in which a card was selected; they cannot by themselves establish that a card is poorly designed. Balance and fun remain research questions, not conclusions of this initial release.

## Attribution

Balatro is the game created by LocalThunk and published by Playstack. This is an independent research harness, not an official project. The original game and any third-party tools retain their own rights and licenses; this repository grants no rights to them. Reference projects include [azazo1/balatro](https://github.com/azazo1/balatro), [Attol8/balatro-ai](https://github.com/Attol8/balatro-ai), and [BalatroBench](https://github.com/Michael-Andrzejewski/balatro-bench). Their reported results should be checked against their published protocols rather than treated as comparable win rates.
