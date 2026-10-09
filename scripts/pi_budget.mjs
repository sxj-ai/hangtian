// Generic execution policy: no task facts, reference answers or analysis routes.
export class RunBudget {
  constructor(config, now = () => Date.now()) {
    this.config = config;
    this.now = now;
    this.started = now();
    this.requests = 0;
    this.queries = 0;
    this.reportingReason = null;
    this.limit = config.max_api_calls_per_task;
    this.reserve = config.reserved_report_requests ?? 0;
    if (!Number.isInteger(this.limit) || this.limit < 1 ||
        !Number.isInteger(this.reserve) || this.reserve < 0 || this.reserve >= this.limit)
      throw new Error('Invalid request/report budget');
  }
  enterReporting(reason) {
    if (!this.reserve || this.reportingReason) return;
    this.reportingReason = reason;
    this.limit = Math.min(this.limit, this.requests + this.reserve);
  }
  refresh(promptTokens = 0) {
    if (!this.reserve) return;
    if (this.requests >= this.config.max_api_calls_per_task - this.reserve)
      this.enterReporting('reserved_report_requests');
    else if (this.queries >= this.config.max_tool_calls_per_task)
      this.enterReporting('query_budget');
    else if (promptTokens >= this.config.report_at_context_tokens)
      this.enterReporting('context_capacity');
    else if (this.now() - this.started >=
        (this.config.max_run_seconds - this.config.reserved_report_seconds) * 1000)
      this.enterReporting('time_reserve');
  }
  get exhausted() { return this.requests >= this.limit; }
  // Called during execution of the already-advertised turn. Do not refresh the
  // request phase here: the current final investigation response still owns it.
  claimQuery() {
    if(this.reportingReason || this.queries>=this.config.max_tool_calls_per_task) return false;
    this.queries++;
    return true;
  }
  notice() {
    return {
      type: 'runtime_budget_notice', request: this.requests + 1,
      maximum_model_requests: this.config.max_api_calls_per_task,
      requests_left_including_this: Math.max(0, this.limit - this.requests),
      queries_left: Math.max(0, this.config.max_tool_calls_per_task - this.queries),
      phase: this.reportingReason ? 'reporting' : 'investigation',
      reporting_reason: this.reportingReason,
      instruction: this.reportingReason
        ? 'Investigation has ended. Use the evidence already in this same conversation to call submit_report now. Correct any rejected submission within the remaining requests. State unresolved limits; do not invent missing evidence.'
        : `Choose your own analysis. Finish with submit_report when ready. The final ${this.reserve} requests are reserved for reporting and submission repair.`,
    };
  }
  prepare(payload) {
    this.refresh();
    const result = structuredClone(payload);
    if (this.reserve) {
      result.messages.push({role: 'user', content: JSON.stringify(this.notice())});
      if (this.reportingReason)
        result.tools = (result.tools ?? []).filter(t => t.function.name === 'submit_report');
    }
    return result;
  }
}
