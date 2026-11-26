/* The catalogue previews saved builds; editor drafts remain independent. */
let libraryData=null,librarySelected=null,libraryDetail=null,libraryCategory='',librarySearch='',libraryPreview='symbol',libraryPart='A';
let libraryFetch=0;
function libraryOptions(value){return (state?.library_categories||[]).map(c=>`<option value="${c.id}" ${c.id===value?'selected':''}>${esc(c.label)}</option>`).join('')}
async function libraryPage(){
 document.body.classList.add('library-mode');location.hash='library';$('nav-library').classList.add('active');$('nav-editor').classList.remove('active');
 $('catalog').innerHTML=`<div class="catalog-bar"><h1>器件库</h1><p>分类保存 · 预览已生成版本 · 直接用于 Cadence</p><span class="spacer"></span><button onclick="editorPage()">返回编辑</button><button onclick="scanLibrary()">收录历史结果</button></div><div class="catalog-toolbar"><span>当前器件入库分类</span><select id="library-build-category" onchange="act({action:'library-category',category:this.value})">${libraryOptions(state?.project.library_category||state?.library_suggestion||'other')}</select><button id="library-add-current" onclick="addCurrentLibrary()">收录当前结果</button><span class="catalog-muted">验证通过后自动入库，分类可修改</span></div><div class="catalog-grid"><aside class="catalog-categories" id="library-categories"></aside><section class="catalog-items"><input class="catalog-search" id="library-search" placeholder="搜索器件、封装…" value="${esc(librarySearch)}" oninput="librarySearch=this.value;renderLibraryList()"><div id="library-list"></div></section><section class="catalog-detail" id="library-detail"><div class="catalog-empty">选择器件，查看符号、PCB 和库路径</div></section></div>`;
 $('library-add-current').disabled=!state?.project.generated?.olb||state.job.busy;
 await loadLibrary();
}
function editorPage(hash=''){document.body.classList.remove('library-mode');$('nav-library').classList.remove('active');$('nav-editor').classList.add('active');location.hash=hash;if(hash==='#pcb')pcbTab();else tab(false)}
async function loadLibrary(){try{libraryData=await api('/api/library');if($('library-add-current'))$('library-add-current').disabled=!state?.project.generated?.olb||state.job.busy;if($('library-build-category')&&document.activeElement!==$('library-build-category'))$('library-build-category').value=state.project.library_category||state.library_suggestion;renderLibraryList();if(librarySelected&&libraryData.items.some(i=>i.id===librarySelected))await selectLibrary(librarySelected);else if(libraryData.items.length)await selectLibrary(libraryData.items[0].id);else $('library-detail').innerHTML='<div class="catalog-empty"><strong>还没有收录器件</strong>生成并验证后会自动入库。<br>已有生成记录可点击“收录历史结果”。</div>'}catch(e){toast(e.message)}}
function renderLibraryList(){
 if(!libraryData||!$('library-list'))return;
 const count=id=>libraryData.items.filter(i=>!id||i.category===id).length;
 $('library-categories').innerHTML=[{id:'',label:'全部器件'},...libraryData.categories].map(c=>`<button class="${libraryCategory===c.id?'selected':''}" data-library-category="${c.id}">${esc(c.label)}<small>${count(c.id)}</small></button>`).join('');
 $('library-categories').querySelectorAll('button').forEach(b=>b.onclick=()=>{libraryCategory=b.dataset.libraryCategory;renderLibraryList()});
 const term=librarySearch.trim().toLowerCase(),items=libraryData.items.filter(i=>(!libraryCategory||i.category===libraryCategory)&&`${i.device} ${i.footprint}`.toLowerCase().includes(term));
 $('library-list').innerHTML=items.map(i=>`<article class="catalog-card ${librarySelected===i.id?'selected':''}" data-library-item="${i.id}"><h3>${esc(i.device)}</h3><p>${esc(i.footprint)} · ${i.pins} PIN · ${i.parts} PART</p><div class="catalog-tags">${i.datasheets?.some(d=>d.available)?'<span class="catalog-tag">规格书 ✓</span>':'<span class="catalog-tag pending">待补规格书</span>'}<span class="catalog-tag">OLB ✓</span>${i.pcb?'<span class="catalog-tag">PCB ✓</span>':'<span class="catalog-tag pending">PCB 待生成</span>'}${i.model3d_status==='generated'?'<span class="catalog-tag">3D ✓</span>':'<span class="catalog-tag pending">3D 待生成</span>'}</div><div class="catalog-muted">${esc(i.category_label)} · ${new Date(i.created).toLocaleDateString()} · ${i.id.slice(0,6)}</div></article>`).join('')||'<div class="catalog-empty">没有符合条件的器件</div>';
 $('library-list').querySelectorAll('[data-library-item]').forEach(c=>c.onclick=()=>selectLibrary(c.dataset.libraryItem));
}
async function selectLibrary(id){
 const request=++libraryFetch;librarySelected=id;renderLibraryList();
 try{const item=await api('/api/library/item?id='+encodeURIComponent(id));if(request!==libraryFetch)return;libraryDetail=item;libraryPart=item.sections[0]?.part||'A';renderLibraryDetail()}catch(e){toast(e.message)}
}
function renderLibraryDetail(){
 const i=libraryDetail;if(!i)return;
 $('library-preview')?._disposeModel?.();
 const pathRow=(key,label)=>`<div class="catalog-path"><label>${label}</label><code>${esc(i.paths[key]||'待添加')}</code><button data-copy-path="${key}" ${i.paths[key]?'':'disabled'}>复制路径</button></div>`;
 $('library-detail').innerHTML=`<h2>${esc(i.device)}</h2><div class="catalog-muted">${esc(i.footprint)} · ${i.pins} PIN · ${i.parts} PART · 版本 ${i.id.slice(0,8)}</div><select class="catalog-classify" id="library-category">${libraryOptions(i.category)}</select><div class="catalog-muted">更改分类后，库目录会更新，请重新复制路径。</div><div class="catalog-tabs">${[['symbol','原理符号'],['pcb','PCB 封装'],['3d','3D 模型']].map(([key,label])=>`<button data-library-preview="${key}" class="${libraryPreview===key?'selected':''}">${label}</button>`).join('')}<button style="margin-left:auto" onclick="renderLibraryPreview()">适应</button></div><div id="library-part-box"></div><div class="catalog-preview" id="library-preview"></div><div class="catalog-muted">已保存版本预览 · 2D 滚轮缩放 / 右键平移 · 3D 拖动旋转</div><div class="catalog-actions"><button class="primary" id="library-download">下载设计用库</button><button id="library-open">载入编辑</button></div><label class="catalog-dra"><input type="checkbox" id="library-include-dra">同时下载可编辑 DRA 源封装</label>${pathRow('capture','Capture 原理图库目录')}${pathRow('psmpath','Allegro · psmpath')}${pathRow('padpath','Allegro · padpath')}${pathRow('model3d','3D 模型目录')}<div class="catalog-actions"><button id="library-copy-pcb" ${i.pcb?'':'disabled'}>复制 PCB 两项路径</button><button id="library-copy-olb">复制 OLB 文件路径</button></div><div class="catalog-muted">Capture：Place Part → Add Library，选择 OLB 文件。<br>Allegro：User Preferences → Paths → Library，分别添加 psmpath / padpath。<br>同名封装的不同版本，请使用所选版本路径，避免同时加入冲突版本。</div><details><summary>库文件清单（不含日志和报告）</summary>${i.files.map(f=>`<div class="catalog-file">${esc(f.path)}</div>`).join('')}</details>`;
 $('library-category').onchange=async e=>{if(await act({action:'library-classify',id:i.id,category:e.target.value}))await loadLibrary()};
 if(i.manufacturer||i.review_notes?.length){const note=document.createElement('p');note.className='history-notice';note.textContent=[i.manufacturer?'厂家：'+i.manufacturer:'',...(i.review_notes||[])].filter(Boolean).join(' · ');$('library-detail').querySelector('h2').after(note)}
 $('library-detail').querySelectorAll('[data-library-preview]').forEach(b=>b.onclick=()=>{libraryPreview=b.dataset.libraryPreview;renderLibraryDetail()});
 $('library-detail').querySelectorAll('[data-copy-path]').forEach(b=>b.onclick=()=>copyLibraryText(i.paths[b.dataset.copyPath]));
 $('library-copy-pcb').onclick=()=>copyLibraryText(`psmpath: ${i.paths.psmpath}\npadpath: ${i.paths.padpath}`);
 $('library-copy-olb').onclick=()=>copyLibraryText(i.paths.capture+pathSeparator(i.paths.capture)+i.files.find(f=>f.path.toLowerCase().endsWith('.olb')).path.split('/').pop());
 $('library-download').onclick=()=>downloadLibrary(i.id,$('library-include-dra').checked);
 $('library-open').onclick=async()=>{if(state.job.busy){toast('请等待当前生成任务完成');return}if(!confirm('载入这个已保存版本进行编辑？当前项目可通过“撤销”恢复。'))return;if($('pcb').dataset.dirty==='true'&&!await savePCB(false))return;if(await act({action:'library-open',id:i.id})){$('pcb').dataset.dirty='false';editorPage();fit();render();tab(false)}};
 $('library-detail').scrollTop=0;
 renderLibraryPreview();
}
function pathSeparator(path){return path.includes('\\')?'\\':'/'}
async function copyLibraryText(value){try{await navigator.clipboard.writeText(value);toast('路径已复制')}catch(e){dialog(`<h2>复制库路径</h2><p>请选中下方路径后按 Ctrl+C。</p><textarea readonly style="width:100%;height:100px">${esc(value)}</textarea><div class="actions"><button onclick="closeDialog()">关闭</button></div>`);$('dialog').querySelector('textarea').select()}}
function renderLibraryPreview(){
 const i=libraryDetail,t=$('library-preview');if(!i||!t)return;t._disposeModel?.();
 t.onpointerdown=t.onpointermove=t.onpointerup=t.onpointercancel=t.onwheel=null;
 $('library-part-box').innerHTML=libraryPreview==='symbol'&&i.sections.length>1?`<select class="catalog-classify" id="library-part">${i.sections.map(s=>`<option ${libraryPart===s.part?'selected':''}>${esc(s.part)}</option>`).join('')}</select>`:'';
 if($('library-part'))$('library-part').onchange=e=>{libraryPart=e.target.value;renderLibraryPreview()};
 if(libraryPreview==='3d'){if(i.model3d_status==='generated'){libraryModelPreview(t,i)}else{t.innerHTML=`<div class="catalog-empty"><strong>3D 模型待生成</strong>根据已保存的机械尺寸生成简化 STEP。<br><button onclick="model3dDialog(libraryDetail.id)" ${i.pcb_spec?'':'disabled'}>生成 3D 模型</button><br>缺失高度需确认；不包含镜头与盖板细节。</div>`}return}
 if(libraryPreview==='pcb'&&!i.pcb){t.innerHTML='<div class="catalog-empty"><strong>此版本仅有原理符号</strong>载入编辑、补齐 PCB 参数后联合生成即可。</div>';return}
 let box,markup='';
 if(libraryPreview==='symbol'){
  const s=i.sections.find(s=>s.part===libraryPart)||i.sections[0];if(!s){t.innerHTML='<div class="catalog-empty">这个历史版本没有可用的原理符号布局参数。</div>';return}box=[-70,-70,s.width+140,s.height+140];
  const graphic=i.symbol_graphics;
  markup=graphic?.frame_visible===false?'':`<rect width="${s.width}" height="${s.height}" fill="white" stroke="#98a8c5"/>`;
  if(graphic?.segments)markup+=graphic.segments.map(([x,y,a,b])=>`<line x1="${x}" y1="${y}" x2="${a}" y2="${b}" stroke="#344862" stroke-width="1.5"/>`).join('');
  for(let [id,name,type,x,y,hx,hy] of s.pins){const vertical=x===hx,tx=x===0?x+7:x===s.width?x-7:x,ty=y===0?y+8:y===s.height?y-8:y+2,anchor=x===s.width||y===0?'end':'start';markup+=`<g><line x1="${x}" y1="${y}" x2="${hx}" y2="${hy}" stroke="#6479d8"/><text x="${tx}" y="${ty}" ${vertical?`transform="rotate(-90 ${tx} ${ty})"`:''} text-anchor="${anchor}" font-size="7" fill="#52637c">${esc(name)}</text><text x="${vertical?x-3:(x+hx)/2}" y="${vertical?(y+hy)/2:y-4}" font-size="5" fill="#8a97ad">${esc(id)}</text></g>`}
  markup+=`<text x="${graphic?0:s.width/2}" y="${graphic?-40:s.height/2}" text-anchor="middle" font-size="12" fill="#52637c">${esc(i.device)}</text>`;
 }else{
  if(!i.pcb_spec||!i.presentation){t.innerHTML='<div class="catalog-empty">封装文件仍可检索下载，但缺少可用的预览参数。原生封装请用 Allegro 打开复核。</div>';return}
  const s=i.pcb_spec,[w,h]=s.body;box=[-w/2-4,-h/2-2,w+8,h+4];markup=`<rect x="${-w/2}" y="${-h/2}" width="${w}" height="${h}" fill="white" stroke="#98a8c5" stroke-width=".035"/>`;
  if(i.presentation.kind==='polygon_smd'){t.innerHTML=i.presentation.svg;bindPolygonLibrary(t);return}
  markup+=i.pads.map(([id,x,y])=>`<g data-library-pad="${esc(id)}"><circle cx="${x}" cy="${-y}" r="${s.pad_dia/2}" fill="#6687c8"/><text x="${x}" y="${-y}" dominant-baseline="central" text-anchor="middle" font-size="${i.presentation.pin.height}" fill="white">${esc(id)}</text></g>`).join('');
  for(let mark of i.presentation.annotations)markup+=`<path d="${mark.segments.map(([[x,y],[a,b]])=>`M ${x} ${-y} L ${a} ${-b}`).join(' ')}" stroke="${mark.color}" stroke-width=".015" fill="none"/><text x="${mark.label[0]}" y="${-mark.label[1]}" text-anchor="${mark.justify==='right'?'end':'start'}" font-size=".16" fill="${mark.color}">${esc(mark.text)}</text>`;
 }
 t.innerHTML=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box.join(' ')}">${markup}</svg>`;
 const svg=t.querySelector('svg');let pan=null;const apply=()=>svg.setAttribute('viewBox',box.join(' '));
 t.oncontextmenu=e=>e.preventDefault();t.onwheel=e=>{e.preventDefault();let k=e.deltaY<0?.86:1/.86;if(box[2]*k<.03||box[2]*k>100000)return;box=[box[0]+box[2]*(1-k)/2,box[1]+box[3]*(1-k)/2,box[2]*k,box[3]*k];apply()};
 t.onpointerdown=e=>{if(![1,2].includes(e.button))return;pan={x:e.clientX,y:e.clientY,box:[...box]};t.setPointerCapture(e.pointerId)};
 t.onpointermove=e=>{if(!pan)return;const a=new DOMPoint(pan.x,pan.y).matrixTransform(svg.getScreenCTM().inverse()),b=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());box=[pan.box[0]+a.x-b.x,pan.box[1]+a.y-b.y,box[2],box[3]];apply()};t.onpointerup=t.onpointercancel=()=>pan=null;
}
async function addCurrentLibrary(){if(await act({action:'library-add',category:$('library-build-category').value})){librarySelected=state.project.generated.library_item;await loadLibrary();toast('已收录当前生成版本')}}
async function scanLibrary(){if(state.job.busy){toast('请等待当前生成任务完成');return}if(await act({action:'library-scan'})){await loadLibrary();toast(`历史整理完成：新收录 ${libraryData.scan.added} 个版本；${libraryData.scan.skipped} 条旧版或不完整记录未收录`)}}
async function downloadLibrary(id,source=false){await downloadCadence('/api/library/download?id='+encodeURIComponent(id)+'&source='+(source?'1':'0'),(libraryDetail?.device||'device')+'-cadence-library.zip')}
async function downloadCadence(url,name){try{const r=await fetch(url,{headers:{'X-Workspace-Token':TOKEN}});if(!r.ok){let e=await r.json();throw Error(e.error||'下载未完成')}const a=document.createElement('a');a.href=URL.createObjectURL(await r.blob());a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}catch(e){toast(e.message)}}
function downloadDesignDialog(){dialog(`<h2>下载 Cadence 库</h2><p>设计用文件包含已生成的 OLB、PSM、PAD 和 STEP。未生成的项目不放入下载包。</p><label><input id="download-dra" type="checkbox"> 加入可编辑 DRA 源封装</label><div class="actions">${state.project.generated?.archive?'<button id="download-full">完整工程（含诊断）</button>':''}<button onclick="closeDialog()">取消</button><button class="primary" id="download-design">下载设计用库</button></div>`);$('download-design').onclick=()=>{downloadCadence('/api/download?source='+($('download-dra').checked?'1':'0'),(state.project.device||'device')+'-cadence-library.zip');closeDialog()};if($('download-full'))$('download-full').onclick=()=>{downloadCadence('/api/download?full=1',(state.project.device||'device')+'-full-project.zip');closeDialog()}}
window.addEventListener('hashchange',()=>{if(!state)return;const hash=location.hash;if(hash==='#history'){if(document.body.dataset.catalog!=='history'||!document.body.classList.contains('library-mode'))historyPage()}else if(hash==='#library'){if(document.body.dataset.catalog!=='library'||!document.body.classList.contains('library-mode'))libraryPage()}else if(document.body.classList.contains('library-mode'))editorPage(hash);else if(hash==='#pcb')pcbTab();else tab(false)});

function bindPolygonLibrary(target){
 const svg=target.querySelector('svg');let box=svg.getAttribute('viewBox').split(/\s+/).map(Number),moving=null;
 const apply=()=>svg.setAttribute('viewBox',box.join(' '));
 target.oncontextmenu=e=>e.preventDefault();target.onwheel=e=>{e.preventDefault();let k=e.deltaY<0?.86:1/.86;box=[box[0]+box[2]*(1-k)/2,box[1]+box[3]*(1-k)/2,box[2]*k,box[3]*k];apply()};
 target.onpointerdown=e=>{if(![1,2].includes(e.button))return;moving={x:e.clientX,y:e.clientY,box:[...box]};target.setPointerCapture(e.pointerId)};
 target.onpointermove=e=>{if(!moving)return;const a=new DOMPoint(moving.x,moving.y).matrixTransform(svg.getScreenCTM().inverse()),b=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());box=[moving.box[0]+a.x-b.x,moving.box[1]+a.y-b.y,...moving.box.slice(2)];apply()};
 target.onpointerup=target.onpointercancel=()=>moving=null;
}
