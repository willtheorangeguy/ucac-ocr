"""Prepare standalone Compose downloads from tracked example configuration."""
import argparse
import re
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


def prepare(tag,image,destination):
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?',tag):
        raise ValueError('Release tag must be vMAJOR.MINOR.PATCH, optionally with a prerelease suffix')
    if not re.fullmatch(r'[a-z0-9][a-z0-9./_-]*',image):raise ValueError('Invalid container image name')
    version=tag[1:]
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    compose=(ROOT/'compose.yaml').read_text()
    # Keep even the fallback image pinned to this release for bare Compose use.
    compose=re.sub(r'\$\{POOL_HEADCOUNT_IMAGE:-[^}]+\}',lambda _:f'${{POOL_HEADCOUNT_IMAGE:-{image}:{version}}}',compose)
    (destination/'compose.yaml').write_text(compose,encoding='utf-8',newline='\n')
    example=(ROOT/'.env.example').read_text()
    example=re.sub(r'^POOL_HEADCOUNT_IMAGE=.*$',lambda _:f'POOL_HEADCOUNT_IMAGE={image}:{version}',example,flags=re.MULTILINE)
    (destination/'.env').write_text(example,encoding='utf-8',newline='\n')
    return version


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag');parser.add_argument('image');parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    prepare(args.tag,args.image,args.destination)
