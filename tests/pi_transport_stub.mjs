// Offline Pi integration fixture. No external fetch survives this preload.
import assert from 'node:assert/strict';
let request=0;
globalThis.fetch=async(input,options)=>{
  const url=new URL(typeof input==='string'?input:input.url??input.href);
  assert.equal(url.href,'https://api.deepseek.com/chat/completions');
  assert.equal(new Headers(options.headers).get('authorization'),'Bearer fixture-not-a-real-key');
  const body=JSON.parse(options.body);request++;
  assert.equal(body.thinking.type,'disabled');
  assert.equal(body.reasoning_effort,undefined);
  assert.deepEqual(body.tools.map(t=>t.function.name).sort(),request<=3?
    ['submit_report','telemetry_query']:['submit_report']);
  assert.equal(JSON.parse(body.messages.at(-1).content).request,request);
  let name,arguments_;
  if(request<=3){
    name='telemetry_query';
    arguments_={record_id:'E2_C1',op:'stat',start_row:0,stop_row:10,
      channel:request===1?'NOT_A_CHANNEL':'U_SA',stat:request===3?'max':'mean'};
  } else {
    name='submit_report';
    const observation=body.messages.filter(m=>m.role==='tool').flatMap(m=>{
      try {const v=JSON.parse(m.content);return v.observation_id?[v.observation_id]:[];}catch{return [];}
    }).at(-1);
    assert.ok(observation,'Fixture requires a successful tool observation, including request3');
    arguments_={findings:[{claim:'Offline protocol fixture only; no scientific conclusion.',
      observation_ids:request===4?[]:[observation]}],conclusion:'Offline protocol fixture, not model inference.',limitations:['No quality assessment.']};
  }
  assert.ok(request<=5);
  const chunk={id:`fixture-${request}`,object:'chat.completion.chunk',created:0,model:'fixture-transport',
    choices:[{index:0,delta:{role:'assistant',tool_calls:[{index:0,id:`fixture-call-${request}`,type:'function',
      function:{name,arguments:JSON.stringify(arguments_)}}]},finish_reason:null}]};
  const last={...chunk,choices:[{index:0,delta:{},finish_reason:'tool_calls'}],
    usage:{prompt_tokens:2000,completion_tokens:100,total_tokens:2100}};
  return new Response(`data: ${JSON.stringify(chunk)}\n\ndata: ${JSON.stringify(last)}\n\ndata: [DONE]\n\n`,
    {status:200,headers:{'content-type':'text/event-stream'}});
};
