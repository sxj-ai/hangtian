# Workspace layout (HPC)

This repository is developed on the HPC in `~/hangtian_material_pipeline` and synchronized to
GitHub (`sxj-ai/hangtian`) with `git push`. Edit on the HPC; pull elsewhere.

## Do not move or rename (absolute paths are hard-coded)

| Path | Used by |
|---|---|
| `~/hangtian_material_pipeline` | recorded in runs, private inputs, handoff manifests |
| `~/llm_datasets/XJTU-SPS` | the dataset; never committed to git (see `DATASET.md`) |
| `~/xjtu_material_analysis_20261008_run01/catalog.json` | `scripts/prepare_hundred_materials.py`, docs |
| `~/space_telemetry_agent` (Pi runtime in `node_modules`) | `scripts/run_qwen_pi_job.py`, `scripts/run_deepseek_pi_job.py` |
| `~/anaconda3` | Python environment |

## Git-ignored directories (not in GitHub)

`private/`, `runs/`, `handoff/`, `.research_loop/`, `*.zip`, `*.private.*`. Never commit these.

## runs/

`runs/` is a provenance chain; later runs record paths of earlier ones, so do not move them.

- Task chain: `expansion_flash_001..007` -> `expansion_flash_final_001` -> `autonomy_revision_001..003`
  -> `autonomous_tasks_final_001` (historical 15-task batch; current scope in `CURRENT_STATUS.md`);
  `autonomous_tasks_100_001` -> `autonomous_tasks_100_final_001`.
- Pi / agent evaluation: `pi_qwen35_*`, `pi_deepseek_flash_budget80_001`, `pilot_001`, `pilot_offline_001`.
- Audits: `case_capacity_audit_002`, `case_curation_handoff_checks_001`.
- `runs/_archive_unreferenced/`: 18 offline smoke / check outputs that nothing references.

## handoff/

`handoff/case_curation_handoff_001/` is a frozen snapshot: its manifest pins `code_snapshot/` by hash.
Do not edit it; make a new handoff instead.

## Home directory

Research reports from 2026-09-30 are in `~/hangtian_research/`. One-off scripts/logs are in
`~/archive/` (see its README; `restore.sh` reverts the move).
