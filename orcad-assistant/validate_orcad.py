"""Run explicit local integration checks against the installed OrCAD 16.6."""
from pathlib import Path
import assistant_core as c
import build_pipeline as b


def main():
    results = []
    for name, footprint, rows in [
        ('GC4693', 'CSP35', c.import_csv(Path(__file__).parent / 'examples/GC4693_ballmap.csv')),
        ('NUMERIC_EP', 'DFN10_EP', [dict(id=str(i), name='IO'+str(i), type='ANA' if i==3 else 'IO', side='', group='', confidence=1., conflicts=[]) for i in range(1,11)] + [dict(id='EP', name='GND', type='GND', side='', group='', confidence=1., conflicts=[])]),
        ('LARGE140', 'QFP140', [dict(id=str(i), name='BUS['+str(i)+']', type='IO', side='', group='', confidence=1., conflicts=[]) for i in range(1,141)])
    ]:
        project = c.new_project()
        project.update(device=name, footprint=footprint, pins=rows, expected_count=len(rows), profile='sensor' if name=='GC4693' else 'simple')
        c.auto_layout(project)
        results.append(b.build(project, c.DEFAULT_ENV, Path(__file__).parent / 'validation-output', print))
    c.atomic_json(Path(__file__).parent / 'validation-output/integration-results.json', results)
    print('All integration checks passed:', [r['report']['pins'] for r in results])


if __name__ == '__main__':
    main()
