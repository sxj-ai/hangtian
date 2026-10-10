# Current project status - 2026-10-10

The project studies evidence-grounded telemetry investigation. It remains a research prototype; task counts, valid submissions, verified numerical observations, and correct answers are separate measures.

## Current scope

- Pipeline quality is under discussion. The latest curation workflow uses the current assistant directly for case discovery, evidence organization, numerical verification, deduplication, and explicitly labelled same-assistant self-review.
- The handoff records 36 candidate leads and zero newly accepted cases. This synchronization starts no case library, question generation, or solver run.
- Do not invoke subagents or model APIs for the current curation workflow. Historical API/subagent provenance is preserved.
- See [direct case workflow](docs/case_curation/DIRECT_CASE_WORKFLOW.md) and [curation documentation](docs/case_curation/README.md). Earlier multi-agent dispatch instructions are retired.
- The 15 historical tasks require task-level quality review; solver success or failure alone does not establish task quality. Reviewing, revising, merging, or retiring tasks and validating a small representative batch before expansion remain proposed work, not completed validation.

## Historical tasks and evaluations

- The revised T01-T15 batch is retained in `runs/autonomous_tasks_final_001/`. It exposes neutral record catalogs and free-window tools rather than reference query lists.
- `runs/autonomous_tasks_100_final_001/` contains the original 15 tasks plus 85 additions. The additions have no recorded solver trajectories. These are related task instances, not 100 independent experiments or verified correct training examples.
- Qwen job 165694 attempted 15 tasks and submitted 14 reports. Review found four core-goal results needing corrections, seven partial results, three failures, and one incomplete task.
- DeepSeek job 165942 submitted all 15 reports. Review found one pass (T15), six core-goal results needing corrections, six partial results, and two failures. These are answer-review outcomes, not task-quality ratings.
- Numerical observation checks passed, but do not establish semantic correctness. Model, execution protocol, and context accounting differed between runs.
- See [Pi execution and review](docs/pi_evaluation.md), [autonomous task design](docs/autonomous_tasks.md), and [hundred-task history](docs/hundred_tasks.md).

## Repository and data boundary

The GitHub repository contains code, prompts, schemas, configuration examples, and documentation. The approximately 5 GB XJTU-SPS dataset stays on the HPC at `~/llm_datasets/XJTU-SPS`; it is not included in the current repository tree. `DATASET_MANIFEST.json` is a metadata inventory, not the dataset.

Private task references, source mappings, raw trajectories, run outputs, handoff evidence, credentials, and model weights remain outside version control. Paths above describe HPC artifacts, not published artifacts. See [workspace layout](docs/workspace_layout.md) and [dataset notes](DATASET.md).
