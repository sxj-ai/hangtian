"""Small offline, loopback-only authoring adapter for an allocated CUDA GPU.

JSON mode is requested in the prompt, not grammar constrained by this backend.
The authoring caller still rejects malformed/truncated/unreviewed responses.
"""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import time
import uuid


def validate_request(body, model):
    if body.get('model') != model:
        raise ValueError('Unexpected model')
    if body.get('chat_template_kwargs', {}).get('enable_thinking') is not False:
        raise ValueError('Only explicitly disabled thinking is allowed')
    if body.get('stream') or body.get('tools'):
        raise ValueError('This adapter only supports nonstreaming authoring')
    if not 1 <= body.get('max_tokens', 0) <= 10000:
        raise ValueError('Invalid output budget')
    messages = body.get('messages')
    if not isinstance(messages, list) or not messages or any(
        m.get('role') not in {'system', 'user', 'assistant'} or not isinstance(m.get('content'), str)
        for m in messages
    ):
        raise ValueError('Expected plain text chat messages')


def main(args):
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('GPU allocation required')
    import torch
    import transformers
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
    if not torch.cuda.is_available():
        raise RuntimeError('Allocated CUDA device unavailable')
    print(json.dumps({'backend': 'transformers', 'torch': torch.__version__,
        'cuda_runtime': torch.version.cuda, 'transformers': transformers.__version__,
        'gpu': torch.cuda.get_device_name(0), 'thinking': False}), flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = Qwen3_5ForConditionalGeneration.from_pretrained(
        args.model, local_files_only=True, dtype=torch.bfloat16,
        device_map='cuda:0', attn_implementation='sdpa').eval()

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, code, data):
            raw = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path != '/v1/models':
                return self.send_json(404, {'error': 'Unknown endpoint'})
            self.send_json(200, {'object': 'list', 'data': [
                {'id': args.served_model_name, 'object': 'model', 'owned_by': 'local'}]})

        def do_POST(self):
            if self.path != '/v1/chat/completions':
                return self.send_json(404, {'error': 'Unknown endpoint'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 2000000:
                    raise ValueError('Invalid request length')
                body = json.loads(self.rfile.read(size))
                validate_request(body, args.served_model_name)
                rendered = tokenizer.apply_chat_template(body['messages'], tokenize=False,
                    add_generation_prompt=True, enable_thinking=False)
                encoded = tokenizer(rendered, return_tensors='pt', add_special_tokens=False).to('cuda:0')
                count = encoded['input_ids'].shape[-1]
                if count + body['max_tokens'] > 65536:
                    raise ValueError('Context budget exceeded')
                torch.manual_seed(body.get('seed', 20261009))
                start = time.monotonic()
                with torch.inference_mode():
                    generated = model.generate(**encoded, max_new_tokens=body['max_tokens'],
                        do_sample=True, temperature=body.get('temperature', 0.65),
                        top_p=body.get('top_p', 0.8), top_k=body.get('top_k', 20),
                        use_cache=True, logits_to_keep=1)
                ids = generated[0, count:]
                text = tokenizer.decode(ids, skip_special_tokens=True)
                result = {'id': 'local-hf-' + uuid.uuid4().hex,
                    'object': 'chat.completion', 'created': int(time.time()),
                    'model': args.served_model_name,
                    'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text},
                        'finish_reason': 'length' if len(ids) >= body['max_tokens'] else 'stop'}],
                    'usage': {'prompt_tokens': count, 'completion_tokens': len(ids),
                        'total_tokens': count + len(ids)},
                    'local_backend': {'engine': 'transformers', 'version': transformers.__version__,
                        'torch': torch.__version__, 'cuda_runtime': torch.version.cuda,
                        'thinking': False, 'json_grammar_enforced': False,
                        'generation_seconds': time.monotonic() - start}}
                self.send_json(200, result)
            except Exception as error:
                print(type(error).__name__ + ': ' + str(error), flush=True)
                self.send_json(500, {'error': str(error)})

    print('Local authoring API ready', flush=True)
    HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True, type=Path)
    p.add_argument('--served-model-name', required=True)
    p.add_argument('--port', required=True, type=int)
    main(p.parse_args())
