import asyncio
import pytest
from app.config import settings
from app.ollama_client import extract, AvailabilityError, ContentError, PermanentError, ResourceError


async def call(tmp_path,photo,**kwargs):
    crop=tmp_path/'crop.png';crop.write_bytes(photo)
    return await extract(crop,['05:15'],tmp_path/'raw.ndjson',**kwargs)


async def test_delayed_first_chunk_and_gaps(ollama,tmp_path,photo,monkeypatch):
    monkeypatch.setattr(settings,'read_timeout',.5)
    ollama.delay=.04;ollama.mode='gaps'
    output,metrics=await call(tmp_path,photo)
    assert output.rows[0].public.value==0
    assert metrics['done'] and 'audit thought' in (tmp_path/'raw.ndjson').read_text()
    assert ollama.requests[0]['think'] is True
    assert ollama.requests[0]['options']['presence_penalty']==0


@pytest.mark.parametrize('mode,error',[('disconnect',ContentError),('truncated',ContentError),('malformed',ContentError),('invalid_message',ContentError),('503',AvailabilityError),('400',PermanentError),('oom',ResourceError)])
async def test_failures(ollama,tmp_path,photo,mode,error):
    ollama.mode=mode
    with pytest.raises(error):await call(tmp_path,photo)


async def test_read_inactivity_timeout(ollama,tmp_path,photo,monkeypatch):
    monkeypatch.setattr(settings,'read_timeout',.03);ollama.delay=.15
    with pytest.raises(AvailabilityError):await call(tmp_path,photo)


async def test_wall_watchdog_closes_request(ollama,tmp_path,photo,monkeypatch):
    monkeypatch.setattr(settings,'wall_timeout',.04);monkeypatch.setattr(settings,'read_timeout',5);ollama.delay=.2
    with pytest.raises(AvailabilityError):await call(tmp_path,photo)
    # The remote may still be computing; local client has exited before this returns.
    await asyncio.sleep(.25)
    assert ollama.active==0
