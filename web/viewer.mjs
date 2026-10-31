import * as THREE from './vendor/three.module.js?v=aligned-sdf-chart-safe-3';
import {OrbitControls} from './vendor/OrbitControls.js?v=aligned-sdf-chart-safe-3';
import {STLLoader} from './vendor/STLLoader.js?v=aligned-sdf-chart-safe-3';

const $=id=>document.getElementById(id);
const axes=['axial','coronal','sagittal'];
const sides=['left','right'];
const disabledMorphPairs=new Set();
const colors={left:0xf04444,right:0x27a85b};
const selected={axial:1,coronal:256,sagittal:256};
export const state={ready:false,time:0,ctIndex:0,morphReady:false,morphMilliseconds:0,displayedTime:null};
const scene=new THREE.Scene();
scene.background=new THREE.Color(0xffffff);
const camera=new THREE.PerspectiveCamera(42,innerWidth/innerHeight,.1,5000);
const renderer=new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
renderer.setSize(innerWidth,innerHeight);
renderer.domElement.setAttribute('aria-label','手动对齐后的三维头部模型');
document.body.appendChild(renderer.domElement);
scene.add(new THREE.HemisphereLight(0xffffff,0xb6bcc5,2.0));
const light=new THREE.DirectionalLight(0xffffff,2.3);
light.position.set(-150,-400,400);scene.add(light);
const fill=new THREE.DirectionalLight(0xffffff,.8);fill.position.set(150,100,40);scene.add(fill);
const controls=new OrbitControls(camera,renderer.domElement);
controls.enableRotate=false;controls.enablePan=false;controls.enableZoom=true;
const modelGroup=new THREE.Group();scene.add(modelGroup);
const morphGroup=new THREE.Group();modelGroup.add(morphGroup);
const loader=new STLLoader(),ray=new THREE.Raycaster(),mouse=new THREE.Vector2();
let timeline=[],skull,homeDistance=400,morphConfig,worker,workerBusy=false,pendingBlend=null,requestId=0;
let visibleEyes=null;
const eyeCache=new Map(),morphMeshes={};

function status(message,error=false){$('selection').textContent=message;$('selection').classList.toggle('error',error);}
async function json(url){const response=await fetch(url,{cache:'no-cache'});if(!response.ok)throw new Error(`${url}：HTTP ${response.status}`);return response.json();}
async function mesh(url,segment){
  const geometry=await loader.loadAsync(url);
  const positions=geometry.getAttribute('position');
  if(!positions||!positions.count)throw new Error('模型没有三角面：'+url);
  geometry.computeBoundingBox();geometry.computeBoundingSphere();
  const isSkull=segment==='skull';
  const material=new THREE.MeshStandardMaterial({color:isSkull?0xb6b4aa:colors[segment],roughness:.57,metalness:0,side:THREE.DoubleSide,transparent:isSkull,opacity:isSkull?+$('opacity').value:1,depthWrite:!isSkull});
  const result=new THREE.Mesh(geometry,material);
  result.name=segment;result.userData.segment=segment;
  return result;
}
function eachVisibleMesh(objects){return objects.filter(Boolean).flatMap(object=>{
  const result=[];if(!object.visible)return result;
  object.traverse(o=>{if(o.isMesh&&o.visible)result.push(o);});return result;
});}
function updateVisibility(){
  if(skull)skull.visible=$('skull').checked;
  for(const side of sides){
    if(visibleEyes)visibleEyes.getObjectByName(side).visible=$(side).checked;
    if(morphMeshes[side])morphMeshes[side].visible=$(side).checked;
  }
}
function showOriginal(index){
  if(visibleEyes)visibleEyes.visible=false;
  visibleEyes=eyeCache.get(index);visibleEyes.visible=true;
  morphGroup.visible=false;updateVisibility();
  state.displayedTime=index;
}
function submitBlend(){
  if(workerBusy||!pendingBlend||!state.morphReady)return;
  const request=pendingBlend;pendingBlend=null;workerBusy=true;
  worker.postMessage({type:'blend',...request});
}
function requestBlend(a,b,f){pendingBlend={id:++requestId,a,b,f};submitBlend();}
function applyMorph(result){
  workerBusy=false;
  const playbackFrame=playing && result.a===Math.floor(state.time) && result.a+result.f<=state.time;
  if((result.id!==requestId&&!playbackFrame)||Math.abs(state.time-Math.round(state.time))<1e-6){submitBlend();return;}
  for(const item of result.meshes){
    const object=morphMeshes[item.side];
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.BufferAttribute(item.positions,3));
    geometry.setAttribute('normal',new THREE.BufferAttribute(item.normals,3));
    geometry.computeBoundingSphere();
    object.geometry.dispose();object.geometry=geometry;
  }
  if(visibleEyes)visibleEyes.visible=false;
  morphGroup.visible=true;updateVisibility();
  state.displayedTime=result.a+result.f;
  state.morphMilliseconds=result.milliseconds;
}
async function initializeMorph(){
  morphConfig=await json('web/aligned_scene/morph.json');
  for(const side of sides){
    const item=morphConfig.axes[side];
    if(!item||item.fields.length!==timeline.length||item.fields.some((f,i)=>f.date!==timeline[i].date))throw new Error('距离场日期与手动对齐场景不匹配');
    const object=new THREE.Mesh(new THREE.BufferGeometry(),new THREE.MeshStandardMaterial({color:colors[side],roughness:.57,side:THREE.DoubleSide,transparent:false,opacity:1}));
    object.name=side;object.userData.segment=side;
    object.position.fromArray(item.renderCenter);object.scale.setScalar(item.renderScale);
    morphMeshes[side]=object;morphGroup.add(object);
  }
  morphGroup.visible=false;
  worker=new Worker(new URL('./morph-worker.mjs?v=solid-2',import.meta.url),{type:'module'});
  return new Promise((resolve,reject)=>{
    worker.onerror=error=>{state.morphReady=false;workerBusy=false;status('形状插值加载失败，请刷新重试。',true);reject(new Error(error.message));};
    worker.onmessage=({data})=>{
      if(data.type==='ready'){state.morphReady=true;resolve();}
      else if(data.type==='mesh'){
        applyMorph(data);submitBlend();
      }else if(data.type==='error'){
        workerBusy=false;state.morphReady=false;status('形状插值失败：'+data.message,true);reject(new Error(data.message));
      }
    };
    worker.postMessage({type:'init',config:morphConfig,baseURL:document.baseURI});
  });
}
function morphQuality(a,b,f){
  const leftA=morphConfig.axes.left.fields[a],leftB=morphConfig.axes.left.fields[b],rightA=morphConfig.axes.right.fields[a],rightB=morphConfig.axes.right.fields[b];
  const weak=[];
  for(const [side,x,y] of [['左眼',leftA,leftB],['右眼',rightA,rightB]]){
    const xStats=x.sourceStats,yStats=y.sourceStats;
    const sourceCells=Math.min(xStats.triangles,yStats.triangles),reconstructedCells=Math.min(x.endpointReconstructionStats.triangles,y.endpointReconstructionStats.triangles);
    const maxError=Math.max(x.endpointSurfaceError.maximumSampledMm,y.endpointSurfaceError.maximumSampledMm);
    if(maxError>0.5)weak.push(`${side}端点采样误差 ${maxError.toFixed(2)} mm`);
    if(!sourceCells||!reconstructedCells)weak.push(`${side}没有可用表面`);
  }
  return weak;
}
function dateLabel(date){return `${date.slice(0,4)}-${date.slice(4,6)}-${date.slice(6,8)}`;}
function volumeFor(item,side){return Number(item.displayMeasurements?.[side]?.volumeCm3);}
function renderVolumeChart(){
  const width=294,height=148,plot={left:34,right:8,top:10,bottom:34};
  const values=sides.map(side=>timeline.map(t=>volumeFor(t,side)));
  if(values.some(series=>series.some(value=>!Number.isFinite(value)))){ $('volumeChart').textContent='网格体积数据不完整'; return; }
  const max=Math.ceil(Math.max(...values.flat())/2)*2;
  const x=i=>plot.left+i/Math.max(1,timeline.length-1)*(width-plot.left-plot.right);
  const y=value=>plot.top+(max-value)/max*(height-plot.top-plot.bottom);
  const ticks=[0,max/2,max];
  let svg=`<svg class="volume-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="左右侧修复后模型外形体积，单位立方厘米">`;
  for(const tick of ticks)svg+=`<line class="grid" x1="${plot.left}" x2="${width-plot.right}" y1="${y(tick)}" y2="${y(tick)}"/><text x="${plot.left-5}" y="${y(tick)+3}" text-anchor="end">${tick}</text>`;
  svg+=`<text x="${width-2}" y="9" text-anchor="end">cm³</text>`;
  for(let series=0;series<values.length;series++){
    const side=sides[series],key=series===0?'left-line':'right-line',color=series===0?'#e33b3b':'#1d9b59';
    const points=values[series].map((value,index)=>`${index?'L':'M'}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(' ');
    svg+=`<path class="line ${key}" d="${points}"/>`;
    values[series].forEach((value,index)=>{const active=index===state.ctIndex;svg+=`<circle class="point ${active?'active':''}" data-date-index="${index}" cx="${x(index).toFixed(1)}" cy="${y(value).toFixed(1)}" r="${active?5:3.7}" fill="${color}"><title>${dateLabel(timeline[index].date)} ${side==='left'?'左侧':'右侧'} ${value.toFixed(4)} cm³</title></circle>`;});
  }
  timeline.forEach((item,index)=>{const label=item.date.slice(4,6)+'/'+item.date.slice(6,8);svg+=`<text x="${x(index)}" y="${height-18}" text-anchor="middle"><title>${dateLabel(item.date)}</title>${label}</text>`;});
  svg+='</svg><div class="chart-legend"><span><i class="left-dot"></i>左侧网格体积</span><span><i class="right-dot"></i>右侧网格体积</span></div>';$('volumeChart').innerHTML=svg;
}
function updateData(){
  const item=timeline[state.ctIndex];
  const skullVolume=Number(timeline[0].segments.skull.volume_cm3_lm);
  const left=volumeFor(item,'left');
  const right=volumeFor(item,'right');
  $('volumes').innerHTML=`<table><tr><td>固定颅骨参考</td><td>${skullVolume.toFixed(3)} cm³</td></tr><tr><td>左侧网格体积</td><td>${left.toFixed(4)} cm³</td></tr><tr><td>右侧网格体积</td><td>${right.toFixed(4)} cm³</td></tr><tr><td>小侧 / 大侧</td><td>${(Math.min(left,right)/Math.max(left,right)).toFixed(5)}</td></tr></table>`;
  $('volumeNote').textContent='按修复后的显示模型计算外形体积。日期节点等距，曲线仅统计检查日期的模型；中间形状为几何插值。';
  renderVolumeChart();
  $('ctDate').textContent='当前 CT：'+dateLabel(item.date)+'（实际检查）';
}
function viewCount(axis){const t=timeline[state.ctIndex];return axis==='axial'?t.geometry.origins.length:axis==='coronal'?t.geometry.rows:t.geometry.cols;}
function physicalViewSize(axis){
  const g=timeline[state.ctIndex].geometry;
  const first=new THREE.Vector3(...g.origins[0]),last=new THREE.Vector3(...g.origins.at(-1));
  const depth=first.distanceTo(last)*(g.origins.length/(Math.max(1,g.origins.length-1)));
  const width=g.cols*g.spacing[1],height=g.rows*g.spacing[0];
  return axis==='axial'?[width,height]:axis==='coronal'?[width,depth]:[height,depth];
}
function fitViews(){
  if(!timeline.length)return;
  for(const axis of axes){
    const [w,h]=physicalViewSize(axis),frame=$(axis+'Frame');
    const factor=Math.min(frame.clientWidth/w,frame.clientHeight/h);
    const image=$(axis+'View');image.style.width=`${w*factor}px`;image.style.height=`${h*factor}px`;
  }
}
function setView(axis,n){
  const item=timeline[state.ctIndex],max=viewCount(axis);
  selected[axis]=Math.max(1,Math.min(max,Math.round(n)));
  const path=item.sliceDir+'/views/'+axis+'_'+String(selected[axis]).padStart(3,'0')+'.png';
  const image=$(axis+'View');if(image.getAttribute('src')!==path)image.src=path;
  $(axis+'No').textContent=`slice ${selected[axis]} / ${max}`;
}
function refreshViews(){axes.forEach(axis=>setView(axis,selected[axis]));fitViews();}
export function setTime(value){
  if(!state.ready)return;
  const max=timeline.length-1,v=THREE.MathUtils.clamp(Number(value),0,max),nearest=Math.round(v);
  const exact=Math.abs(v-nearest)<1e-6,a=Math.floor(v),b=Math.min(max,a+1),f=v-a;
  const unstablePair=!exact&&disabledMorphPairs.has(`${timeline[a]?.date}:${timeline[b]?.date}`);
  const previousCT=state.ctIndex;
  state.time=v;state.ctIndex=nearest;$('timeSlider').value=v;
  if(exact){
    pendingBlend=null;showOriginal(nearest);
    $('timeLabel').textContent=dateLabel(timeline[nearest].date);
    $('timeMode').textContent='实际检查日期 · 使用手动对齐结果'+(timeline[nearest].visualizationCompletion?' · 可视化内腔补全':'');
  }else{
    $('timeLabel').textContent=`${dateLabel(timeline[a].date)} → ${dateLabel(timeline[b].date)}`;
    const quality=morphQuality(a,b,f);
    $('timeMode').textContent=`形状插值 ${Math.round(f*100)}% · 非新增检查${quality.length?' · '+quality.join('；'):''}`;
    if(unstablePair){pendingBlend=null;requestId++;showOriginal(nearest);$('timeMode').textContent='此区间的插值会产生明显缺损，当前显示最近日期的实测模型';}
    else if(state.morphReady)requestBlend(a,b,f);
    else{showOriginal(nearest);$('timeMode').textContent='插值尚未就绪，显示最近的实际模型';}
  }
  if(previousCT!==state.ctIndex||!$('axialView').getAttribute('src')){updateData();refreshViews();}
  status(unstablePair?'为避免缺损伪影，此区间显示最近一次实测模型；点击模型联动 CT。':'已加载全部时间点；点击模型联动 CT。');
  $('prev').disabled=v<=0;$('next').disabled=v>=max;
}
export function selectModelPoint(point){
  const t=timeline[state.ctIndex],alignment=t.alignment;
  if(!alignment?.webToNativeLPS){status('这个模型没有保存到原始 CT 的坐标变换。',true);return null;}
  const local=point.clone().applyMatrix4(new THREE.Matrix4().set(...alignment.webToNativeLPS));
  const g=t.geometry,u=new THREE.Vector3(...g.orientation.slice(0,3)),v=new THREE.Vector3(...g.orientation.slice(3,6)),normal=new THREE.Vector3().crossVectors(u,v).normalize();
  let k=0,best=Infinity;
  for(let i=0;i<g.origins.length;i++){
    const distance=Math.abs(new THREE.Vector3().subVectors(local,new THREE.Vector3(...g.origins[i])).dot(normal));
    if(distance<best){best=distance;k=i;}
  }
  const delta=local.clone().sub(new THREE.Vector3(...g.origins[k]));
  const col=Math.round(delta.dot(u)/g.spacing[1]),row=Math.round(delta.dot(v)/g.spacing[0]);
  const axialSpacing=g.origins.length>1?new THREE.Vector3(...g.origins[0]).distanceTo(new THREE.Vector3(...g.origins[1])):1;
  if(col<0||col>=g.cols||row<0||row>=g.rows||best>axialSpacing*.75){
    status('该点位于当前实际 CT 的扫描范围外。');return null;
  }
  setView('axial',k+1);setView('coronal',row+1);setView('sagittal',col+1);
  status(`${dateLabel(t.date)} CT · 体素 (${col}, ${row}, ${k}) · 轴向 slice ${k+1}`);
  return {col,row,k};
}
function resetCamera(){
  modelGroup.rotation.set(0,0,0);camera.up.set(0,0,1);camera.position.set(0,-homeDistance,0);controls.target.set(0,0,0);controls.update();
}
let down=null,wasDragged=false;
renderer.domElement.addEventListener('pointerdown',event=>{
  if(event.button!==0)return;down={x:event.clientX,y:event.clientY,lastX:event.clientX,lastY:event.clientY};wasDragged=false;
  renderer.domElement.setPointerCapture(event.pointerId);
});
renderer.domElement.addEventListener('pointermove',event=>{
  if(!down)return;
  if(Math.hypot(event.clientX-down.x,event.clientY-down.y)>4)wasDragged=true;
  if(wasDragged){modelGroup.rotation.z+=(event.clientX-down.lastX)*.008;modelGroup.rotation.x=THREE.MathUtils.clamp(modelGroup.rotation.x+(event.clientY-down.lastY)*.008,-.9,.9);}
  down.lastX=event.clientX;down.lastY=event.clientY;
});
renderer.domElement.addEventListener('pointerup',event=>{
  down=null;if(renderer.domElement.hasPointerCapture(event.pointerId))renderer.domElement.releasePointerCapture(event.pointerId);
});
renderer.domElement.addEventListener('pointercancel',()=>{down=null;wasDragged=true;});
renderer.domElement.addEventListener('click',event=>{
  if(wasDragged||!state.ready)return;
  const r=renderer.domElement.getBoundingClientRect();mouse.set((event.clientX-r.left)/r.width*2-1,-(event.clientY-r.top)/r.height*2+1);
  ray.setFromCamera(mouse,camera);
  const eyes=eachVisibleMesh([morphGroup.visible?morphGroup:visibleEyes]);
  const hits=ray.intersectObjects(eyes,false);
  const hit=hits[0]||ray.intersectObjects(eachVisibleMesh([skull]),false)[0];
  if(hit)selectModelPoint(modelGroup.worldToLocal(hit.point.clone()));
});
for(const side of ['skull',...sides])$(side).onchange=updateVisibility;
let playing=false,lastPlaybackTick=null;
function pausePlayback(){playing=false;lastPlaybackTick=null;$('play').textContent='▶ 播放';$('play').setAttribute('aria-pressed','false');}
function seekManually(value){pausePlayback();setTime(value);}
$('play').onclick=()=>{
  if(!state.ready)return;
  if(playing){pausePlayback();return;}
  if(state.time>=timeline.length-1)setTime(0);
  playing=true;lastPlaybackTick=null;
  $('play').textContent='Ⅱ 暂停';$('play').setAttribute('aria-pressed','true');
};
$('timeSlider').addEventListener('pointerdown',pausePlayback);
document.addEventListener('visibilitychange',()=>{if(document.hidden)pausePlayback();});
$('opacity').oninput=()=>{if(skull)skull.material.opacity=+$('opacity').value;};
$('resetView').onclick=resetCamera;
$('timeSlider').oninput=event=>seekManually(event.target.value);
$('volumeChart').addEventListener('click',event=>{const point=event.target.closest('[data-date-index]');if(point)seekManually(Number(point.dataset.dateIndex));});
$('prev').onclick=()=>seekManually(Math.max(0,Math.ceil(state.time)-1));
$('next').onclick=()=>seekManually(Math.min(timeline.length-1,Math.floor(state.time)+1));
for(const axis of axes){
  $(axis+'Frame').addEventListener('wheel',event=>{event.preventDefault();if(state.ready)setView(axis,selected[axis]+Math.sign(event.deltaY));},{passive:false});
  $(axis+'View').onerror=()=>status('CT 切片读取失败：'+axis,true);
}
addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);fitViews();});
async function initialize(){
  if(location.protocol==='file:')throw new Error('请先双击“启动CT查看器.cmd”，通过本地服务打开页面。');
  timeline=await json('web/aligned_scene/timeline.json');
  if(!Array.isArray(timeline)||!timeline.length)throw new Error('对齐场景时间轴为空');
  for(const t of timeline){if(!t.alignment?.webToNativeLPS||!t.geometry?.origins?.length)throw new Error(t.date+' 缺少 CT 坐标变换');}
  $('timeSlider').max=timeline.length-1;
  status('正在加载手动对齐的参考颅骨…');
  skull=await mesh(timeline[0].sharedSkull||'web/aligned_scene/skull.stl','skull');modelGroup.add(skull);
  const box=new THREE.Box3().setFromObject(skull),size=box.getSize(new THREE.Vector3());
  homeDistance=Math.max(size.z,size.x/camera.aspect)*2.5;resetCamera();
  const morphPromise=initializeMorph().catch(error=>{console.error(error);status('形状插值不可用：'+error.message,true);return false;});
  let completed=0;
  await Promise.all(timeline.map(async(t,index)=>{
    const group=new THREE.Group();group.name=t.date;
    const children=await Promise.all(sides.map(side=>mesh(t.eyeModels[side],side)));children.forEach(child=>group.add(child));
    group.visible=false;modelGroup.add(group);eyeCache.set(index,group);
    status(`正在预加载已对齐的双眼：${++completed} / ${timeline.length}`);
  }));
  await morphPromise;
  state.ready=true;selected.axial=Math.floor(timeline[0].geometry.origins.length/2);
  $('timeSlider').disabled=false;$('play').disabled=false;setTime(0);
  if(!state.morphReady)status('实际模型已加载，形状插值资源不可用。',true);
}
initialize().catch(error=>{console.error(error);status('加载失败：'+error.message,true);});
renderer.setAnimationLoop(now=>{
  if(playing){
    if(lastPlaybackTick===null)lastPlaybackTick=now;
    const elapsed=Math.min(Math.max(0,now-lastPlaybackTick),250);
    if(elapsed>=50){
      lastPlaybackTick=now;
      setTime(Math.min(timeline.length-1,state.time+elapsed/10000));
      if(state.time>=timeline.length-1)pausePlayback();
    }
  }
  renderer.render(scene,camera);
});


