from fastapi.testclient import TestClient
from app.main import app
from app.db import query
from conftest import make_job


def test_pages_upload_review_and_origin(data,photo):
    job=make_job(data)
    with TestClient(app) as c:
        assert c.get('/health').status_code==200
        assert c.get('/').status_code==200
        assert c.get('/settings').status_code==200
        assert c.get('/jobs/'+job).status_code==200
        r=c.post('/api/jobs/'+job+'/photos',files={'photos':('test.png',photo,'image/png')})
        assert r.json()['added']==1
        assert c.get('/api/jobs/'+job).json()['sources'][0]['state']=='pending'
        assert c.post('/api/jobs/'+job+'/control/pause',json={}).status_code==200
        assert query('SELECT state FROM jobs',one=True)['state']=='paused'
        assert c.post('/api/jobs/'+job+'/control/resume',json={},headers={'Origin':'https://other.example'}).status_code==403
