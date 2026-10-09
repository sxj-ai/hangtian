"""Import an explicit assistant review; never auto-approve candidates."""
import argparse
import json
from pathlib import Path
from hangtian.material_review import finalize

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--case-dir', type=Path, required=True)
    p.add_argument('--review', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(finalize(a.case_dir, a.review), ensure_ascii=False))
