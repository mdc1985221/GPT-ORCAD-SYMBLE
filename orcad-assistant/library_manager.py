"""A local catalogue with immutable, verified Cadence design files."""
import copy
import hashlib
import io
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import assistant_core as core
import footprint_pipeline as fp
import model3d_pipeline as model3d

CATEGORIES=[dict(id=k,label=v) for k,v in (
    ('resistor','电阻'),('capacitor','电容'),('inductor','电感'),('diode','二极管'),
    ('transistor','晶体管'),('ic-power','IC / 电源'),('ic-memory','IC / 存储器'),
    ('ic-interface','IC / 接口'),('ic-sensor','IC / 传感器'),('ic-other','IC / 其他'),
    ('connector','连接器'),('connector-dip','连接器 / DIP（单排、双排通孔）'),('crystal','晶振'),('other','其他'))]


def suggest_category(project):
    text=' '.join(str(project.get(k,'')) for k in ('device','description','footprint')).upper()
    rule=project.get('connector_rule') or {}
    if rule.get('mounting')=='PTH' and rule.get('rows') in (1,2):return 'connector-dip'
    if re.search(r'\b(?:GC\d+|SC\d{4}|IMX\d+|OV\d+)|SENSOR|传感',text):return 'ic-sensor'
    if re.search(r'RESISTOR|电阻',text):return 'resistor'
    if re.search(r'CAPACITOR|电容',text):return 'capacitor'
    if re.search(r'INDUCTOR|电感',text):return 'inductor'
    if re.search(r'MOSFET|TRANSISTOR|晶体管|三极管',text):return 'transistor'
    if re.search(r'DIODE|二极管',text):return 'diode'
    if re.search(r'CONNECTOR|连接器',text):return 'connector'
    if re.search(r'CRYSTAL|OSCILLATOR|晶振',text):return 'crystal'
    if re.search(r'EEPROM|FLASH|DDR|SRAM|存储',text):return 'ic-memory'
    if re.search(r'REGULATOR|LDO|BUCK|BOOST|PMIC|电源',text):return 'ic-power'
    if re.search(r'TRANSCEIVER|RS485|RS232|接口',text):return 'ic-interface'
    return 'ic-other' if len(project.get('pins',[]))>3 else 'other'


class Library:
    def __init__(self, root, output_root):
        self.root=Path(root).resolve()
        self.output_root=Path(output_root).resolve()

    def _category(self, category):
        if category not in {c['id'] for c in CATEGORIES}:raise ValueError('请选择有效的器件分类')
        return category

    def _source(self, path):
        p=Path(path).resolve()
        if not p.is_relative_to(self.output_root) or not p.is_file():
            raise ValueError('只能收录本工具已生成的库文件')
        return p

    def _folder(self, item_id):
        if not re.fullmatch(r'[a-f0-9]{24}',str(item_id)):raise ValueError('器件库编号无效')
        matches=list(self.root.glob('*/'+item_id+'/_internal/item.json'))
        if len(matches)!=1:raise ValueError('器件不存在或尚未入库')
        folder=matches[0].parent.parent.resolve()
        if not folder.is_relative_to(self.root):raise ValueError('器件库路径无效')
        return folder

    def _read(self, folder):
        item=json.loads((folder/'_internal/item.json').read_text(encoding='utf8'))
        item['paths']={key:str(folder/relative) if (folder/relative).is_dir() else None
            for key,relative in [('capture','symbol'),('psmpath','pcb/psm'),('padpath','pcb/pad'),('model3d','3d')]}
        item['category_label']=next(c['label'] for c in CATEGORIES if c['id']==item['category'])
        return item

    def list(self):
        result=[]
        for p in self.root.glob('*/*/_internal/item.json'):
            if p.parts[-4].startswith('.'):continue
            result.append(self._read(p.parent.parent))
        return sorted(result,key=lambda i:i['created'],reverse=True)

    def get(self, item_id):return self._read(self._folder(item_id))

    def add(self, project, generated, category=None):
        if (generated.get('report') or {}).get('status')!='PASS':raise ValueError('只有验证通过的结果可以入库')
        report_path=self._source(Path(generated.get('directory',''))/'verification.json')
        report=json.loads(report_path.read_text(encoding='utf8'))
        original=dict(report=report)
        check=dict(generated=original)
        core.invalidate_legacy_pcb(check)
        if original['report']['status']!='PASS':raise ValueError('旧版 PCB 结果需要重新生成后再入库')
        olb=self._source(generated.get('olb',''))
        if olb.suffix.lower()!='.olb':raise ValueError('缺少原理图库 OLB')
        root=report_path.parent
        if report.get('pcb'):
            if not olb.is_relative_to(root/'symbol') or Path(generated.get('pcb_directory','')).resolve()!=root/'pcb':
                raise ValueError('库文件与验证记录不属于同一次构建')
        elif olb.parent!=root:raise ValueError('OLB 与验证记录不属于同一次构建')
        built_project=self._source(olb.parent/'project.json')
        symbol_report=json.loads(self._source(olb.parent/'verification.json').read_text(encoding='utf8'))
        if symbol_report.get('status')!='PASS' or symbol_report!=report.get('symbol',report):
            raise ValueError('原理符号验证记录不一致或未通过')
        snapshot=core.load_project(built_project)
        # The preview must describe the built version, never a later editor draft.
        snapshot.pop('generated',None)
        sections=core.section_layouts(snapshot,core.DEFAULT_ENV)
        category=self._category(category or project.get('library_category') or suggest_category(snapshot))
        files={'symbol/'+olb.name:olb}
        pcb=report.get('pcb')
        if pcb:
            if pcb.get('status')!='PASS' or report.get('symbol',{}).get('status')!='PASS':raise ValueError('PCB 或原理符号验证尚未通过')
            spec=snapshot.get('pcb',{}).get('spec')
            if not spec:raise ValueError('缺少构建时的 PCB 参数')
            import pcb_workflow
            migrated=copy.deepcopy(snapshot);pcb_workflow.enrich_project(migrated)
            if migrated['pcb']['spec']!=spec:raise ValueError('旧版中心坐标需要修正并重新生成')
            spec_path=self._source(Path(generated.get('pcb_directory',''))/'spec.json')
            if json.loads(spec_path.read_text(encoding='utf8'))!=spec:raise ValueError('PCB 参数与构建快照不一致')
            adir=(Path(generated['pcb_directory'])/'allegro').resolve()
            if spec.get('kind')=='polygon_smd':
                wanted={('pcb/pad/' if name.endswith('.pad') else 'pcb/psm/' if name.endswith(('.psm','.ssm')) else 'pcb/source/')+name:name
                        for name in fp.native_asset_names(spec,pcb)}
            else:
                wanted={folder+name:name for folder,name in {'pcb/psm/':str(spec['name'])+'.psm',
                    'pcb/pad/':fp.padstack_name(spec)+'.pad','pcb/source/':str(spec['name'])+'.dra'}.items()}
            for relative,name in wanted.items():
                found=[p for p in adir.iterdir() if p.name.lower()==name.lower()]
                if len(found)!=1:raise ValueError('缺少已验证库文件：'+name)
                files[str(Path(relative).parent.as_posix())+'/'+found[0].name]=self._source(found[0])
            if set(p[0] for _,_,ps in sections for p in ps)!=fp.electrical_ids(spec):
                raise ValueError('原理图与 PCB 脚号不一致')
        payload={n:p.read_bytes() for n,p in files.items()}
        if any(not b for b in payload.values()):raise ValueError('库文件为空，请重新生成')
        verified_hashes=report.get('file_hashes',{})
        check_files=[*files.values(),built_project]
        if pcb:check_files.append(spec_path)
        for file in check_files:
            key=file.relative_to(root).as_posix()
            if key not in verified_hashes:raise ValueError('旧结果缺少构建时文件校验记录，请重新生成后入库')
            if hashlib.sha256(file.read_bytes()).hexdigest()!=verified_hashes[key]:
                raise ValueError('生成文件在验证后被修改，请重新生成后入库')
        if pcb:fp.verify(spec_path.parent)
        digest=hashlib.sha256()
        for n,b in sorted(payload.items()):digest.update(n.encode()+b'\0'+b)
        digest.update(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode())
        item_id=digest.hexdigest()[:24]
        for item in self.list():
            if item['id']==item_id:return item
        folder=self.root/category/item_id
        staging=self.root/('.staging-'+uuid.uuid4().hex)
        try:
            for n,b in payload.items():
                target=staging/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
            info=dict(id=item_id,device=snapshot['device'],footprint=snapshot['footprint'],category=category,
                pins=len(snapshot['pins']),parts=len(sections),pcb=bool(pcb),model3d_status='pending',
                created=datetime.now(timezone.utc).isoformat(),status='PASS',
                files=[dict(path=n,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b)) for n,b in sorted(payload.items())])
            core.atomic_json(staging/'_internal/project.json',snapshot)
            core.atomic_json(staging/'_internal/verification.json',report)
            core.atomic_json(staging/'_internal/item.json',info)
            folder.parent.mkdir(parents=True,exist_ok=True)
            staging.rename(folder)
        finally:
            if staging.exists():shutil.rmtree(staging)
        return self._read(folder)

    def classify(self, item_id, category):
        category=self._category(category);folder=self._folder(item_id)
        item=json.loads((folder/'_internal/item.json').read_text(encoding='utf8'))
        if item['category']!=category:
            destination=self.root/category/item_id;destination.parent.mkdir(parents=True,exist_ok=True)
            folder.rename(destination);folder=destination
            item['category']=category;core.atomic_json(folder/'_internal/item.json',item)
        return self._read(folder)

    def with_model(self, item_id, generated, options):
        """Create a new version; attaching a STEP never alters existing versions."""
        old=self._folder(item_id);project=self.project(item_id)
        spec=(project.get('pcb') or {}).get('spec')
        if not spec:raise ValueError('这个版本尚无 CSP/BGA 机械参数，请先载入编辑补齐')
        output=self._source(Path(generated['directory'])/'model3d.json').parent
        report=model3d.verify(output,model3d.plan(spec,options))
        # Check the existing design files before copying, too.
        self.design_bytes(item_id,True)
        item=self.get(item_id)
        new_id=model3d.fingerprint(dict(base=item_id,plan=report['plan'],files=report['file_hashes']))[:24]
        if any(i['id']==new_id for i in self.list()):return self.get(new_id)
        stage=self.root/('.staging-'+uuid.uuid4().hex)
        try:
            shutil.copytree(old,stage)
            (stage/'3d').mkdir(exist_ok=True)
            item['files']=[f for f in item['files'] if not f['path'].startswith('3d/')]
            target=stage/'3d'/report['step'];shutil.copyfile(output/report['step'],target)
            item['files'].append(dict(path='3d/'+report['step'],sha256=report['file_hashes'][report['step']],bytes=target.stat().st_size))
            for file in ('model3d.json','mesh.json'):shutil.copyfile(output/file,stage/'_internal'/file)
            project['model3d']=dict(options,enabled=True)
            core.atomic_json(stage/'_internal/project.json',project)
            item.update(id=new_id,model3d_status='generated',created=datetime.now(timezone.utc).isoformat())
            item.pop('paths',None);item.pop('category_label',None)
            core.atomic_json(stage/'_internal/item.json',item)
            stage.rename(self.root/item['category']/new_id)
        finally:
            if stage.exists():shutil.rmtree(stage)
        return self.get(new_id)

    def model_mesh(self, item_id):
        folder=self._folder(item_id);report=json.loads((folder/'_internal/model3d.json').read_text(encoding='utf8'))
        raw=(folder/'_internal/mesh.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=report['file_hashes']['mesh.json']:raise ValueError('3D 预览文件已被修改')
        return json.loads(raw)

    def project(self, item_id):return core.load_project(self._folder(item_id)/'_internal/project.json')

    def detail(self, item_id):
        item=self.get(item_id);p=self.project(item_id)
        item['sections']=[dict(part=part,width=cfg['W'],height=cfg['H'],pins=pins)
            for part,cfg,pins in core.section_layouts(p,core.DEFAULT_ENV)]
        spec=(p.get('pcb') or {}).get('spec')
        item['pcb_spec']=spec
        item['pads']=fp.geometry(spec) if spec else []
        item['presentation']=fp.presentation(spec) if spec else None
        if item.get('model3d_status')=='generated':
            item['model3d']=json.loads((self._folder(item_id)/'_internal/model3d.json').read_text(encoding='utf8'))
        return item

    def design_bytes(self, item_id, include_source=False):
        item=self.get(item_id);folder=self._folder(item_id);buf=io.BytesIO()
        with ZipFile(buf,'w',ZIP_DEFLATED) as archive:
            for record in item['files']:
                relative=record['path'];file=(folder/relative).resolve()
                if not file.is_relative_to(folder) or file.suffix.lower() not in ('.olb','.psm','.pad','.ssm','.dra','.step'):
                    raise ValueError('库文件路径无效')
                if file.suffix.lower()=='.dra' and not include_source:continue
                raw=file.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('库文件已被外部修改，请重新入库')
                archive.writestr(relative,raw)
        return buf.getvalue()

    def scan_history(self):
        added=0;skipped=0;before={i['id'] for i in self.list()}
        # Joint results are authoritative; do not also collect their symbol sub-builds.
        for record in self.output_root.glob('*/verification.json'):
            if record.parent.name.startswith('.'):continue
            try:
                report=json.loads(record.read_text(encoding='utf8'));root=record.parent
                if 'pcb' in report:
                    projects=list((root/'symbol').glob('*/project.json'))
                    if len(projects)!=1:raise ValueError('构建记录不完整')
                    project=core.load_project(projects[0]);olbs=list(projects[0].parent.glob('*.OLB'))
                    if len(olbs)!=1:raise ValueError('缺少 OLB')
                    g=dict(olb=str(olbs[0]),directory=str(root),pcb_directory=str(root/'pcb'),report=report)
                else:
                    project=core.load_project(root/'project.json');olbs=list(root.glob('*.OLB'))
                    if len(olbs)!=1:raise ValueError('缺少 OLB')
                    g=dict(olb=str(olbs[0]),directory=str(root),report=report)
                item=self.add(project,g)
                if (root/'model3d/model3d.json').is_file():
                    item=self.with_model(item['id'],dict(directory=str(root/'model3d')),project.get('model3d') or {})
                if item['id'] not in before:added+=1;before.add(item['id'])
            except (ValueError,KeyError,OSError,TypeError):skipped+=1
        return dict(added=added,skipped=skipped)
