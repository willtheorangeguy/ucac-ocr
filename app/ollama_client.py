import asyncio
import base64
import json
import os
import time
from pathlib import Path
import httpx
from .config import settings
from .prompts import prompt, schema
from .schemas import Extraction, QuickExtraction


class AvailabilityError(Exception):pass
class ContentError(Exception):pass
class PermanentError(Exception):pass
class ResourceError(Exception):pass


def classify(status,text):
    if 'out of memory' in text.lower() or 'oom' in text.lower(): raise ResourceError(text)
    if any(term in text.lower() for term in ('unsupported option','does not support','model not found','requires ollama','invalid option','unauthorized')):raise PermanentError(text)
    if status in (429,503) or status>=500: raise AvailabilityError(text)
    raise PermanentError(f'HTTP {status}: {text}')


async def preflight():
    if not settings.ollama_base_url:raise PermanentError('Set OLLAMA_BASE_URL to your existing Ollama LAN endpoint, then resume')
    if not settings.ollama_base_url.startswith(('http://','https://')):raise PermanentError('OLLAMA_BASE_URL must be an HTTP(S) endpoint')
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url,timeout=15,trust_env=False) as c:
            v=await c.get('/api/version')
            if v.status_code!=200:classify(v.status_code,v.text)
            version=tuple(int(x) for x in v.json()['version'].split('-')[0].split('.')[:3])
            if version<(0,17,1):raise PermanentError('Ollama 0.17.1 or later is required')
            r=await c.post('/api/show',json={'model':settings.ollama_model})
            if r.status_code!=200:classify(r.status_code,r.text)
            info=r.json()
            if 'vision' not in info.get('capabilities',[]):raise PermanentError('Configured model has no vision capability')
            if settings.think and 'thinking' not in info.get('capabilities',[]):raise PermanentError('Configured model has no thinking capability')
            tags=await c.get('/api/tags'); digest=None
            if tags.status_code==200:
                digest=next((m.get('digest') for m in tags.json().get('models',[]) if m.get('name')==settings.ollama_model),None)
            return dict(version=v.json()['version'],digest=digest,capabilities=info.get('capabilities'),model=settings.ollama_model)
    except (httpx.TransportError,ValueError,KeyError) as e:
        raise AvailabilityError(str(e)) from e


async def health():
    try:
        async with httpx.AsyncClient(timeout=5,trust_env=False) as c:
            r=await c.get(settings.ollama_base_url.rstrip('/')+'/api/version')
            return r.status_code==200
    except (httpx.HTTPError,ValueError):return False


async def extract(crop,expected,raw_path,smaller=False,on_chunk=None,transport=None):
    system,user=prompt(expected)
    payload=dict(model=settings.ollama_model,stream=True,think=settings.think,keep_alive=settings.keep_alive,
                 format=schema(expected),options=settings.profile(smaller),messages=[{'role':'system','content':system},
                 {'role':'user','content':user,'images':[base64.b64encode(Path(crop).read_bytes()).decode()]}])
    timeout=httpx.Timeout(connect=settings.connect_timeout,read=settings.read_timeout,write=settings.write_timeout,pool=settings.pool_timeout)
    raw=Path(raw_path); raw.parent.mkdir(parents=True,exist_ok=True)
    content=[]; thinking=[]; received=0; done=None
    try:
        # asyncio.timeout cancels the coroutine, unwinding response/client contexts before return.
        async with asyncio.timeout(settings.wall_timeout or None):
            async with httpx.AsyncClient(base_url=settings.ollama_base_url,timeout=timeout,trust_env=False,transport=transport) as client:
                async with client.stream('POST','/api/chat',json=payload) as response:
                    if response.status_code!=200:
                        body=(await response.aread())[:8000].decode(errors='replace')
                        classify(response.status_code,body)
                    with raw.open('xb') as log:
                        async for line in response.aiter_lines():
                            if not line:continue
                            received+=len(line.encode())
                            if received>settings.max_response_bytes:raise ContentError('Raw response storage bound exceeded')
                            arrived=time.time()
                            log.write((json.dumps({'arrived':arrived,'chunk':line})+'\n').encode()); log.flush()
                            if on_chunk:on_chunk(arrived)
                            try:chunk=json.loads(line)
                            except ValueError as e:raise ContentError('Malformed stream chunk') from e
                            if not isinstance(chunk,dict):raise ContentError('Stream chunk must be an object')
                            if 'error' in chunk:classify(500,str(chunk['error']))
                            message=chunk.get('message',{})
                            if not isinstance(message,dict) or any(not isinstance(message.get(k,''),str) for k in ('content','thinking')):
                                raise ContentError('Invalid streamed message content')
                            content.append(message.get('content','')); thinking.append(message.get('thinking',''))
                            if chunk.get('done') is True:done=chunk; break
                        os.fsync(log.fileno())
        if done is None or done.get('done_reason') not in ('stop',):raise ContentError('Stream incomplete or generation truncated')
        try:
            data=json.loads(''.join(content))
            # Also accept saved/detailed readings when recovering older work.
            if expected and settings.rough_counts and isinstance(data,dict) and set(data)=={'rows'}:
                result=QuickExtraction.model_validate(data).expand().check(expected)
            else:result=Extraction.model_validate(data).check(expected)
        except ValueError as e:raise ContentError(str(e)) from e
        metrics={k:v for k,v in done.items() if k!='message'}
        return result,metrics
    except (httpx.TransportError,TimeoutError) as e:
        raise AvailabilityError(f'Uncertain request termination: {type(e).__name__}: {e}') from e
