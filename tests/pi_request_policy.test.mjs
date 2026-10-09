import test from 'node:test';
import assert from 'node:assert/strict';
import {providerPolicy,contextUpperBound} from '../scripts/pi_request_policy.mjs';
const config={base_url:'https://api.deepseek.com',model:'deepseek-flash',thinking:'disabled'};
test('remote egress needs both flags and environment credentials',()=>{
  assert.throws(()=>providerPolicy(config,{},{}));
  assert.throws(()=>providerPolicy(config,{'allow-remote':true},{DEEPSEEK_API_KEY:'dummy'}));
  assert.throws(()=>providerPolicy(config,{'allow-remote':true,'allow-data-egress':true},{}));
  const p=providerPolicy(config,{'allow-remote':true,'allow-data-egress':true},{DEEPSEEK_API_KEY:'dummy'});
  assert.equal(p.chatPath,'/chat/completions');assert.equal(p.key,'dummy');
});
test('no automatic model/endpoint/thinking fallback; check-only never reads a key',()=>{
  for(const change of [{model:'deepseek-v4-pro'},{thinking:'enabled'},{base_url:'https://evil.example'},{base_url:'https://api.deepseek.com?key=dummy'}])
    assert.throws(()=>providerPolicy({...config,...change},{'check-only':true},{}));
  assert.equal(providerPolicy(config,{'check-only':true},{DEEPSEEK_API_KEY:'dummy'}).key,undefined);
});
test('context estimate includes new tool data, does not assume unchanged histories',()=>{
  const body={messages:[{role:'user',content:'task'},{role:'tool',content:'长数据'.repeat(500)}],tools:[]};
  const prev={promptTokens:8000,messages:[body.messages[0]],tools:[]};
  assert.ok(contextUpperBound(body,prev)>8000+4500);
  assert.ok(contextUpperBound(body,null)>4500);
});
