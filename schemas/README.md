# Versioned JSON contracts

`src/hangtian/contracts.py` is the single source for the implemented contracts. Export using:

```bash
python -m hangtian.cli schemas --out schemas
```

`manifest`, `config`, `case`, `tasks`, `critique`, and `query` are validated by runtime code. Tests compare each exported JSON document to its runtime schema. Closed objects reject additional keys; source and fact cross-references are checked separately.

Candidate/fact-package structures are currently constructed by trusted Python code, not accepted as arbitrary external imports. Their field definitions are documented in Method. A production import API and a trajectory schema remain future work; this directory does not imply they are implemented.
