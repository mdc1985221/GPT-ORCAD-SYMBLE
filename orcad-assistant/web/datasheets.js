/* Datasheets stay separate from CAD design downloads. */
const originalLibraryDetail=renderLibraryDetail,originalHistoryDetail=renderHistoryDetail;
renderLibraryDetail=function(){originalLibraryDetail();renderDatasheets(libraryDetail)};
renderHistoryDetail=function(){originalHistoryDetail();renderDatasheets(libraryDetail)};
async function renderDatasheets(item){
 if(!item||!$('library-detail'))return;
 const box=document.createElement('section');box.id='item-datasheets';box.className='datasheet-section';
 box.innerHTML='<h3>规格书</h3><p class="catalog-muted">正在读取归档…</p>';$('library-detail').appendChild(box);
 try{
  const r=await api('/api/library/datasheets?id='+encodeURIComponent(item.id)+'&history='+(item.history?'1':'0'));
  if(libraryDetail?.id!==item.id||!box.isConnected)return;
  box.innerHTML='<h3>规格书</h3>'+r.items.map(d=>`<div class="datasheet-file"><span>${esc(d.name)}<small>${d.pages} 页 · ${d.role==='package'?'补充封装图':'规格书'} · ${d.available?'已归档':'文件缺失'}</small></span><button data-datasheet="${d.sha256}" ${d.available?'':'disabled'}>打开 PDF</button></div>`).join('')+(r.items.length?'':'<p class="catalog-muted">待补规格书。上传该型号的PDF后会独立归档，原文件移动后仍可找到。</p>')+'<button class="quiet" id="datasheet-add">'+(r.items.length?'补充资料':'上传规格书')+'</button>';
  box.querySelectorAll('[data-datasheet]').forEach(b=>b.onclick=()=>openDatasheet(b.dataset.datasheet));
  box.querySelector('#datasheet-add').onclick=()=>{const input=document.createElement('input');input.type='file';input.accept='.pdf';input.onchange=()=>{if(input.files[0])attachDatasheet(item,input.files[0])};input.click()};
 }catch(e){box.textContent=e.message}
}
async function openDatasheet(sha){
 const popup=window.open('about:blank','_blank');
 try{const r=await fetch('/api/library/datasheet?sha='+encodeURIComponent(sha),{headers:{'X-Workspace-Token':TOKEN}});if(!r.ok)throw Error((await r.json()).error||'规格书打开失败');const url=URL.createObjectURL(await r.blob());if(popup)popup.location=url;else{const a=document.createElement('a');a.href=url;a.download='datasheet.pdf';a.click()}setTimeout(()=>URL.revokeObjectURL(url),120000)}catch(e){popup?.close();toast(e.message)}
}
async function attachDatasheet(item,file){
 if(file.size>60*1024*1024){toast('规格书须小于60MB');return}
 const reader=new FileReader();reader.onerror=()=>toast('文件读取失败，请重试');reader.onload=async()=>{
  if(await act({action:'datasheet-attach',id:item.id,history:!!item.history,name:file.name,content:reader.result.split(',')[1]})){
   if(libraryDetail?.id===item.id){$('item-datasheets')?.remove();renderDatasheets(item)}toast('规格书已独立归档')
  }
 };reader.readAsDataURL(file);
}

const pageWithDatasheets=libraryPage;
libraryPage=async function(){await pageWithDatasheets();const bar=document.querySelector('.catalog-bar');if(!bar||document.getElementById('datasheet-backfill'))return;const b=document.createElement('button');b.id='datasheet-backfill';b.textContent='补齐已有规格书';b.onclick=async()=>{b.disabled=true;try{if(await act({action:'datasheet-backfill'})){toast('已按保存的来源归档；缺失资料可在器件详情补充');await loadLibrary()}}finally{b.disabled=false}};bar.appendChild(b)};
