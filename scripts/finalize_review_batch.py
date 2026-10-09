"""Batch import hash-bound reviews after independent raw-material verification."""
import argparse
import json
from pathlib import Path
from hangtian.material_review import finalize
from hangtian.data import write_json

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True)
    a=p.parse_args();results=[]
    for case in sorted(a.run_dir.iterdir()):
        if (case/'private/generated_candidate.json').exists():
            results.append(finalize(case,case/'private/assistant_review.submitted.json'))
    if not results:raise SystemExit('No generated cases')
    write_json(a.run_dir/'reviewed_batch_summary.json',{'cases':results,'stage':'assistant_review_and_reference_validation'})
    print(json.dumps(results,ensure_ascii=False))
