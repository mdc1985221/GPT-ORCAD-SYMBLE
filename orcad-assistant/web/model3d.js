/* Local STEP generation; the canvas displays the tessellated saved model. */
document.getElementById('canvas-tab').insertAdjacentHTML('afterend','<button class="tab" id="model3d-editor" onclick="model3dDialog()">3D 模型</button>');
async function model3dDialog(itemId=null){
 if(state.job.busy){toast('请等待当前任务完成');return}
 if(!itemId&&$('pcb').dataset.dirty==='true'){toast('请先保存 PCB 尺寸，再生成 3D');pcbTab();return}
 const detail=itemId?libraryDetail:null,s=detail?detail.pcb_spec||null:state.project.pcb?.spec;
 // Symbol-only saved versions may still contain a mechanical snapshot.
 if(!s){toast('请先载入编辑，补齐 CSP / BGA 机械尺寸');return}
 if(s.family==='connector'){toast('此连接器当前提供符号与PCB；3D需补齐本体相对焊盘位置后建模');return}
 if(s.family==='standard_smd'){standardModelDialog(s,itemId);return}if(s.kind==='polygon_smd'){polygonModelDialog(s,itemId);return}
 const options=detail?(detail.model3d?.plan||{}):(state.project.model3d||{});
 dialog(`<h2>CSP / BGA 简化 3D 模型</h2><p>本体 ${s.body.join(' × ')} mm · 球径 ${s.ball_dia} mm。XY 与 PCB 一致，Z=0 为板面接触点，向上为正。</p><div class="pcb-fields"><div class="field"><label>总高度，包含焊球（mm）</label><input id="model-total" type="number" step="any" value="${esc(options.total_height??s.height_nominal??s.height_max??'')}"></div><div class="field"><label>焊球突出高度（mm）</label><input id="model-ball" type="number" step="any" value="${esc(options.ball_height??s.ball_height??s.ball_dia)}"></div></div><p class="pcb-warning">${s.sensor_array?`将生成感光区域 ${s.sensor_array.join(" × ")} mm、芯片表面、${s.glass_thickness??.4} mm 玻璃及全部焊球。玻璃透明显示；${s.top_to_wafer!=null?`感光面按规格书 C3=${s.top_to_wafer} mm 定位。`:"感光面深度采用外观近似。"}内部支撑结构为简化示意。`:`焊球高度优先取规格书，缺失时暂用球径。生成矩形本体和球冠，不包含玻璃盖板、镜头、倒角及内部结构。`}</p><label class="pcb-check"><input id="model-confirm" type="checkbox"> 我已核对方向及高度，接受此简化模型用于装配参考。</label>${itemId?'':'<label class="pcb-check"><input id="model-enabled" type="checkbox" checked> 后续“符号 + PCB”联合生成时同时生成 STEP</label>'}<div class="actions"><button onclick="closeDialog()">取消</button>${!itemId?'<button id="model-config">仅保存联合生成设置</button>':''}<button class="primary" id="model-generate" ${state.model3d_available?'':'disabled'}>生成并验证 STEP</button></div>${state.model3d_available?'':'<p class="pcb-warning">3D 引擎尚未安装，请按 README 安装可选依赖；OLB 和 PCB 功能不受影响。</p>'}${!itemId&&state.project.model3d_generated?'<button id="model-existing">预览 / 下载已生成模型</button>':''}`);
 if(s.mechanical_dimensions){const rows=Object.values(s.mechanical_dimensions).filter(d=>['C','C1','C2','C3','C4','D','GLASS','a','b'].includes(d.symbol));$('model-total').closest('.pcb-fields').insertAdjacentHTML('afterend',`<details open><summary>规格书机械尺寸 · mm</summary><table><thead><tr><th>尺寸</th><th>最小</th><th>典型</th><th>最大</th><th>来源</th></tr></thead><tbody>${rows.map(d=>`<tr><td>${esc(d.label)} (${esc(d.symbol)})</td><td>${esc(d.min??'—')}</td><td>${esc(d.typ)}</td><td>${esc(d.max??'—')}</td><td>p${esc(d.page)}</td></tr>`).join('')}</tbody></table><p>按典型值建模；最大高度用于装配边界。修改总高或球高属于用户覆盖值。</p></details>`)}
 const values=()=>{if(!$('model-confirm').checked)throw Error('请先勾选高度和简化结构确认');return {enabled:itemId?true:$('model-enabled').checked,confirmed:true,total_height:Number($('model-total').value),ball_height:Number($('model-ball').value),dimension_source:'用户确认的总高（含球）和球高；本体与球位复用 PCB 机械参数'}};
 if($('model-existing'))$('model-existing').onclick=()=>showCurrentModel();
 if($('model-config'))$('model-config').onclick=async()=>{try{if(await act({action:'model3d-config',options:values()})){closeDialog();toast('已保存，后续联合生成将包含 STEP')}}catch(e){toast(e.message)}};
 $('model-generate').onclick=async()=>{try{
  const options=values();if(!await act({action:'model3d-build',id:itemId,options}))return;closeDialog();
  while(state.job.busy){await new Promise(r=>setTimeout(r,600));state=await api('/api/state')}
  if(state.job.error){toast(state.job.error);return}
  if(itemId){librarySelected=state.model3d_item;libraryPreview='3d';await loadLibrary();toast('3D 已保存为新版本，原版本保留')}
  else {if(document.body.classList.contains('library-mode'))await loadLibrary();await showCurrentModel()}
 }catch(e){toast(e.message)}};
}

// Studio materials only affect preview. Saved STEP geometry and its colors are
// left untouched; coatings, metal and light panels below are appearance presets.
function modelStudioMaterial(name,color,isBall){
 if(name.startsWith('TERMINAL_'))return {color:color,surface:[.25,1,2]};
 if(name==='CERAMIC_BODY_APPROX')return {color:color,surface:[.45,0,0]};
 if(name==='ALUMINA_BODY_APPROX')return {color:color,surface:[.65,0,0]};
 if(name==='CATHODE_BAND_APPROX')return {color:color,surface:[.7,0,0]};
 if(name==='RESISTIVE_COATING_APPROX'||name==='MOLDED_BODY_APPROX')return {color:color,surface:[.48,0,0]};
 if(isBall)return {color:[.63,.66,.70],surface:[.22,1,2]};
 if(name==='COVER_GLASS')return {color:[.80,.91,.97],surface:[.08,0,3]};
 if(name==='SENSOR_ARRAY')return {color:[.025,.018,.055],surface:[.16,.55,1]};
 if(name.startsWith('EDGE_FEATURE'))return {color:[.67,.52,.23],surface:[.30,.85,2]};
 if(name.startsWith('PERIMETER_FRAME'))return {color:[.31,.36,.40],surface:[.28,.75,2]};
 if(name.includes('DIRECTION_MARK'))return {color:[.17,.30,.10],surface:[.75,0,0]};
 return {color:color.map(v=>v*.24),surface:[.68,.08,0]};
}
const modelStudioShaders={
vertex:`
 attribute vec3 position;attribute vec3 normal;attribute vec3 color;
 uniform vec2 angle;uniform vec3 scale;
 varying vec3 vNormal;varying vec3 vPosition;varying vec3 vLocal;varying vec3 vColor;
 vec3 rotate(vec3 p){float c=cos(angle.x),s=sin(angle.x),a=cos(angle.y),b=sin(angle.y);vec3 q=vec3(p.x*c-p.y*s,p.x*s+p.y*c,p.z);return vec3(q.x,q.y*a-q.z*b,q.y*b+q.z*a);}
 void main(){vec3 q=rotate(position);gl_Position=vec4(q.x*scale.x,q.y*scale.y,-q.z*scale.z,1.);vNormal=rotate(normalize(normal));vPosition=q;vLocal=position;vColor=color;}
`,
fragment:`
 precision highp float;
 varying vec3 vNormal;varying vec3 vPosition;varying vec3 vLocal;varying vec3 vColor;
 uniform vec3 material;uniform vec3 baseColor;uniform float opacity;uniform float studio;
 const float PI=3.14159265;
 float saturate(float v){return clamp(v,0.,1.);}
 vec3 fresnel(float angle,vec3 f0){return f0+(1.-f0)*pow(1.-angle,5.);}
 vec3 lightBRDF(vec3 n,vec3 v,vec3 l,vec3 base,float rough,float metal){
  vec3 h=normalize(v+l);float nl=max(dot(n,l),0.),nv=max(dot(n,v),.001),nh=max(dot(n,h),0.),vh=max(dot(v,h),0.);
  float a=rough*rough,a2=a*a,d=a2/(PI*pow(nh*nh*(a2-1.)+1.,2.)+.0001),k=pow(rough+1.,2.)/8.;
  float g=nv/(nv*(1.-k)+k)*nl/(nl*(1.-k)+k);vec3 f=fresnel(vh,mix(vec3(.04),base,metal));
  return ((1.-f)*(1.-metal)*base/PI+f*d*g/max(4.*nv*nl,.001))*nl;
 }
 vec3 environment(vec3 r,float rough){
  float key=exp(-pow((r.x+.22)/(.12+rough*.5),2.)-pow((r.y-.48)/(.38+rough*.25),2.));
  float fill=exp(-pow((r.x-.63)/(.16+rough*.5),2.)-pow((r.y+.16)/(.45+rough*.3),2.));
  float rim=pow(saturate(dot(r,normalize(vec3(-.7,-.2,.6)))),20.);
  float strip=exp(-pow((r.x+.20)/(.10+rough*.3),2.)-pow((r.y+.94)/(.18+rough*.3),2.));
  return mix(vec3(.11,.13,.17),vec3(.36,.41,.49),saturate(r.z*.5+.5))+key*vec3(2.8,2.75,2.65)+fill*vec3(.85,1.0,1.2)+rim*.6+strip*vec3(1.7,1.8,1.9);
 }
 void main(){
  vec3 n=normalize(vNormal);if(!gl_FrontFacing)n=-n;
  if(studio<.5){gl_FragColor=vec4(vColor*(.65+.3*abs(dot(n,normalize(vec3(.3,-.4,.85))))),opacity);return;}
  vec3 v=normalize(vec3(-vPosition.xy*.15,2.8)),r=reflect(-v,n);float nv=saturate(dot(n,v));
  float rough=material.x,metal=material.y,kind=material.z;vec3 base=baseColor;
  if(kind>.5&&kind<1.5){float film=saturate(.42+.35*sin(vLocal.x*.45+vLocal.y*.23+nv*3.));base=mix(vec3(.024,.018,.055),vec3(.015,.055,.047),film);}
  vec3 f0=mix(vec3(.04),base,metal),f=fresnel(nv,f0);
  vec3 lit=base*(.16+.12*saturate(n.z))*(1.-metal)+environment(r,rough)*f*(.65-.35*rough);
  lit+=lightBRDF(n,v,normalize(vec3(-.5,.65,1.)),base,rough,metal)*2.5;
  lit+=lightBRDF(n,v,normalize(vec3(.8,-.25,.6)),base,rough,metal)*vec3(.55,.65,.85);
  if(kind<.5){float grain=fract(sin(dot(vLocal.xy,vec2(127.1,311.7)))*43758.5453);lit*=.96+grain*.06;}
  if(kind>2.5){
   if(opacity>.99){gl_FragColor=vec4(vColor,1.);return;}
   float edge=pow(1.-nv,5.);vec3 env=environment(r,.08);
   float highlight=saturate(max(max(env.r,env.g),env.b)-.35);
   float alpha=clamp(.035+edge*.42+highlight*.12,.035,.45);
   vec3 glassColor=mix(vec3(.42,.60,.67),env/(env+vec3(1.)),.8);
   gl_FragColor=vec4(glassColor,alpha);return;
  }
  lit=lit/(lit+vec3(1.));lit=pow(lit,vec3(1./2.2));gl_FragColor=vec4(lit,1.);
 }
`};
async function showCurrentModel(){
 try{const mesh=await api('/api/model3d/mesh');dialog('<h2>已生成 STEP · 简化机械模型</h2><div id="model-current-preview" style="height:340px;background:#f7f9fc;border-radius:10px"></div><p>拖动旋转 · 滚轮缩放 · 双击复位。毫米单位，Z=0 为接触板面；传感器模型包含透明玻璃与感光区域；内部结构为简化外观，不包含镜头。部分 CAD 导入器不保留透明度：可隐藏 COVER_GLASS 或将其透明度设为 82%。写实材质仅用于 Web 预览。</p><div class="actions"><button onclick="closeDialog()">关闭</button><button id="model-inspection-download">下载隐藏玻璃检查版</button><button class="primary" id="model-download">下载完整 STEP</button></div>');drawModel3D($('model-current-preview'),mesh);if(mesh.kind==='polygon_smd'){$('model-inspection-download').style.display='none';$('model-current-preview').nextElementSibling.textContent='QFN 本体及独立器件端子；旋转、滚轮缩放可检查底部。端子圆角、PIN1 标记及材质为已标注外观近似。'}$('model-download').onclick=()=>downloadCadence('/api/model3d/download',(state.project.footprint||'device')+'.step');$('model-inspection-download').onclick=()=>downloadCadence('/api/model3d/download?variant=inspection',(state.project.footprint||'device')+'_INSPECTION_NO_GLASS.step')}catch(e){toast(e.message)}
}
async function libraryModelPreview(target,item){
 target.innerHTML='<div class="catalog-empty">正在读取 3D 模型…</div>';
 try{const mesh=await api((item.history?'/api/library/history/mesh':'/api/library/mesh')+'?id='+encodeURIComponent(item.id));if(!target.isConnected||libraryPreview!=='3d'||libraryDetail?.id!==item.id)return;drawModel3D(target,mesh)}catch(e){target.textContent=e.message}
}
function drawModel3D(target,data){
 target._disposeModel?.();
 target.style.position='relative';target.style.background='radial-gradient(ellipse at 48% 35%,#fff 0%,#eef1f4 72%,#e4e9ef 100%)';target.style.overflow='hidden';target.innerHTML='<div class="model-shadow" style="position:absolute;inset:0;pointer-events:none"></div><canvas style="position:relative;width:100%;height:100%;display:block;touch-action:none" aria-label="器件三维模型"></canvas><span class="model-dimensions" style="position:absolute;left:12px;top:10px;font-size:11px;color:#7c899c;pointer-events:none"></span><span class="model-help" style="position:absolute;left:12px;bottom:10px;font-size:11px;color:#7c899c;pointer-events:none">材质与灯光为外观示意 · 拖动旋转 / 滚轮缩放</span>';
 const optical=data.optical||null;
 const controls=document.createElement('div');controls.style.cssText='position:absolute;right:10px;top:32px;display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end;max-width:95%;z-index:2';
 controls.innerHTML=['正面','背面','侧面','立体'].map((name,i)=>`<button type="button" data-view="${i}" style="font-size:12px;padding:5px 9px;border:1px solid #dce4ef;border-radius:6px;background:#fff;color:#345">${name}</button>`).join('')+(optical?'<button type="button" data-glass style="font-size:12px;padding:5px 9px;border:1px solid #dce4ef;border-radius:6px;background:#fff;color:#345">隐藏玻璃</button><button type="button" data-annotations style="font-size:12px;padding:5px 9px;border:1px solid #dce4ef;border-radius:6px;background:#fff;color:#345">隐藏标注</button>':'');target.appendChild(controls);
 const overlay=document.createElementNS('http://www.w3.org/2000/svg','svg');overlay.style.cssText='position:absolute;inset:0;width:100%;height:100%;pointer-events:none';target.appendChild(overlay);
 if(optical){const info=document.createElement('div');info.style.cssText='position:absolute;left:12px;bottom:30px;right:12px;font-size:11px;line-height:1.6;color:#607189;pointer-events:none';info.textContent=`感光区 ${optical.size.join(' × ')} mm · 玻璃 ${optical.glass_thickness} mm`+(data.appearance_notice?' · 边缘小方块 / 细框 / 三角标记 / 收边为图示外观近似':'');target.appendChild(info)}
 const canvas=target.querySelector('canvas'),gl=canvas.getContext('webgl',{antialias:true,preserveDrawingBuffer:true}),bounds=data.bounds,mid=[(bounds[0]+bounds[3])/2,(bounds[1]+bounds[4])/2,(bounds[2]+bounds[5])/2];
 if(!gl){target.innerHTML='<div class="catalog-empty">当前浏览器未启用 WebGL，请启用硬件加速或下载 STEP 查看。</div>';return}
 const shader=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error('3D 着色器不可用');return s};
 const program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,modelStudioShaders.vertex));
 gl.attachShader(program,shader(gl.FRAGMENT_SHADER,modelStudioShaders.fragment));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('3D 显示初始化失败');gl.useProgram(program);
 const values=[],ranges=[];
 for(const mesh of [...data.meshes].sort((a,b)=>(b.opacity??1)-(a.opacity??1))){
  const start=values.length/9,isBall=/^[A-Z]{1,3}\d+$/.test(mesh.name),lo=[0,1,2].map(k=>Math.min(...mesh.vertices.map(v=>v[k]))),hi=[0,1,2].map(k=>Math.max(...mesh.vertices.map(v=>v[k]))),capRadius=(hi[0]-lo[0])/2,ballHeight=hi[2]-lo[2],radius=ballHeight<capRadius?(capRadius*capRadius+ballHeight*ballHeight)/(2*ballHeight):capRadius,center=[(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]+radius];
  for(const tri of mesh.triangles){const [a,b,c]=tri.map(i=>mesh.vertices[i]),u=b.map((v,i)=>v-a[i]),v=c.map((v,i)=>v-a[i]),n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]],flatCap=isBall&&Math.abs(a[2]-b[2])+Math.abs(b[2]-c[2])<1e-8,color=mesh.name==='A1'?[.9,.66,.22]:mesh.color;
   for(const p of [a,b,c])values.push(...p.map((v,i)=>v-mid[i]),...(isBall&&!flatCap?p.map((v,i)=>v-center[i]):n),...color)
  }ranges.push({start,count:values.length/9-start,opacity:mesh.opacity??1,name:mesh.name,material:modelStudioMaterial(mesh.name,mesh.color,isBall)});
 }
 const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(values),gl.STATIC_DRAW);
 for(const [name,offset] of [['position',0],['normal',12],['color',24]]){const loc=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,3,gl.FLOAT,false,36,offset)}
 const opacityLocation=gl.getUniformLocation(program,'opacity');const angleLocation=gl.getUniformLocation(program,'angle'),scaleLocation=gl.getUniformLocation(program,'scale'),materialLocation=gl.getUniformLocation(program,'material'),baseLocation=gl.getUniformLocation(program,'baseColor'),studioLocation=gl.getUniformLocation(program,'studio');gl.enable(gl.DEPTH_TEST);gl.clearColor(0,0,0,0);
 target.querySelector('.model-dimensions').textContent=bounds.slice(3).map((v,j)=>(v-bounds[j]).toFixed(3)).join(' × ')+' mm · 简化模型';
 const initialPitch=Number.isFinite(data.initial_pitch)?data.initial_pitch:(data.meshes.some(m=>m.name==="SENSOR_ARRAY")?.72:2.25);let yaw=-.45,pitch=initialPitch,zoom=1.6,drag=null,glassVisible=true,annotations=false,studio=true,opaqueGlass=false;
 const styleButton=document.createElement('button');styleButton.type='button';styleButton.dataset.material='';styleButton.style.cssText='font-size:12px;padding:5px 9px;border:1px solid #dce4ef;border-radius:6px;background:#fff;color:#345';styleButton.textContent='工程配色';controls.appendChild(styleButton);
 const opacityButton=document.createElement('button');opacityButton.type='button';opacityButton.style.cssText=styleButton.style.cssText;opacityButton.textContent='玻璃设为不透明';if(optical)controls.appendChild(opacityButton);
 if(controls.querySelector('[data-annotations]'))controls.querySelector('[data-annotations]').textContent='显示标注';
 function render(){
  const rect=target.getBoundingClientRect();if(!rect.width||!rect.height)return;
  const ratio=devicePixelRatio||1;canvas.width=Math.round(rect.width*ratio);canvas.height=Math.round(rect.height*ratio);gl.viewport(0,0,canvas.width,canvas.height);
  const extent=Math.hypot(bounds[3]-bounds[0],bounds[4]-bounds[1],bounds[5]-bounds[2]),scale=Math.min(rect.width,rect.height)*.7/extent*zoom;
  gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.uniform2f(angleLocation,yaw,pitch);gl.uniform1f(studioLocation,studio?1:0);gl.uniform3f(scaleLocation,scale*2/rect.width,scale*2/rect.height,1/extent);
  for(const range of ranges){if(!glassVisible&&range.name==='COVER_GLASS')continue;if(range.opacity<1&&!(opaqueGlass&&range.name==='COVER_GLASS')){gl.enable(gl.BLEND);gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);gl.enable(gl.CULL_FACE);gl.cullFace(gl.BACK)}else{gl.disable(gl.BLEND);gl.depthMask(true);gl.disable(gl.CULL_FACE)}gl.uniform1f(opacityLocation,opaqueGlass&&range.name==='COVER_GLASS'?1:range.opacity);gl.uniform3fv(baseLocation,range.material.color);gl.uniform3fv(materialLocation,range.material.surface);gl.drawArrays(gl.TRIANGLES,range.start,range.count)}gl.depthMask(true);gl.disable(gl.CULL_FACE);
  const projectPoint=p=>{const a=p.map((v,i)=>v-mid[i]),c=Math.cos(yaw),s=Math.sin(yaw),x=a[0]*c-a[1]*s,y=a[0]*s+a[1]*c;return [rect.width/2+x*scale,rect.height/2-(y*Math.cos(pitch)-a[2]*Math.sin(pitch))*scale]};
  const shadow=target.querySelector('.model-shadow');
  if(studio&&Math.cos(pitch)>.2){const corners=[[bounds[0],bounds[1]],[bounds[3],bounds[1]],[bounds[3],bounds[4]],[bounds[0],bounds[4]]].map(([x,y])=>projectPoint([x+.13,y+.10,bounds[2]-.04]));shadow.innerHTML=`<svg width="100%" height="100%" viewBox="0 0 ${rect.width} ${rect.height}"><polygon points="${corners.map(p=>p.join(',')).join(' ')}" fill="#263342" opacity=".23" style="filter:blur(12px)"/></svg>`}else shadow.innerHTML='';
  overlay.setAttribute('viewBox',`0 0 ${rect.width} ${rect.height}`);overlay.innerHTML='';
  if(optical&&annotations&&Math.cos(pitch)>0.15){
   const project=p=>{const a=p.map((v,i)=>v-mid[i]),c=Math.cos(yaw),s=Math.sin(yaw),x=a[0]*c-a[1]*s,y=a[0]*s+a[1]*c;return [rect.width/2+x*scale,rect.height/2-(y*Math.cos(pitch)-a[2]*Math.sin(pitch))*scale]};
   const [cx,cy]=optical.center,[w,h]=optical.size,z=bounds[5]-(optical.top_to_wafer??optical.glass_thickness);
   const corners=[[-w/2,-h/2],[w/2,-h/2],[w/2,h/2],[-w/2,h/2]].map(([x,y])=>project([cx+x,cy+y,z]));
   const [x,y]=project([cx,cy,z]);overlay.innerHTML=`<polygon points="${corners.map(p=>p.join(',')).join(' ')}" fill="none" stroke="#f7b653" stroke-width="1.2"/><path d="M${x-8},${y}H${x+8}M${x},${y-8}V${y+8}" stroke="#f7b653" stroke-width="1.2"/><text x="${x+12}" y="${y-10}" fill="#ab6509" font-size="11" style="paint-order:stroke;stroke:#fff;stroke-width:3">光学中心 · 参考标注</text>`;
  }
 }
 controls.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{const view=Number(b.dataset.view);yaw=view===3?-.45:(view===1?Math.PI:0);pitch=[0,Math.PI,-Math.PI/2,initialPitch][view];zoom=1.6;render()});
 const glassButton=controls.querySelector('[data-glass]');if(glassButton)glassButton.onclick=()=>{glassVisible=!glassVisible;glassButton.textContent=glassVisible?'隐藏玻璃':'显示玻璃';render()};
 const annotationButton=controls.querySelector('[data-annotations]');if(annotationButton)annotationButton.onclick=()=>{annotations=!annotations;annotationButton.textContent=annotations?'隐藏标注':'显示标注';render()};
 opacityButton.onclick=()=>{opaqueGlass=!opaqueGlass;opacityButton.textContent=opaqueGlass?'恢复透明玻璃':'玻璃设为不透明';render()};
 styleButton.onclick=()=>{studio=!studio;styleButton.textContent=studio?'工程配色':'写实材质';target.querySelector('.model-help').textContent=studio?'材质与灯光为外观示意 · 拖动旋转 / 滚轮缩放':'工程配色 · 金色为 A1 · 拖动旋转 / 滚轮缩放';render()};
 canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY,yaw,pitch];canvas.setPointerCapture(e.pointerId)};
 canvas.onpointermove=e=>{if(!drag)return;yaw=drag[2]+(e.clientX-drag[0])*.012;pitch=drag[3]+(e.clientY-drag[1])*.012;render()};canvas.onpointerup=canvas.onpointercancel=()=>drag=null;
 canvas.onwheel=e=>{e.preventDefault();zoom=Math.max(.2,Math.min(8,zoom*(e.deltaY<0?1.12:1/1.12)));render()};canvas.ondblclick=()=>{yaw=-.45;pitch=initialPitch;zoom=1.6;render()};render();
 target._disposeModel=()=>{observer.disconnect();gl.deleteBuffer(buffer);gl.deleteProgram(program);target._disposeModel=null};
 const observer=new ResizeObserver(()=>{if(!canvas.isConnected){target._disposeModel?.();return}render()});observer.observe(target);
}

function polygonModelDialog(s,itemId){
 const options=state.project.model3d||{};
 dialog(`<h2>QFN 器件 3D</h2><p>本体 ${s.body.join(' × ')} mm；端子采用 p46 器件机械轮廓，与 p47 PCB 焊盘分开。圆端/角部为简化近似，PIN1 表面标记为外观示意。</p><div class="field"><label>总高度（mm，规格书 ${s.height_min}–${s.height_max}）</label><input id="qfn-model-height" type="number" step=".01" value="${options.total_height??s.height_nominal}"></div><p>${esc(s.terminal_profile.notice)}</p><label><input id="qfn-model-confirm" type="checkbox"> 已核对高度并接受已标注的端子外观近似。</label><div class="actions"><button onclick="closeDialog()">取消</button><button id="qfn-model-build" class="primary">生成并验证 STEP</button></div>${!itemId&&state.project.model3d_generated?'<button id="model-existing">预览 / 下载已生成模型</button>':''}`);
 if($('model-existing'))$('model-existing').onclick=()=>showCurrentModel();
 $('qfn-model-build').onclick=async()=>{if(!$('qfn-model-confirm').checked){toast('请先确认高度与外观近似');return}const opts={confirmed:true,enabled:true,total_height:Number($('qfn-model-height').value),dimension_source:'TI p46 QFN nominal terminals; documented appearance simplifications'};if(!await act({action:'model3d-build',id:itemId,options:opts}))return;closeDialog();while(state.job.busy){await new Promise(r=>setTimeout(r,600));state=await api('/api/state')}if(state.job.error){toast(state.job.error);return}if(itemId){librarySelected=state.model3d_item;await loadLibrary()}else await showCurrentModel()};
}

function standardModelDialog(s,itemId){
 dialog(`<h2>贴片器件 3D</h2><p>${esc(s.label)} · 本体 ${s.body.join(' × ')} mm · ${s.height_selection==='maximum_envelope'?'按最大高度包络建模，不代表具体料号典型高度':'机械尺寸按已核对资料取值'}</p><p>${esc(s.standard_recipe.notes)}</p><div class="field"><label>总高度 · mm（不超过 ${s.height_max}）</label><input id="standard-model-height" type="number" step=".01" value="${s.height_nominal}"></div><label><input type="checkbox" id="standard-model-confirm"> 已核对规格书版本和标注的外观近似</label><div class="actions"><button onclick="closeDialog()">取消</button><button id="standard-model-build" class="primary">生成并验证 STEP</button></div>`);
 $('standard-model-build').onclick=async()=>{if(!$('standard-model-confirm').checked){toast('请先确认高度和外观说明');return}const options={confirmed:true,enabled:true,total_height:Number($('standard-model-height').value)};if(!await act({action:'model3d-build',id:itemId,options}))return;closeDialog();while(state.job.busy){await new Promise(r=>setTimeout(r,600));state=await api('/api/state')}if(state.job.error){toast(state.job.error);return}if(itemId){librarySelected=state.model3d_item;libraryPreview='3d';await loadLibrary()}else await showCurrentModel()};
}
