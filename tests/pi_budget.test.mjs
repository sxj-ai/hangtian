import test from 'node:test';
import assert from 'node:assert/strict';
import {RunBudget} from '../scripts/pi_budget.mjs';

const config = {max_api_calls_per_task:80, reserved_report_requests:3,
  max_tool_calls_per_task:320, report_at_context_tokens:100000,
  max_run_seconds:7200, reserved_report_seconds:600};
const payload = {messages:[{role:'user', content:'public task'},
  {role:'tool', content:'unaltered observation'}],
  tools:['telemetry_query','submit_report'].map(name=>({function:{name}}))};

test('77 investigation requests leave three report/repair requests in the same history',()=>{
  const budget = new RunBudget(config);
  for(let i=0;i<80;i++) {
    const request=budget.prepare(payload);
    assert.deepEqual(request.messages.slice(0,-1),payload.messages);
    assert.equal(budget.exhausted,false);
    assert.equal(request.tools.length,i<77?2:1);
    assert.equal(JSON.parse(request.messages.at(-1).content).requests_left_including_this,80-i);
    budget.requests++;
  }
  assert.equal(budget.exhausted,true);
  assert.equal(budget.reportingReason,'reserved_report_requests');
  assert.equal(payload.messages.length,2);
});
test('all queries emitted by the final investigation response retain advertised access',()=>{
  const b=new RunBudget(config);b.requests=76;
  assert.equal(b.prepare(payload).tools.length,2);
  b.requests++; // request77 is now in flight/finished, before tool execution
  assert.equal(b.claimQuery(),true);
  assert.equal(b.claimQuery(),true); // multi-call responses share the same phase
  assert.equal(b.reportingReason,null);
  assert.equal(b.prepare(payload).tools.length,1); // next request78 changes phase
  assert.equal(b.claimQuery(),false);
});
test('a single multi-tool response cannot bypass the hard query cap',()=>{
  const b=new RunBudget(config);b.queries=319;
  assert.equal(b.claimQuery(),true);
  assert.equal(b.claimQuery(),false);
  assert.equal(b.queries,320);
});
test('query exhaustion, context pressure and time reserve each close investigation',()=>{
  for(const reason of ['query_budget','context_capacity','time_reserve']) {
    let clock=0;
    const b=new RunBudget(config,()=>clock);
    b.requests=12;
    if(reason==='query_budget')b.queries=320;
    if(reason==='time_reserve')clock=6600000;
    b.refresh(reason==='context_capacity'?100000:0);
    assert.equal(b.reportingReason,reason);
    assert.equal(b.limit,15);
    assert.deepEqual(b.prepare(payload).tools,[{function:{name:'submit_report'}}]);
  }
});
test('early plain-text stop permits three submission attempts without resetting evidence',()=>{
  const b=new RunBudget(config);b.requests=11;
  b.enterReporting('assistant_stopped_without_submission');
  b.enterReporting('second_notice');
  assert.equal(b.limit,14);
  assert.equal(b.reportingReason,'assistant_stopped_without_submission');
  assert.deepEqual(b.prepare(payload).messages.slice(0,-1),payload.messages);
});
test('historical configuration retains its original payload',()=>{
  const b=new RunBudget({...config,reserved_report_requests:0,max_api_calls_per_task:20});
  b.requests=19;
  assert.deepEqual(b.prepare(payload),payload);
  b.requests++;
  assert.equal(b.exhausted,true);
});
