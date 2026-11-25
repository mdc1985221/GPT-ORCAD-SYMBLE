"""Reviewed connector drawing adapters, separate electrical pins and hold-downs."""
from pathlib import Path
import hashlib,json,copy
BASE=Path(__file__).parent

def profile(path):
    if not Path(path).is_file():return None
    template=BASE/'templates/connector/shouhan_12502_12p.json'
    if not template.is_file():return None
    spec=json.loads(template.read_text(encoding='utf8'))
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=spec['source_pdf_sha256']:return None
    pins=[dict(id=str(i),name=str(i),type='PASS',part='A',side='',group='',page=1,source=str(Path(path).resolve()),raw=f'12502 SERIES 1.25mm-12P LT; 12P dimension row; pin {i} numbering is a provisional top-view convention, not marked in drawing',confidence=.9,conflicts=[]) for i in range(1,13)]
    return dict(pins=pins,pcb=dict(spec=spec,confirmed=False,needs=list(spec['unresolved']),sources=spec['sources'],notes=spec['notes']))
