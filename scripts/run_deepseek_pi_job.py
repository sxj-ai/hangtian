"""Authorized flash-only external inference; CPU Slurm job, 15 fresh Pi sessions."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
NODE='/home/xjshang/.local/share/pi-sdk-runtime/node-v22.23.3-linux-x64/bin/node'
PYTHON='/home/xjshang/anaconda3/bin/python'
PI='/home/xjshang/space_telemetry_agent/node_modules/@earendil-works/pi-coding-agent/dist/index.js'


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--credential-file',type=Path,default=Path('/home/xjshang/.config/hangtian/deepseek_api_key'))
    a=p.parse_args()
    job=os.environ.get('SLURM_JOB_ID')
    if not job: raise RuntimeError('Run inside the authorized CPU allocation')
    config=json.loads((ROOT/'configs/pi_deepseek_flash_budget80.json').read_text())
    if config['model']!='deepseek-flash' or config['thinking']!='disabled':raise RuntimeError('Unexpected provider policy')
    if a.credential_file.stat().st_mode & 0o077:raise RuntimeError('Credential file must be owner-only')
    key=a.credential_file.read_text().strip()
    if not key:raise RuntimeError('Empty API credential')
    out=ROOT/'runs/pi_deepseek_flash_budget80_001'/('job_'+job)
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    (out/'model_config.json').write_text(json.dumps(config,indent=2))
    env=os.environ.copy()
    for name in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','NODE_OPTIONS']:
        env.pop(name,None)
    env.update(DEEPSEEK_API_KEY=key,PYTHONPATH=str(ROOT/'src'),PYTHONUNBUFFERED='1',DO_NOT_TRACK='1')
    status={'job_id':job,'host':socket.gethostname(),'status':'starting','tasks':[],
      'started_at_unix':time.time(),'model':config['model'],'thinking':'disabled','gpu_requested':False,
      'condition':'same15 approved tasks; protocol-v2 fixes prior request-boundary/error propagation defects; not a strict model-only ablation'}
    def save():
        tmp=out/'status.json.tmp';tmp.write_text(json.dumps(status,indent=2));tmp.replace(out/'status.json')
    snapshot=out/'code_snapshot.private';hashes={}
    for relative in ['scripts/run_deepseek_pi_job.py','scripts/run_deepseek_pi.sbatch','scripts/pi_pilot.mjs',
      'scripts/pi_budget.mjs','scripts/pi_request_policy.mjs','src/hangtian/pi_bridge.py','src/hangtian/autonomous.py',
      'src/hangtian/contracts.py','prompts/pi_investigator.md','configs/pi_deepseek_flash_budget80.json']:
        source=ROOT/relative;dest=snapshot/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest);hashes[relative]=hashlib.sha256(source.read_bytes()).hexdigest()
    (snapshot/'sha256.json').write_text(json.dumps(hashes,indent=2))
    task_ids=[t['task_id'] for t in json.loads((ROOT/'runs/autonomous_tasks_final_001/tasks.json').read_text())['tasks']]
    if task_ids!=[f'T{i:02d}' for i in range(1,16)]:raise RuntimeError('Expected exactly the approved15 tasks')
    def run_one(tid):
        cmd=[NODE,str(ROOT/'scripts/pi_pilot.mjs'),'--config',str(out/'model_config.json'),
          '--pi-entry',PI,'--python',PYTHON,'--batch',str(ROOT/'runs/autonomous_tasks_final_001'),
          '--task',tid,'--mode','tools','--out',str(out/(tid+'_tools')),'--allow-remote','--allow-data-egress']
        started=time.time()
        with (out/(tid+'_tools.log')).open('w') as log:
            proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:code=proc.wait(timeout=config['max_run_seconds']+120)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL);proc.wait();code=124
        result={'task_id':tid,'mode':'tools','exit_code':code,'elapsed_seconds':time.time()-started}
        meta=out/(tid+'_tools')/'run_metadata.json'
        if meta.exists():result['run']=json.loads(meta.read_text())
        return result
    try:
        status['status']='running_agents';save()
        # An automatic first-session gate prevents fanning an invalid key or API
        # configuration across the whole batch. This still counts as taskT01.
        first=run_one(task_ids[0]);status['tasks'].append(first);save()
        if first['exit_code'] or first.get('run',{}).get('api_requests',0)==0:
            raise RuntimeError('First session failed at the provider/runner boundary; remaining tasks were not charged')
        with ThreadPoolExecutor(max_workers=config['concurrency']) as pool:
            pending=[pool.submit(run_one,tid) for tid in task_ids[1:]]
            for f in as_completed(pending):status['tasks'].append(f.result());save()
        status['status']='runs_finished_pending_semantic_review';save()
        # CPU-only recomputation after the whole batch; does not grade prose.
        check=subprocess.run([PYTHON,'scripts/verify_pi_observations.py','--batch','runs/autonomous_tasks_final_001',
          '--run',str(out)],cwd=ROOT,env={k:v for k,v in env.items() if k!='DEEPSEEK_API_KEY'},
          capture_output=True,text=True,timeout=900)
        (out/'verification.log').write_text(check.stdout+check.stderr)
        status['numerical_verification_exit_code']=check.returncode
    except Exception as error:
        status.update(status='failed',error=str(error).replace(key,'[REDACTED]'))
    finally:
        status['finished_at_unix']=time.time();save()
    return 0 if status['status']=='runs_finished_pending_semantic_review' else 1


if __name__=='__main__':raise SystemExit(main())
