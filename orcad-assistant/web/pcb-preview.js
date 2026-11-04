/* Physical millimetre dimensions come from the same settings as the native export. */
const pcbLayers = {pins:true, refs:true, centers:true, bound:true};
let pcbPan = {x:0,y:0};

function drawPCB() {
  const target=$('pcb-preview'), s=state?.project.pcb?.spec, pads=state?.pcb_preview, style=state?.pcb_presentation;
  if(!target)return;
  if($('pcb').style.display==='block')$('zoom').textContent=Math.round(pcbZoom*100)+'%';
  if(!s||!pads?.length||!style){target.innerHTML='<div class="pcb-placeholder">补齐尺寸后，自动显示 PCB 焊盘布局</div>';return;}
  const [w,h]=s.body, hx=w/2, hy=h/2, pin=style.pin, center=style.center;
  const vw=(w+9)/pcbZoom, vh=(h+3.4)/pcbZoom, cx=pcbPan.x, cy=pcbPan.y;
  const bound=pcbLayers.bound?`<rect data-feature="place-bound" x="${-style.place_bound.width/2}" y="${-style.place_bound.height/2}" width="${style.place_bound.width}" height="${style.place_bound.height}" fill="#7a8cf40b" stroke="#7888c8" stroke-width=".018" stroke-dasharray=".09 .06"/><text data-feature="height" x="${-hx}" y="${hy+.47}" font-size=".17" fill="#6b77a7">PLACE BOUND · Z max ${s.height_max==null?'待填写':esc(s.height_max)+' mm'}</text>`:'';
  const padMarkup=pads.map(([id,x,y])=>`<g data-pad="${esc(id)}"><circle cx="${x}" cy="${-y}" r="${(s.pad_dia+2*s.mask_margin)/2}" fill="none" stroke="#6ca88e" stroke-width=".012"/><circle cx="${x}" cy="${-y}" r="${s.pad_dia/2}" fill="${id==='A1'?'#d88e44':'#6687c8'}"/>${pcbLayers.pins?`<text data-feature="pin-number" x="${x}" y="${-y}" text-anchor="middle" dominant-baseline="central" font-family="Consolas,monospace" font-size="${pin.height}" textLength="${id.length*pin.width+(id.length-1)*pin.char_space}" lengthAdjust="spacingAndGlyphs" fill="white">${esc(id)}</text>`:''}</g>`).join('');
  const refMarkup=pcbLayers.refs?[-hy-.82,hy+1.02].map((y,i)=>`<path data-feature="refdes" data-stroke-mm="${style.ref.stroke}" aria-label="#REFDES" transform="translate(0 ${y})" d="${style.ref.svg_path}" fill="none" stroke="${i?'#b579a2':'#a28bba'}" stroke-width="${style.ref.stroke}" stroke-linecap="round" stroke-linejoin="round"/>`).join(''):'';
  let centers='';
  if(pcbLayers.centers){
    centers=style.annotations.map(mark=>{
      const [x,y]=mark.point,[lx,ly]=mark.label,r=mark.name==='BODY'?center.body_radius:center.radius;
      return `<g data-feature="center" data-center="${mark.name}" data-linewidth-mm="0"><path d="M ${x-r} ${-y} H ${x+r} M ${x} ${-y-r} V ${-y+r}" fill="none" stroke="${mark.color}" stroke-width="1" vector-effect="non-scaling-stroke"/><path data-feature="center-leader" d="${mark.segments.map(([[x0,y0],[x1,y1]])=>`M ${x0} ${-y0} L ${x1} ${-y1}`).join(' ')}" fill="none" stroke="${mark.color}" stroke-width="1" vector-effect="non-scaling-stroke"/><text x="${lx}" y="${-ly}" text-anchor="${mark.justify==='right'?'end':'start'}" font-size="${center.text_height}" font-family="Consolas,monospace" fill="${mark.color}">${esc(mark.text)}</text></g>`;
    }).join('');
  }
  target.innerHTML=`<svg id="pcb-svg" xmlns="http://www.w3.org/2000/svg" viewBox="${cx-vw/2} ${cy-vh/2} ${vw} ${vh}" aria-label="PCB 封装顶视图，含脚号、REF、中心和高度边界">${bound}<rect x="${-hx}" y="${-hy}" width="${w}" height="${h}" fill="white" fill-opacity=".75" stroke="#8393ab" stroke-width=".05"/>${padMarkup}<path d="M ${-hx+.4} ${-hy} L ${-hx} ${-hy+.4}" stroke="#d88e44" stroke-width=".045"/>${centers}${refMarkup}</svg>`;
}

function bindPCBPreview(){
  const target=$('pcb-preview');
  target.oncontextmenu=e=>e.preventDefault();
  target.onwheel=e=>{e.preventDefault();pcbZoom=Math.max(.5,Math.min(12,pcbZoom*(e.deltaY<0?1.15:1/1.15)));drawPCB();};
  let moving=null;
  target.onpointerdown=e=>{if(e.button!==2&&e.button!==1)return;e.preventDefault();moving={x:e.clientX,y:e.clientY,pan:{...pcbPan}};target.setPointerCapture(e.pointerId);};
  target.onpointermove=e=>{if(!moving)return;const svg=$('pcb-svg'),matrix=svg.getScreenCTM().inverse();const a=new DOMPoint(moving.x,moving.y).matrixTransform(matrix),b=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix);pcbPan={x:moving.pan.x+a.x-b.x,y:moving.pan.y+a.y-b.y};drawPCB();};
  target.onpointerup=target.onpointercancel=()=>{moving=null;};
}

function renderProgress(){
  const job=state.job, container=$('task-progress'),bar=$('task-progress-bar');
  container.classList.toggle('running',!!job.busy);
  container.classList.toggle('failed',!!job.error);
  bar.style.width=job.busy?'35%':job.error?'100%':`${job.progress||0}%`;
  container.setAttribute('aria-valuetext',job.error?'操作未完成':job.message);
  if(job.busy)container.removeAttribute('aria-valuenow');else container.setAttribute('aria-valuenow',job.error?'0':String(job.progress||0));
  $('task-progress-label').textContent=job.error?'操作未完成，请查看错误信息':job.message;
  $('task-progress-value').textContent=job.busy?'进行中':job.error?'未完成':job.progress===100?'100%':state.project.pins.length?'待生成':'就绪';
}
