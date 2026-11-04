"""GC4693 review generator; supersedes the early positive-X trial."""
import json
from datetime import datetime
from footprint_pipeline import prepare, TEMPLATES, BASE

if __name__ == '__main__':
    spec=json.loads((TEMPLATES/'gc4693.json').read_text(encoding='utf-8'))
    output=BASE/'footprint-validation'/('GC4693-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    print(prepare(spec,output))
