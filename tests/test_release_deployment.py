import json
import shutil
import subprocess

import pytest

from scripts.prepare_release import prepare


IMAGE='ghcr.io/willtheorangeguy/ucac-ocr'


@pytest.mark.skipif(shutil.which('docker') is None,reason='Docker Compose CLI is unavailable')
def test_release_files_work_without_a_checkout_or_dockerfile(tmp_path):
    prepare('v0.1.0',IMAGE,tmp_path)
    assert {p.name for p in tmp_path.iterdir()}=={'compose.yaml','.env'}
    environment=(tmp_path/'.env').read_text()
    assert f'POOL_HEADCOUNT_IMAGE={IMAGE}:0.1.0' in environment
    # Use the Compose parser to verify file-relative env paths and interpolation.
    result=subprocess.run(['docker','compose','--project-directory',str(tmp_path),'--env-file',str(tmp_path/'.env'),
                           '-f',str(tmp_path/'compose.yaml'),'config','--format','json'],capture_output=True,text=True)
    if result.returncode and ('not found' in result.stderr.lower() or 'not recognized' in result.stderr.lower()):
        pytest.skip('Docker Compose is unavailable')
    assert result.returncode==0,result.stderr
    config=json.loads(result.stdout)
    for service in config['services'].values():
        assert service['image']==IMAGE+':0.1.0'
        assert 'build' not in service
        assert service['environment']['DATA_DIR']=='/data'


def test_new_release_updates_both_image_defaults(tmp_path):
    prepare('v0.2.0',IMAGE,tmp_path)
    assert f'POOL_HEADCOUNT_IMAGE={IMAGE}:0.2.0' in (tmp_path/'.env').read_text()
    assert f'${{POOL_HEADCOUNT_IMAGE:-{IMAGE}:0.2.0}}' in (tmp_path/'compose.yaml').read_text()


@pytest.mark.parametrize('tag',['main','v0.1','v0.1.0;echo unsafe','v0.1.0\nextra'])
def test_release_tag_is_validated_before_writing_files(tmp_path,tag):
    with pytest.raises(ValueError):prepare(tag,IMAGE,tmp_path/'release')
    assert not (tmp_path/'release').exists()
