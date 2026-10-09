// Explicit provider boundary; never auto-switch models or destinations.
export function providerPolicy(config, args, env) {
  const endpoint=new URL(config.base_url);
  const local=endpoint.protocol==='http:' && endpoint.hostname==='127.0.0.1' &&
    endpoint.pathname==='/v1' && config.model==='Qwen3.5-27B';
  const remote=endpoint.href==='https://api.deepseek.com/' && config.model==='deepseek-flash';
  if(endpoint.username || endpoint.password || endpoint.search || endpoint.hash ||
    config.thinking!=='disabled' || (!local && !remote)) throw new Error('Unapproved model or endpoint');
  const checkOnly=args['check-only']===true;
  if(!checkOnly && local && !args['allow-local-inference']) throw new Error('Explicit local inference flag required');
  if(!checkOnly && remote && (!args['allow-remote'] || !args['allow-data-egress']))
    throw new Error('Explicit remote inference and data egress flags required');
  const key=remote && !checkOnly ? env.DEEPSEEK_API_KEY?.trim() : undefined;
  if(remote && !checkOnly && !key) throw new Error('DEEPSEEK_API_KEY is required');
  return {local,remote,key,endpoint,chatPath:local?'/v1/chat/completions':'/chat/completions'};
}

// Provider usage anchors the existing prefix; newly appended UTF-8 bytes are a
// conservative estimate, not an exact tokenizer count. History is never removed.
export function contextUpperBound(body, previous) {
  if(!previous || !Number.isInteger(previous.promptTokens))
    return Buffer.byteLength(JSON.stringify({messages:body.messages,tools:body.tools})) + 4096 + 64*body.messages.length;
  let common=0;
  while(common<Math.min(body.messages.length,previous.messages.length) &&
    JSON.stringify(body.messages[common])===JSON.stringify(previous.messages[common])) common++;
  const suffix=body.messages.slice(common);
  const changedTools=JSON.stringify(body.tools)!==JSON.stringify(previous.tools);
  return previous.promptTokens + Buffer.byteLength(JSON.stringify(suffix)) + 4096 + 64*suffix.length +
    (changedTools?Buffer.byteLength(JSON.stringify(body.tools??[])):0);
}
