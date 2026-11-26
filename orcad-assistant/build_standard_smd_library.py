"""Rebuild the reviewed surface-mount reference library from matching original PDFs."""
import argparse,json,shutil,uuid
from pathlib import Path
import assistant_core as core
import build_pipeline
import datasheet_archive
import library_manager
import model3d_pipeline
import polygon_native
import standard_smd

def build_library(state,datasheets,devices=None,progress=print):
    state=Path(state).resolve();datasheets=Path(datasheets).resolve()
    recipes=standard_smd.catalog()
    if devices:
        unknown=set(devices)-{r['device'] for r in recipes}
        if unknown:raise ValueError('未知贴片规则：'+','.join(sorted(unknown)))
        recipes=[r for r in recipes if r['device'] in devices]
    library=library_manager.Library(state/'library',state/'output');archive=datasheet_archive.Archive(state/'datasheets')
    env=core.DEFAULT_ENV.copy()
    if (state/'environment.json').is_file():env.update(json.loads((state/'environment.json').read_text(encoding='utf8')))
    result=[]
    for recipe in recipes:
        spec=standard_smd.specification(recipe,datasheets/recipe['source']['file']);p=standard_smd.project(recipe,spec)
        root=state/'output'/('standard-smd-'+recipe['device']+'-'+uuid.uuid4().hex[:8]);root.mkdir(parents=True)
        progress('生成 '+recipe['device'])
        symbol=build_pipeline.build(p,env,root/'symbol',progress)
        pcb=polygon_native.build(spec,root/'pcb',progress,env.get('allegro','D:/tools/pcb/bin/allegro.exe'))
        model=model3d_pipeline.build(spec,{'confirmed':True},root/'model3d',progress)
        report=dict(status='PASS',symbol=symbol['report'],pcb=pcb,limitation='Native readback passed; electrical selection, process presets and target-design acceptance pending')
        olb=Path(symbol['olb']);files=[olb,olb.parent/'project.json',root/'pcb/spec.json']+[root/'pcb/allegro'/n for n in pcb['assets']]
        report['file_hashes']=core.artifact_hashes(root,files);core.atomic_json(root/'verification.json',report)
        generated=dict(directory=str(root),olb=str(olb),pcb_directory=str(root/'pcb'),report=report)
        item=library.add(p,generated,recipe['category']);item=library.with_model(item['id'],model,{'confirmed':True});archive.capture(p)
        result.append(item);progress('已入库 '+item['device'])
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',default=str(Path(__file__).parent/'workspace'))
    parser.add_argument('--datasheets',help='Folder containing the reviewed original PDF filenames')
    parser.add_argument('--device',action='append',help='Repeat for selected recipe names; omit for all22')
    parser.add_argument('--list',action='store_true')
    args=parser.parse_args()
    if args.list:
        for r in standard_smd.catalog():print(r['category'],r['device'],r['source']['url'])
        return
    folder=Path(args.datasheets) if args.datasheets else standard_smd.download_sources(Path(args.state)/'standard-smd-sources')
    build_library(args.state,folder,args.device)

if __name__=='__main__':main()
