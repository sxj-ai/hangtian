"""HPC loopback-only Qwen authoring; immutable call logs and explicit review gate."""
import argparse
import json
import os
import re
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from hangtian.autonomous import public_environment, export_tasks
from hangtian.contracts import schema
from hangtian.data import digest, file_hash, write_json
from hangtian.materials import read_json

ROOT = Path(__file__).resolve().parents[1]
VLLM = '/home/xjshang/anaconda3/envs/hwkb/bin/python'


def payload_for(material, environment, targets):
    slots=[s for s in material['task_slots'] if s['slot_id'] in targets]
    needed={i for s in slots for i in s['measurement_ids']}
    return {'material_id':material['material_id'], 'public_environment':environment,
            'private_limitations':material['limitations'],
            'private_slots':[{'slot_id':s['slot_id'],'target_task_id':targets[s['slot_id']],
                'focus':s['focus'],'reference_fact_ids':s['measurement_ids']} for s in slots],
            'private_verified_anchors':[{'id':f['fact_id'],'query':f['query'],
                'value':f['result']['value'],'unit':f['unit'],'source_rows':f['result']['source_rows']}
                for f in material['facts'] if f['fact_id'] in needed],
            'required_output_schema':schema('autonomous_tasks')}


def validate_loopback(url):
    from urllib.parse import urlparse
    p=urlparse(url)
    if p.scheme!='http' or p.hostname!='127.0.0.1' or p.username or p.password:
        raise ValueError('Only this-job loopback inference is permitted')


def public_style_errors(tasks):
    """Reject common scaffolding; passing this is not semantic approval."""
    errors=[]
    for t in tasks:
        text=t['title']+' '+t['prompt']
        if len(t['prompt'])>90 or len(t['title'])>30:
            errors.append(t['task_id']+': public text exceeds concise interface limits')
        if re.search(r'\b[UIP]_[A-Za-z0-9_]+|load[123]_phase|需|结合|重点|分别|并说明|请说明|避免|而非|不得|电阻|分流器|功率平衡|各自.*阶段|相同.*阶段|对应.*阶段',text,re.I):
            errors.append(t['task_id']+': channel checklist, supporting method, or unverified term in public text')
        if len([s for s in re.split('[。！？；;]',t['prompt']) if s.strip()])!=1:
            errors.append(t['task_id']+': expected one primary-goal sentence')
    return errors


def main(out, selected, feedback_file, task_ids=None, runtime_config=None):
    job=os.environ.get('SLURM_JOB_ID')
    if not job: raise RuntimeError('Use an allocated GPU job')
    config=read_json(ROOT/'configs/pi_qwen35_27b.example.json')
    runtime=read_json(runtime_config) if runtime_config else {'backend':'vllm','python':VLLM}
    if runtime['backend'] not in {'vllm','transformers'}:raise ValueError('Unsupported runtime')
    runtime_python=runtime['python']
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    url=f'http://127.0.0.1:{port}/v1';validate_loopback(url)
    run=out/'generation_jobs'/job;run.mkdir(parents=True,exist_ok=False)
    prompt='\n\n'.join((ROOT/'prompts'/p).read_text() for p in ['autonomous_generator.md','batch_diversity.md'])
    feedback=read_json(feedback_file) if feedback_file else {}
    status={'job_id':job,'status':'starting','completed':[],'model':config['model'],
            'thinking':False,'external_api_calls':0,'agent_solves':0,'runtime':runtime}
    def save():write_json(run/'status.json',status)
    service=None
    env=os.environ.copy()
    for k in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','PYTHONPATH']:env.pop(k,None)
    env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',
        VLLM_NO_USAGE_STATS='1',DO_NOT_TRACK='1',TOKENIZERS_PARALLELISM='false',PYTHONNOUSERSITE='1',
        OMP_NUM_THREADS=os.environ.get('SLURM_CPUS_PER_TASK','8'),VLLM_WORKER_MULTIPROC_METHOD='spawn',VLLM_USE_FLASHINFER_SAMPLER='0')
    env['PATH']=str(Path(runtime_python).parent)+os.pathsep+env.get('PATH','')
    command=[runtime_python,'-m','vllm.entrypoints.openai.api_server','--model',config['model_path'],
        '--served-model-name',config['model'],'--host','127.0.0.1','--port',str(port),
        '--tensor-parallel-size','1','--dtype','bfloat16','--max-model-len','65536',
        '--max-num-seqs','4','--max-num-batched-tokens','4096','--gpu-memory-utilization','0.9',
        '--compilation-config','{"mode":0,"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[1,2,4]}',
        '--limit-mm-per-prompt','{"image":0,"video":0}','--reasoning-parser','qwen3','--generation-config','vllm']
    if runtime['backend']=='transformers':
        command=[runtime_python,'-u',str(ROOT/'scripts/local_transformers_api.py'),
            '--model',config['model_path'],'--served-model-name',config['model'],'--port',str(port)]
    write_json(run/'service_command.json',command)
    gpu=subprocess.run(['nvidia-smi'],capture_output=True,text=True,timeout=30)
    (run/'gpu.txt').write_text(gpu.stdout+gpu.stderr)
    if gpu.returncode:raise RuntimeError('Allocated GPU unavailable')
    write_json(run/'model_identity.json',{'path':config['model_path'],'model':config['model'],
        'configuration_sha256':file_hash(Path(config['model_path'])/'config.json')})
    (run/'system_prompt.txt').write_text(prompt)
    write_json(run/'code_identity.json',{str(p.relative_to(ROOT)):file_hash(p) for p in
        [Path(__file__),ROOT/'scripts/local_transformers_api.py',ROOT/'scripts/prepare_hundred_materials.py',ROOT/'prompts/autonomous_generator.md',ROOT/'prompts/batch_diversity.md']})
    def stop(signum,frame):raise InterruptedError('Job interrupted')
    signal.signal(signal.SIGTERM,stop)
    try:
        save()
        with (run/'service.log').open('w') as log:
            service=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            status['status']='loading_model';save();deadline=time.monotonic()+1500
            while True:
                if service.poll() is not None:raise RuntimeError('Model service exited')
                try:
                    with urllib.request.urlopen(url+'/models',timeout=3) as response:models=json.load(response)
                    if config['model'] not in [m['id'] for m in models['data']]:raise RuntimeError('Wrong model')
                    write_json(run/'served_models.json',models);break
                except OSError:
                    if time.monotonic()>deadline:raise TimeoutError('Startup deadline')
                    time.sleep(3)
            cases=read_json(out/'private/manifest.json')['cases']
            if selected:cases=[c for c in cases if c['case_id'] in selected]
            if task_ids:
                known={tid for c in cases for tid in c['targets'].values()}
                if not set(task_ids).issubset(known):raise ValueError('Unknown selected task')
                cases=[dict(c,targets={k:v for k,v in c['targets'].items() if v in task_ids}) for c in cases]
                cases=[c for c in cases if c['targets']]
            def generate(case):
                cid=case['case_id'];source=Path(case['source_case_dir'])
                material=read_json(source/'private/material.json');records=read_json(source/'private/records.json')
                environment=public_environment(material,records,case['public_context'])
                payload=payload_for(material,environment,case['targets'])
                if cid in feedback:payload['review_feedback']=feedback[cid]
                errors=[]
                for attempt in range(3):
                    if errors:payload['structural_feedback']=errors[-1]
                    request={'model':config['model'],'messages':[{'role':'system','content':prompt},
                        {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
                        'max_tokens':10000,'temperature':0.65,'top_p':0.8,'top_k':20,
                        'seed':20261009+attempt,'chat_template_kwargs':{'enable_thinking':False},
                        'response_format':{'type':'json_object'}}
                    call=run/f'{cid}_attempt{attempt+1}.json'
                    write_json(call,{'request':request,'status':'requested'})
                    raw=None
                    try:
                        req=urllib.request.Request(url+'/chat/completions',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
                        with urllib.request.urlopen(req,timeout=900) as r:raw=json.load(r)
                        write_json(call,{'request':request,'response':raw,'status':'returned'})
                        if raw['model']!=config['model']:raise ValueError('Response model mismatch')
                        if raw['choices'][0]['finish_reason']!='stop':raise ValueError('Truncated generation')
                        proposal=json.loads(raw['choices'][0]['message']['content'])
                        public=export_tasks(proposal,material,environment,case['targets'])
                        issues=public_style_errors(public)
                        if issues:raise ValueError('; '.join(issues))
                        directory=run/cid
                        write_json(directory/'private/candidate.json',{'identity':{
                            'material_sha256':digest(material),'records_file_sha256':file_hash(source/'private/records.json'),
                            'input_sha256':digest(payload)},'authorship':'local_model_api','proposal':proposal,
                            'source_call_logs':[str(call)],'model':config['model'],'thinking':False})
                        write_json(directory/'candidate_tasks.json',public)
                        return {'case_id':cid,'tasks':len(public),'status':'pending_assistant_review','candidate_dir':str(directory)}
                    except Exception as e:
                        errors.append(str(e));write_json(call,{'request':request,'response':raw,'status':'rejected','error':str(e)})
                return {'case_id':cid,'status':'generation_failed','errors':errors}
            status['status']='generating';save()
            with ThreadPoolExecutor(max_workers=4) as pool:
                for f in as_completed([pool.submit(generate,c) for c in cases]):
                    status['completed'].append(f.result());save()
            status['status']='finished_pending_review' if all(c['status']=='pending_assistant_review' for c in status['completed']) else 'incomplete'
            if status['status']=='incomplete':
                raise RuntimeError('Generation failed for one or more cases; inspect retained call logs')
    except Exception as e:
        status.update(status='failed',error=str(e));raise
    finally:
        if service:
            try:os.killpg(service.pid,signal.SIGTERM);service.wait(timeout=20)
            except (ProcessLookupError,subprocess.TimeoutExpired):
                try:os.killpg(service.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                service.wait()
        status['model_service_stopped']=service is None or service.poll() is not None;save()
        print(json.dumps(status,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cases',nargs='*');p.add_argument('--feedback',type=Path);p.add_argument('--tasks',nargs='*')
    p.add_argument('--runtime-config',type=Path)
    a=p.parse_args();main(a.out,a.cases,a.feedback,a.tasks,a.runtime_config)
