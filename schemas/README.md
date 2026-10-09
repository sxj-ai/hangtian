# Versioned JSON contracts

The v0.2 `material-batch` path adds `material_query`, `material_tasks`, `material_review`, `solver_step`, `pilot_answer`, `answer_review`, `material_config`, and `material_batch`. The private recipe is a trusted, researcher-authored input, not a model-generated executable specification. See `docs/material_pipeline.md` for input/output separation and resume behavior.

The material-engine-0.3 extension supports named recipe regions, above/below sustained thresholds, scalar quality metrics, acquisition-order zero runs, API-authored interpretation statements, and assistant review mode. Model settings optionally configure thinking/effort. Assistant reviews bind proposal/material/public hashes; their per-task reviews use material_review. Aggregate tasks.json uses a 0.3 envelope around the public task exports; it is not the private material_tasks proposal schema. See docs/batch_prompting.md for the actual batch path and its guided-task limits.

`src/hangtian/contracts.py` is the single source for the implemented contracts. Export using:

```bash
python -m hangtian.cli schemas --out schemas
```

`manifest`, `config`, `case`, `tasks`, `critique`, and `query` are validated by runtime code. Tests compare each exported JSON document to its runtime schema. Closed objects reject additional keys; source and fact cross-references are checked separately.

Candidate/fact-package structures are currently constructed by trusted Python code, not accepted as arbitrary external imports. Their field definitions are documented in Method. A production import API and a trajectory schema remain future work; this directory does not imply they are implemented.


Autonomous investigation contracts: autonomous_tasks, autonomous_query, autonomous_answer, autonomous_step. Public exports omit reference queries; private outcome review is required beyond replay integrity.
