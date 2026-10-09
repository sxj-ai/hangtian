// Actual Pi SDK orchestration. The Python child is only a closed numerical tool service.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { createHash } from 'node:crypto';
import { RunBudget } from './pi_budget.mjs';
import { providerPolicy, contextUpperBound } from './pi_request_policy.mjs';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => {
  if (v.startsWith('--')) a.push([v.slice(2), all[i+1]?.startsWith('--') ? true : all[i+1] ?? true]);
  return a;
}, []));
const root = fileURLToPath(new URL('../', import.meta.url));
const config = JSON.parse(fs.readFileSync(path.resolve(args.config), 'utf8'));
const out = path.resolve(args.out);
if (fs.existsSync(out)) throw new Error('Use a fresh output directory; previous attempts are immutable.');
fs.mkdirSync(out, {recursive:true, mode:0o700});
const checkOnly = args['check-only'] === true;
const {local,remote,key,endpoint,chatPath}=providerPolicy(config,args,process.env);
const mode = args.mode ?? 'tools';
if (!['tools','no_data','report_only'].includes(mode)) throw new Error('Unknown mode');
if ((mode==='report_only') !== !!args['prior-trajectory']) throw new Error('Prior evidence is for reporting diagnostics only');
const clean = value => JSON.parse(JSON.stringify(value, (k,v) => {
  if (['reasoning_content','thinkingSignature'].includes(k) && typeof v === 'string') return '[not retained]';
  return typeof v === 'string' && key ? v.split(key).join('[REDACTED]') : v;
}));
const write = (name, value) => fs.writeFileSync(path.join(out,name), JSON.stringify(clean(value),null,2));
const append = (name,value) => fs.appendFileSync(path.join(out,name), JSON.stringify(clean(value))+'\n');
const hash = value => createHash('sha256').update(value).digest('hex');

const piEntry = path.resolve(args['pi-entry']);
const pi = await import(pathToFileURL(piEntry));
const aiEntry = path.resolve(path.dirname(piEntry),'../node_modules/@earendil-works/pi-ai/dist/index.js');
const ai = await import(pathToFileURL(aiEntry));
const packagePath = path.resolve(path.dirname(piEntry),'../package.json');
const packageInfo = JSON.parse(fs.readFileSync(packagePath,'utf8'));
if (packageInfo.version !== config.pi_package_version) throw new Error('Unexpected Pi version');
const {createAgentSession,createExtensionRuntime,ModelRuntime,SessionManager,SettingsManager} = pi;
const childEnv = {...process.env, PYTHONPATH:path.join(root,'src')};
delete childEnv.DEEPSEEK_API_KEY;
delete childEnv.OPENAI_API_KEY;delete childEnv.ANTHROPIC_API_KEY;
const child = spawn(args.python ?? 'python3',['-u','-m','hangtian.pi_bridge',
  '--batch',path.resolve(args.batch),'--task',args.task,'--out',out,'--mode',mode,
  '--max-calls',String(config.max_tool_calls_per_task),
  ...(mode==='report_only'?['--prior-trajectory',path.resolve(args['prior-trajectory'])]:[])], {cwd:root, env:childEnv, stdio:['pipe','pipe','pipe']});
const pending=[];
createInterface({input:child.stdout}).on('line',line => {
  const item=pending.shift();
  try { item?.resolve(JSON.parse(line)); } catch { item?.reject(new Error('Malformed trusted tool response')); }
});
child.stderr.on('data',data => append('bridge_errors.jsonl',{message:data.toString()}));
child.on('exit',code => {for (const p of pending.splice(0)) p.reject(new Error(`Tool service exited: ${code}`));});
const rpc = message => new Promise((resolve,reject) => {
  if (child.exitCode !== null) return reject(new Error('Tool service unavailable'));
  pending.push({resolve,reject}); child.stdin.write(JSON.stringify(message)+'\n');
});
let session, timer;
let submitted=false, apiRequests=0, requestHooks=0, assistantTurns=0;
let timedOut=false;
let lastUsageContext=null, infrastructureFailure=null;
const budget=new RunBudget({...config, ...(mode==='tools'?{}:
  {max_api_calls_per_task:1,reserved_report_requests:0})});
const responseAudits=[];
const metadata={task_id:args.task,mode,pi_package:packageInfo.name,pi_version:packageInfo.version,
  model_requested:config.model,thinking_level:'off',thinking_request:local?
    {chat_template_kwargs:{enable_thinking:false}}:{thinking:{type:'disabled'}},
  protocol_version:'pi-budget-v2',remote_data_egress:remote,
  fixture_only:config.fixture_only===true,
  api_requests:0,status:'initializing',started_at:new Date().toISOString(),config};
try {
  const init = await rpc({op:'init'});
  if (init.error) throw new Error(init.error);
  write('public_input.json',init.task);
  const descriptions={
    telemetry_query:'Read or compute over a freely chosen permitted telemetry window. Operation and field semantics are in the system prompt. Returns a reproducible observation_id.',
    submit_report:'Submit your final evidence-based report. A receipt does not evaluate correctness. Cite observations actually returned by telemetry_query.'};
  const customTools = mode !== 'no_data' ? [
    {name:'telemetry_query',label:'Telemetry query',description:descriptions.telemetry_query,
      parameters:init.query_schema,executionMode:'sequential',execute:async(id,query) => {
        let result;
        if(!budget.claimQuery()) result={error:'Investigation budget ended. Submit using existing observations.'};
        else result=await rpc({op:'query',query});
        append('tool_calls.jsonl',{tool_call_id:id,name:'telemetry_query',arguments:query,result});
        if(result.error) throw new Error(result.error);
        return {content:[{type:'text',text:JSON.stringify(result)}],details:{},isError:!!result.error};
      }},
    {name:'submit_report',label:'Submit report',description:descriptions.submit_report,
      parameters:init.answer_schema,executionMode:'sequential',execute:async(id,answer) => {
        const result=await rpc({op:'submit',answer});
        submitted = result.receipt === 'submitted';
        append('tool_calls.jsonl',{tool_call_id:id,name:'submit_report',arguments:answer,result});
        if(result.error) throw new Error(result.error);
        return {content:[{type:'text',text:JSON.stringify(result)}],details:{},isError:!!result.error};
      }}].filter(t=>mode!=='report_only'||t.name==='submit_report') : [];
  const cwd=path.join(out,'isolated'); fs.mkdirSync(cwd);
  const runtime=await ModelRuntime.create({credentials:new ai.InMemoryCredentialStore(),
    modelsPath:null,modelsStorePath:path.join(cwd,'models-cache.json'),
    allowModelNetwork:false,refreshOnCreate:false});
  runtime.registerProvider(config.provider,{api:'openai-completions',baseUrl:config.base_url,
    apiKey:key??'offline-or-local-no-auth',authHeader:remote,models:[{id:config.model,name:config.model,
      reasoning:true,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},
      contextWindow:config.context_window,maxTokens:config.max_output_tokens,
      compat:{...(local?{thinkingFormat:'qwen-chat-template'}:{}),supportsReasoningEffort:false,maxTokensField:'max_tokens',
        supportsStore:false,supportsDeveloperRole:false}}]});
  const model=runtime.getModel(config.provider,config.model);
  let system=fs.readFileSync(path.join(root,'prompts/pi_investigator.md'),'utf8');
  if(mode==='report_only') system=fs.readFileSync(path.join(root,'prompts/pi_reporting_probe.md'),'utf8');
  if(mode==='no_data') system='You are answering an investigation request in a no-data control condition. You have only the public task and metadata; no telemetry tools or actual record values are available. Give your best answer in Chinese, clearly separating conclusions supported by this visible information from guesses and missing evidence. Do not invent measurements or claim you inspected records. Return plain text.';
  const loader={
    getExtensions:()=>({extensions:[],errors:[],runtime:createExtensionRuntime()}),
    getSkills:()=>({skills:[],diagnostics:[]}),getPrompts:()=>({prompts:[],diagnostics:[]}),
    getThemes:()=>({themes:[],diagnostics:[]}),getAgentsFiles:()=>({agentsFiles:[]}),
    getSystemPrompt:()=>system,getSystemPromptSource:()=>undefined,
    getAppendSystemPrompt:()=>[],getAppendSystemPromptSources:()=>[],
    extendResources:()=>{},reload:async()=>{}};
  ({session}=await createAgentSession({cwd,agentDir:cwd,modelRuntime:runtime,model,
    thinkingLevel:'off',tools:customTools.map(t=>t.name),customTools,resourceLoader:loader,
    sessionManager:SessionManager.inMemory(cwd),settingsManager:SettingsManager.inMemory({
      compaction:{enabled:false},retry:{enabled:false},httpIdleTimeoutMs:180000,
      enableAnalytics:false,enableInstallTelemetry:false})}));
  const active=session.getActiveToolNames().sort();
  if(JSON.stringify(active)!==JSON.stringify(customTools.map(t=>t.name).sort())) throw new Error('Unexpected active tools');
  write('session_boundary.json',{active_tools:active,history_messages:session.messages.length,
    initial_messages:session.messages,project_context_files:[],skills:[],extensions:[],
    system_prompt:session.systemPrompt,system_prompt_sha256:hash(session.systemPrompt),
    private_reference_exposed:false,tool_scope:'approved public record catalog only'});
  // Pi renders its custom preamble and an automatic cwd section. No other section
  // or prior user/assistant/tool history is permitted.
  const expectedPrompt=system+'\n\n<cwd>\n'+cwd+'\n</cwd>';
  if(session.messages.some(m=>m.role!=='system') || session.thinkingLevel!=='off'
    || ![system,expectedPrompt].includes(session.systemPrompt)) throw new Error('Session context isolation failed');
  if(checkOnly){metadata.status='offline_pi_session_created';}
  else {
    const originalPrepare=session.agent.prepareRequest;
    session.agent.prepareRequest=async(request,signal)=>{
      const prepared=await originalPrepare?.(request,signal);
      const context=prepared?.context??request.context;
      budget.refresh();
      if(budget.reportingReason){
        session.setActiveToolsByName(['submit_report']);
        return {...prepared,context:{...context,tools:(context.tools??[]).filter(t=>t.name==='submit_report')}};
      }
      return prepared;
    };
    const nativeFetch=globalThis.fetch;
    const guardedFetch=async(input,options={})=>{
      const url=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url);
      if(url.origin!==endpoint.origin||url.pathname!==chatPath || url.search || url.hash)
        throw new Error('Endpoint outside authorized scope');
      const originalBody=JSON.parse(options.body);
      let body=budget.prepare(originalBody);
      if(body.model!==config.model || body.reasoning_effort!==undefined ||
        (local?body.chat_template_kwargs?.enable_thinking!==false:body.thinking?.type!=='disabled'))
        throw new Error('Actual request does not match no-thinking model policy');
      if(remote && new Headers(options.headers).get('authorization')!==`Bearer ${key}`)
        throw new Error('Missing authorized provider credential');
      let promptTokens=null;
      let contextCountMethod=null;
      if(config.count_context_tokens && mode==='tools'){
        if(!local) throw new Error('Exact local tokenizer is unavailable for this provider');
        const countTokens=async value=>{
          const response=await nativeFetch(new URL('/tokenize',endpoint),{method:'POST',redirect:'error',
            headers:{'content-type':'application/json'},signal:AbortSignal.timeout(60000),
            body:JSON.stringify({model:value.model,messages:value.messages,tools:value.tools,
              chat_template_kwargs:value.chat_template_kwargs})});
          if(!response.ok) throw new Error(`Local tokenizer failed: ${response.status}`);
          const result=await response.json();
          if(!Number.isInteger(result.count)) throw new Error('Invalid tokenizer count');
          return result.count;
        };
        promptTokens=await countTokens(body);
        contextCountMethod='exact_local_tokenizer';
        const previous=budget.reportingReason;
        budget.refresh(promptTokens);
        if(previous!==budget.reportingReason){body=budget.prepare(originalBody);promptTokens=await countTokens(body);}
        if(promptTokens+body.max_tokens>config.context_window)
          throw new Error('Context capacity exceeded; original evidence was not truncated');
      }
      if(remote && mode==='tools'){
        await Promise.all(responseAudits);
        promptTokens=contextUpperBound(body,lastUsageContext);
        contextCountMethod='previous_provider_usage_plus_new_utf8_upper_bound';
        const previous=budget.reportingReason;
        budget.refresh(promptTokens);
        if(previous!==budget.reportingReason){body=budget.prepare(originalBody);promptTokens=contextUpperBound(body,lastUsageContext);}
        if(promptTokens+body.max_tokens>config.context_window)
          throw new Error('Conservative context limit exceeded; original evidence was not truncated');
      }
      const wireBody=JSON.stringify(body);
      if(Buffer.byteLength(wireBody)>config.max_input_bytes) throw new Error('Input byte budget exhausted');
      if(key && wireBody.includes(key)) throw new Error('Credential unexpectedly present in model payload');
      if(budget.exhausted) throw new Error('API request budget exhausted');
      apiRequests++;
      budget.requests=apiRequests;
      append('request_audit.jsonl',{index:apiRequests,url:url.href,model:body.model,chat_template_kwargs:body.chat_template_kwargs,thinking:body.thinking,
        max_tokens:body.max_tokens,temperature:body.temperature,tool_names:(body.tools??[]).map(t=>t.function.name),
        message_count:body.messages.length,payload_sha256:hash(wireBody),input_bytes:Buffer.byteLength(wireBody),
        prompt_tokens_preflight:promptTokens,context_count_method:contextCountMethod,
        budget_notice:budget.reserve?JSON.parse(body.messages.at(-1).content):null});
      const response=await nativeFetch(input,{...options,body:wireBody,redirect:'error'});
      if(!response.ok) infrastructureFailure=`Provider HTTP ${response.status}`;
      const index=apiRequests;
      responseAudits.push(response.clone().text().then(text=>{
        const audit={index,http_status:response.status,models:[],response_ids:[],usage:null,reasoning_content_seen:false};
        for(const line of text.split('\n')){
          if(!line.startsWith('data: ')||line==='data: [DONE]') continue;
          try {const chunk=JSON.parse(line.slice(6));
            if(chunk.model&&!audit.models.includes(chunk.model)) audit.models.push(chunk.model);
            if(chunk.id&&!audit.response_ids.includes(chunk.id)) audit.response_ids.push(chunk.id);
            if(chunk.usage) audit.usage=chunk.usage;
            if(chunk.choices?.some(c=>!!c.delta?.reasoning_content)) audit.reasoning_content_seen=true;
          } catch {}
        }
        append('response_audit.jsonl',audit);
        if(audit.usage) lastUsageContext={promptTokens:audit.usage.prompt_tokens,messages:body.messages,tools:body.tools};
      }).catch(()=>append('response_audit.jsonl',{index,audit_error:'Response stream interrupted'})));
      return response;
    };
    const originalStream=session.agent.streamFunction;
    session.agent.streamFunction=(m,c,o)=>originalStream(m,c,{...o,fetch:guardedFetch,maxRetries:0});
    session.agent.onPayload=payload=>{
      requestHooks++;
      delete payload.thinking;delete payload.reasoning_effort;delete payload.chat_template_kwargs;
      if(local) payload.chat_template_kwargs={enable_thinking:false};
      else payload.thinking={type:'disabled'};
      payload.max_tokens=config.max_output_tokens;delete payload.max_completion_tokens;
      payload.temperature=config.temperature;
      if(local){payload.top_p=config.top_p;payload.top_k=config.top_k;payload.seed=config.seed;}
      else {delete payload.top_p;delete payload.top_k;delete payload.seed;}
      return payload;
    };
    session.agent.finishTurn=()=>submitted||budget.exhausted||timedOut||infrastructureFailure?{action:'end'}:undefined;
    session.subscribe(event=>{
      if(event.type==='message_end' && event.message.role==='toolResult')
        append('pi_tool_results.jsonl',event.message);
      if(event.type==='message_end' && event.message.role==='assistant'){
        assistantTurns++;
        const m={...event.message,content:event.message.content.filter(c=>c.type!=='thinking')};
        if(m.stopReason==='error') infrastructureFailure=m.errorMessage??'Provider response error';
        append('assistant_messages.jsonl',m);
        console.log(JSON.stringify({task:args.task,mode,assistant_turn:assistantTurns,
          tool_calls:m.content.filter(c=>c.type==='toolCall').map(c=>c.name),stop_reason:m.stopReason}));
      }
    });
    timer=setTimeout(()=>{timedOut=true;session.agent.abort();},config.max_run_seconds*1000);
    metadata.status='running';write('run_metadata.json',metadata);
    await session.prompt(JSON.stringify({task:init.task,
      ...(mode==='report_only'?{prior_observations:init.prior_observations}:{}),
      budget:{max_api_calls:mode==='tools'?config.max_api_calls_per_task:1,
      max_tool_calls:mode==='tools'?config.max_tool_calls_per_task:mode==='report_only'?1:0}}));
    // Continue the SAME Pi session only for submission/repair. Never seed a new
    // conversation, inject facts or turn a receipt into a correctness verdict.
    while(mode==='tools' && budget.reserve && !submitted && !budget.exhausted && !timedOut && !infrastructureFailure){
      budget.enterReporting('assistant_stopped_without_submission');
      session.setActiveToolsByName(['submit_report']);
      const before=apiRequests;
      await session.prompt('The task is not submitted. Use submit_report with the evidence already in this conversation. Correct any rejected submission; state unresolved limitations. No additional investigation is available.');
      if(apiRequests===before) break;
    }
    await Promise.all(responseAudits);
    metadata.status=submitted?'submitted':mode==='no_data'?'no_data_response':'no_submission';
    if(infrastructureFailure){metadata.status='provider_error';metadata.error=infrastructureFailure;process.exitCode=1;}
    write('final_text.json',{text:session.getLastAssistantText()??''});
  }
  await rpc({op:'finish'});
} catch(error){metadata.status='error';metadata.error=String(error);process.exitCode=1;}
finally{
  clearTimeout(timer);
  metadata.api_requests=apiRequests;metadata.payload_hooks=requestHooks;metadata.assistant_turns=assistantTurns;
  metadata.budget_state={queries:budget.queries,reporting_reason:budget.reportingReason,
    effective_request_limit:budget.limit,exhausted:budget.exhausted,timed_out:timedOut,
    same_session_reporting:true};
  metadata.finished_at=new Date().toISOString();write('run_metadata.json',metadata);
  session?.dispose();child.stdin.end();
  console.log(JSON.stringify({task:args.task,mode,status:metadata.status,api_requests:apiRequests}));
}
