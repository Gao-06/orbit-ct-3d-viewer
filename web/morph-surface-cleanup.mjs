// Suppress disconnected interpolation specks while retaining the main closed surface.
export function mainSurface(positions,normals){
  const count=positions.length/9,parent=new Int32Array(count),sizes=new Int32Array(count),owner=new Map();
  for(let i=0;i<count;i++){parent[i]=i;sizes[i]=1;}
  const find=i=>{while(parent[i]!==i){parent[i]=parent[parent[i]];i=parent[i];}return i;};
  for(let t=0;t<count;t++)for(let v=0;v<3;v++){
    const k=t*9+v*3,key=[0,1,2].map(j=>Math.round(positions[k+j]*1e6)).join(',');
    if(owner.has(key)){let a=find(t),b=find(owner.get(key));if(a!==b){if(sizes[a]<sizes[b])[a,b]=[b,a];parent[b]=a;sizes[a]+=sizes[b];}}
    else owner.set(key,t);
  }
  let biggest=0;for(let i=0;i<count;i++)if(sizes[find(i)]>sizes[biggest])biggest=find(i);
  // Large disconnected pieces must not be silently removed.
  const roots=new Set();for(let i=0;i<count;i++)roots.add(find(i));
  const keep=new Set([...roots].filter(r=>r===biggest||sizes[r]>Math.max(64,count*.005)));
  const kept=[...keep].reduce((sum,r)=>sum+sizes[r],0);
  if(kept===count)return {positions,normals,removedTriangles:0};
  const p=new Float32Array(kept*9),n=new Float32Array(kept*9);let cursor=0;
  for(let i=0;i<count;i++)if(keep.has(find(i))){p.set(positions.subarray(i*9,i*9+9),cursor);n.set(normals.subarray(i*9,i*9+9),cursor);cursor+=9;}
  return {positions:p,normals:n,removedTriangles:count-kept};
}
