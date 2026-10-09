# Current project status - 2026-10-08

The benchmark objective is independent agent investigation. Earlier guided tasks do NOT meet that acceptance criterion.

Current reviewed public tasks: runs/autonomous_tasks_final_001/tasks.json
Readable questions: runs/autonomous_tasks_final_001/questions.html
- 15 revised tasks, all authored by deepseek-flash API; immutable task objects verified against API responses.
- Old 3 assistant drafts + 12 API guided tasks retained separately, not approved for autonomous evaluation.
- New solver exports contain neutral data documentation and full selected-record access, without reference query lists, expected verdicts or private event regions.
- Assistant-curated private outcome rubrics permit alternative valid analysis paths. Candidate API grading proposals are not the authoritative rubrics.
- 101 code tests passed locally and on HPC; 126 free-window saved-record calculations matched an independent pandas implementation.
- Reference integrity is not task correctness. Semantic outcome grading still requires review.
- Independent solver API calls: 0. Agent trajectories: 0. Pass rate: unknown.
- Design review permits a bounded autonomous-investigation pilot; difficulty, tool budgets, agent solvability and generalization remain unmeasured.

Operational scripts: scripts/generate_autonomous_batch.py, scripts/assemble_autonomous_versions.py, scripts/verify_autonomous_windows.py, scripts/finalize_autonomous_batch.py.
Shared prompts: prompts/autonomous_generator.md and prompts/autonomous_solver.md.
See docs/autonomous_tasks.md for contracts, limitations and next-step isolated Agent runs. Do not give private references/reviews to solvers, or run the old guided solver and report it as autonomous analysis.
