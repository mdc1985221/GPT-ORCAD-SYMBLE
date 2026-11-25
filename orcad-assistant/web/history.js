/* Read-only discovery; historical files never acquire verified-library status. */
let historyData=null,historyTerm='',historyCategory='',historyKind='',historySource='',historySelected=null,historyRequest=0;
const verifiedLibraryPage=libraryPage;
libraryPage=async function(){document.body.dataset.catalog='library';await verifiedLibraryPage();document.querySelector('.catalog-bar .spacer')?.insertAdjacentHTML('afterend','<button onclick="historyPage()">历史封装检索</button>')};
async function historyPage(refresh=false){
 document.body.dataset.catalog='history';document.body.classList.add('library-mode');location.hash='history';$('nav-library').classList.add('active');$('nav-editor').classList.remove('active');
 $('catalog').innerHTML=`<div class="catalog-bar"><h1>历史封装检索</h1><p>查找以前生成的器件 · 保留原文件 · 不自动入库</p><span class="spacer"></span><button onclick="libraryPage()">已入库器件</button><button onclick="historyPage(true)">刷新历史索引</button><button onclick="editorPage()">返回编辑</button></div><div class="catalog-toolbar"><span>检索范围：当前工作区、旧 EXE 输出、历史验证样例</span><span class="catalog-muted">G盘公司原库不在自动扫描范围内。</span></div><div class="catalog-grid"><aside class="catalog-categories" id="history-categories"></aside><section class="catalog-items"><input class="catalog-search" id="history-search" placeholder="型号 / 封装 / 分类 / PIN数，多词检索" value="${esc(historyTerm)}"><div class="history-filters"><select id="history-kind"><option value="">全部文件</option><option value="symbol">有原理符号</option><option value="pcb">有PCB封装</option><option value="3d">有3D文件</option></select><select id="history-source"><option value="">全部来源</option></select></div><div class="catalog-muted" id="history-count">正在检索历史文件…</div><div id="history-list"></div></section><section class="catalog-detail" id="library-detail"><div class="catalog-empty">选择历史器件，查看预览及原文件路径。</div></section></div>`;
 const request=++historyRequest;
 try{
  historyData=await api('/api/library/history'+(refresh?'?refresh=1':''));if(request!==historyRequest||!$('history-list'))return;
  $('history-source').innerHTML='<option value="">全部来源</option>'+[...new Set(historyData.items.map(i=>i.source))].map(s=>`<option>${esc(s)}</option>`).join('');
  $('history-kind').value=historyKind;$('history-source').value=historySource;
  $('history-search').oninput=e=>{historyTerm=e.target.value;renderHistoryList()};
  $('history-kind').onchange=e=>{historyKind=e.target.value;renderHistoryList()};$('history-source').onchange=e=>{historySource=e.target.value;renderHistoryList()};
  renderHistoryList();if(historySelected&&historyData.items.some(i=>i.id===historySelected))await selectHistory(historySelected);
 }catch(e){if($('history-list'))$('history-list').textContent=e.message}
}
function renderHistoryList(){
 if(!historyData||!$('history-list'))return;
 $('history-categories').innerHTML=[{id:'',label:'全部分类'},...historyData.categories].map(c=>`<button data-category="${c.id}" class="${historyCategory===c.id?'selected':''}">${esc(c.label)}<small>${historyData.items.filter(i=>!c.id||i.category===c.id).length}</small></button>`).join('');
 $('history-categories').querySelectorAll('button').forEach(b=>b.onclick=()=>{historyCategory=b.dataset.category;renderHistoryList()});
 const terms=historyTerm.trim().toLowerCase().split(/\s+/).filter(Boolean);
 const items=historyData.items.filter(i=>{const text=`${i.device} ${i.footprint} ${i.category_label} ${i.pins} PIN ${i.source} ${i.source_path}`.toLowerCase();return (!historyCategory||i.category===historyCategory)&&(!historySource||i.source===historySource)&&(!historyKind||(historyKind==='3d'?i.model3d_status!=='pending':historyKind==='symbol'?i.symbol:i.pcb))&&terms.every(t=>text.includes(t))});
 $('history-count').textContent=`找到 ${items.length} / ${historyData.items.length} 条历史记录 · 历史版本需复核`;
 $('history-list').innerHTML=items.map(i=>`<article class="catalog-card ${historySelected===i.id?'selected':''}" data-history-id="${i.id}"><h3>${esc(i.device)}</h3><p>${esc(i.footprint)} · ${i.pins||'—'} PIN</p><div class="catalog-tags">${i.symbol?'<span class="catalog-tag">OLB 文件</span>':''}${i.pcb?'<span class="catalog-tag">PCB 文件</span>':''}${i.model3d_status!=='pending'?'<span class="catalog-tag">3D 文件</span>':''}<span class="catalog-tag pending">历史待复核</span></div><div class="catalog-muted">${esc(i.category_label)} · ${esc(i.source)} · ${new Date(i.created).toLocaleDateString()}</div></article>`).join('')||'<div class="catalog-empty">没有匹配的历史封装，请更换关键词或筛选条件。</div>';
 $('history-list').querySelectorAll('[data-history-id]').forEach(b=>b.onclick=()=>selectHistory(b.dataset.historyId));
}
async function selectHistory(id){
 const request=++libraryFetch;historySelected=id;renderHistoryList();
 try{const i=await api('/api/library/history/item?id='+encodeURIComponent(id));if(request!==libraryFetch||!$('history-list'))return;libraryDetail=i;libraryPart=i.sections[0]?.part||'A';if(!i.sections.length&&libraryPreview==='symbol')libraryPreview=i.pcb?'pcb':i.model3d_status==='generated'?'3d':'symbol';renderHistoryDetail()}catch(e){toast(e.message)}
}
function renderHistoryDetail(){
 const i=libraryDetail;if(!i?.history)return;$('library-preview')?._disposeModel?.();
 const pathRow=(k,label)=>`<div class="catalog-path"><label>${label}</label><code>${esc(i.paths[k]||'没有此文件')}</code><button data-history-copy="${k}" ${i.paths[k]?'':'disabled'}>复制路径</button></div>`;
 $('library-detail').innerHTML=`<h2>${esc(i.device)}</h2><div class="catalog-muted">${esc(i.category_label)} · ${esc(i.footprint)}</div><p class="history-notice">历史文件 · 待复核。预览来自保存的布局参数或3D网格，不代表本次已重新验收。</p><div class="catalog-tabs">${[['symbol','原理符号'],['pcb','PCB封装'],['3d','3D模型']].map(([k,n])=>`<button data-history-view="${k}" class="${libraryPreview===k?'selected':''}">${n}</button>`).join('')}<button onclick="renderLibraryPreview()">适应</button></div><div id="library-part-box"></div><div class="catalog-preview" id="library-preview"></div><div class="catalog-muted">2D滚轮缩放 / 右键平移 · 3D拖动旋转 / 滚轮缩放</div><p class="catalog-muted">来源：${esc(i.source)}<br>${esc(i.source_path)}</p><div class="catalog-actions"><button class="primary" id="history-download">下载历史库文件</button><button id="history-copy-root">复制原文件夹路径</button></div><label class="catalog-dra"><input type="checkbox" id="history-dra">包含可编辑DRA</label>${pathRow('capture','Capture 原理图库')}${pathRow('psmpath','Allegro · psmpath')}${pathRow('padpath','Allegro · padpath')}${pathRow('model3d','3D 模型目录')}<details><summary>查看历史文件清单</summary>${i.files.map(f=>`<div class="catalog-file">${esc(f.path)}</div>`).join('')}</details>`;
 $('library-detail').querySelectorAll('[data-history-view]').forEach(b=>b.onclick=()=>{libraryPreview=b.dataset.historyView;renderHistoryDetail()});
 const expand=document.createElement('button');expand.textContent='放大预览';expand.onclick=toggleLibraryPreviewSize;$('library-detail').querySelector('.catalog-tabs').appendChild(expand);
 $('library-detail').querySelectorAll('[data-history-copy]').forEach(b=>b.onclick=()=>copyLibraryText(i.paths[b.dataset.historyCopy]));
 $('history-copy-root').onclick=()=>copyLibraryText(i.source_path);
 $('history-download').onclick=()=>downloadCadence('/api/library/history/download?id='+encodeURIComponent(i.id)+'&source='+($('history-dra').checked?'1':'0'),i.device+'-history-review.zip');
 if(libraryPreview==='3d'&&i.model3d_status!=='generated'){$('library-preview').innerHTML='<div class="catalog-empty">没有已保存的3D预览网格；已有STEP文件可下载后用3D软件打开。</div>';return}
 renderLibraryPreview();
}
function toggleLibraryPreviewSize(){
 const box=$('library-preview');if(!box)return;
 const expanded=box.classList.toggle('expanded-preview');
 let close=box.querySelector('.preview-close');
 if(expanded&&!close){close=document.createElement('button');close.className='preview-close';close.textContent='收起 · Esc';close.onclick=toggleLibraryPreviewSize;box.appendChild(close)}else close?.remove();
}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('library-preview')?.classList.contains('expanded-preview'))toggleLibraryPreviewSize()});
