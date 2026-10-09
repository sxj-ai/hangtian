"""One allocated GPU job owns local model service and all isolated Pi runs."""
import hashlib
import argparse
import json
import os
import re
from pathlib import Path
import signal
import socket
import shutil
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
NODE = '/home/xjshang/.local/share/pi-sdk-runtime/node-v22.23.3-linux-x64/bin/node'
PI = '/home/xjshang/space_telemetry_agent/node_modules/@earendil-works/pi-coding-agent/dist/index.js'
PYTHON = '/home/xjshang/anaconda3/bin/python'
VLLM_PYTHON = '/home/xjshang/anaconda3/envs/hwkb/bin/python'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reporting-baseline', type=Path)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/pi_qwen35_27b.example.json')
    parser.add_argument('--run-family')
    parser.add_argument('--seed', type=int)
    args = parser.parse_args()
    baseline = args.reporting_baseline
    if baseline is not None:
        base_status = json.loads((baseline / 'status.json').read_text())
        if base_status['status'] != 'runs_finished_pending_semantic_review' or len(base_status['tasks']) != 15:
            raise RuntimeError('Reporting diagnostic requires a completed 15-task baseline')
    job_id = os.environ.get('SLURM_JOB_ID')
    if not job_id:
        raise RuntimeError('Run inside the authorized Slurm allocation')
    family = args.run_family or ('pi_qwen35_reporting_001' if baseline else 'pi_qwen35_nothinking_001')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', family):
        raise ValueError('Invalid run family')
    out = ROOT / 'runs' / family / ('job_' + job_id)
    out.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.config.read_text())
    if args.seed is not None:
        config['seed'] = args.seed
    concurrency = config.get('concurrency', 4)
    if baseline:
        config.update(max_api_calls_per_task=1, reserved_report_requests=0,
                      max_tool_calls_per_task=1, max_run_seconds=900)
    # Select a currently free loopback port; the service is never externally bound.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    config['base_url'] = f'http://127.0.0.1:{port}/v1'
    (out / 'model_config.json').write_text(json.dumps(config, indent=2))
    status = {'job_id': job_id, 'host': socket.gethostname(), 'status': 'starting',
              'started_at_unix': time.time(), 'tasks': [], 'controls': []}
    if baseline:
        status.update(condition='prompted reporting diagnostic, excluded from baseline completion',
                      baseline=str(baseline), reports=[])
    snapshot = out / 'code_snapshot.private'
    hashes = {}
    for relative in ['scripts/run_qwen_pi_job.py', 'scripts/pi_pilot.mjs', 'scripts/pi_budget.mjs',
                     'scripts/run_qwen_pi_budget80.sbatch',
                     'src/hangtian/pi_bridge.py', 'src/hangtian/autonomous.py',
                     'src/hangtian/contracts.py', 'prompts/pi_investigator.md',
                     'prompts/pi_reporting_probe.md', str(args.config.resolve().relative_to(ROOT))]:
        source = ROOT / relative
        if source.exists():
            dest = snapshot / relative; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            hashes[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
    (snapshot / 'sha256.json').write_text(json.dumps(hashes, indent=2))

    def save():
        (out / 'status.json').write_text(json.dumps(status, indent=2))

    def interrupted(signum, frame):
        raise InterruptedError(f'Job signal {signum}')

    signal.signal(signal.SIGTERM, interrupted)
    service = None
    exit_code = 1
    try:
        save()
        env = os.environ.copy()
        for name in ('DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY'):
            env.pop(name, None)
        env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                   VLLM_NO_USAGE_STATS='1', DO_NOT_TRACK='1', TOKENIZERS_PARALLELISM='false',
                   PYTHONNOUSERSITE='1', OMP_NUM_THREADS='8', VLLM_WORKER_MULTIPROC_METHOD='spawn',
                   VLLM_USE_FLASHINFER_SAMPLER='0')
        env.pop('PYTHONPATH', None)
        env['PATH'] = str(Path(VLLM_PYTHON).parent) + os.pathsep + env.get('PATH', '')
        gpu = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=30)
        (out / 'gpu.txt').write_text(gpu.stdout + gpu.stderr)
        if gpu.returncode:
            raise RuntimeError('Allocated GPU unavailable')
        files = ['config.json', 'tokenizer_config.json', 'chat_template.jinja', 'model.safetensors.index.json']
        hashes = {name: hashlib.sha256((Path(config['model_path']) / name).read_bytes()).hexdigest()
                  for name in files if (Path(config['model_path']) / name).exists()}
        (out / 'model_identity.json').write_text(json.dumps({'path': config['model_path'],
            'configuration_hashes': hashes, 'weights_modified': False}, indent=2))
        command = [VLLM_PYTHON, '-m', 'vllm.entrypoints.openai.api_server',
            '--model', config['model_path'], '--served-model-name', config['model'],
            '--host', '127.0.0.1', '--port', str(port), '--tensor-parallel-size', '1',
            '--dtype', 'bfloat16', '--max-model-len', str(config['context_window']),
            '--max-num-seqs', str(concurrency), '--max-num-batched-tokens', '4096',
            '--gpu-memory-utilization', '0.9',
            '--compilation-config', '{"mode":0,"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[1,2,4]}',
            '--limit-mm-per-prompt', '{"image":0,"video":0}',
            '--enable-auto-tool-choice', '--tool-call-parser', 'qwen3_coder',
            '--reasoning-parser', 'qwen3', '--generation-config', 'vllm']
        (out / 'service_command.json').write_text(json.dumps(command, indent=2))
        with (out / 'service.log').open('w') as log:
            service = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            status['status'] = 'loading_model'; save()
            deadline = time.monotonic() + 1500
            while True:
                if service.poll() is not None:
                    raise RuntimeError(f'Model service exited: {service.returncode}')
                try:
                    with urllib.request.urlopen(config['base_url'] + '/models', timeout=3) as response:
                        catalog = json.load(response)
                    if config['model'] not in [m['id'] for m in catalog['data']]:
                        raise RuntimeError('Served model identity differs')
                    (out / 'served_models.json').write_text(json.dumps(catalog, indent=2))
                    break
                except (OSError, ValueError):
                    if time.monotonic() > deadline:
                        raise TimeoutError('Model startup exceeded 25 minutes')
                    time.sleep(3)
            tasks = json.loads((ROOT / 'runs/autonomous_tasks_final_001/tasks.json').read_text())['tasks']
            if [t['task_id'] for t in tasks] != [f'T{i:02d}' for i in range(1, 16)]:
                raise RuntimeError('Expected exactly the approved 15 tasks')
            def run_one(tid, mode):
                    if service.poll() is not None:
                        raise RuntimeError('Model service stopped during experiment')
                    destination = out / (tid + '_' + mode)
                    cmd = [NODE, str(ROOT / 'scripts/pi_pilot.mjs'), '--config', str(out / 'model_config.json'),
                        '--pi-entry', PI, '--python', PYTHON, '--batch', str(ROOT / 'runs/autonomous_tasks_final_001'),
                        '--task', tid, '--mode', mode, '--out', str(destination), '--allow-local-inference']
                    if mode == 'report_only':
                        cmd += ['--prior-trajectory', str(baseline / (tid + '_tools') / 'trajectory.json')]
                    started = time.time()
                    with (out / (tid + '_' + mode + '.log')).open('w') as run_log:
                        try:
                            result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=run_log,
                                stderr=subprocess.STDOUT, timeout=config['max_run_seconds'] + 120)
                            code = result.returncode
                        except subprocess.TimeoutExpired:
                            code = 124
                    record = {'task_id': tid, 'mode': mode, 'exit_code': code, 'elapsed_seconds': time.time() - started}
                    meta = destination / 'run_metadata.json'
                    if meta.exists():
                        record['run'] = json.loads(meta.read_text())
                    print(json.dumps({'completed': tid, 'mode': mode, 'exit_code': code}), flush=True)
                    return record
            stages = [('tools', [t['task_id'] for t in tasks])]
            if config.get('run_no_data_controls', True):
                stages.append(('no_data', ['T01', 'T05', 'T12']))
            if baseline:
                unfinished = [t['task_id'] for t in tasks if json.loads(
                    (baseline / (t['task_id'] + '_tools') / 'trajectory.json').read_text())['answer'] is None]
                stages = [('report_only', unfinished)]
            for mode, selected in stages:
                status.update(status='running_agents', current_mode=mode, concurrency=concurrency); save()
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures = [pool.submit(run_one, tid, mode) for tid in selected]
                    for future in as_completed(futures):
                        status[{'tools':'tasks','no_data':'controls','report_only':'reports'}[mode]].append(future.result()); save()
            status['status'] = 'runs_finished_pending_semantic_review'
            exit_code = 0
    except Exception as error:
        status.update(status='failed', error=str(error))
        print(str(error), flush=True)
    finally:
        if service is not None:
            try:
                os.killpg(service.pid, signal.SIGTERM)
                service.wait(timeout=20)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try: os.killpg(service.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                service.wait()
        status['model_service_stopped'] = service is None or service.poll() is not None
        status['finished_at_unix'] = time.time(); save()
        print(json.dumps(status, indent=2), flush=True)
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
