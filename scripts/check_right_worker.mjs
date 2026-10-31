import fs from 'node:fs';
import {MarchingCubes} from '../web/vendor/MarchingCubes.js';
import {MeshStandardMaterial} from '../web/vendor/three.module.js';
import {mainSurface} from '../web/morph-surface-cleanup.mjs';
const cfg=JSON.parse(fs.readFileSync('web/aligned_scene/morph.json','utf8')),axis=cfg.axes.right;
const fields=axis.fields.slice(3).map(x=>{const b=fs.readFileSync(x.url);return new Int16Array(b.buffer,b.byteOffset,b.length/2);});
const mc=new MarchingCubes(axis.resolution,new MeshStandardMaterial(),false,false,150000);mc.isolation=0;
const result=[];
for(let step=1;step<100;step++){
 const f=step/100;for(let i=0;i<mc.field.length;i++)mc.field[i]=(fields[0][i]*(1-f)+fields[1][i]*f)*cfg.distanceScale;
 mc.normal_cache.fill(0);mc.update();if(!mc.count||mc.count>mc.positionArray.length/3)throw Error('bad surface');
 const raw=mc.positionArray.slice(0,mc.count*3),norm=mc.normalArray.slice(0,mc.count*3),clean=mainSurface(raw,norm);
 if(!clean.positions.every(Number.isFinite)||clean.positions.length<raw.length*.99)throw Error('invalid/excessive cleanup');
 const edges=new Map();for(let t=0;t<clean.positions.length;t+=9){const vs=[0,3,6].map(o=>[0,1,2].map(j=>Math.round(clean.positions[t+o+j]*1e6)).join(','));for(let k=0;k<3;k++){const key=[vs[k],vs[(k+1)%3]].sort().join('/');edges.set(key,(edges.get(key)||0)+1);}}
 result.push({f,triangles:clean.positions.length/9,removed:clean.removedTriangles,nonPairEdges:[...edges.values()].filter(v=>v!==2).length});
}
fs.writeFileSync('web/aligned_scene/qa/right_worker_checks.json',JSON.stringify(result,null,2));console.log('Actual Three.js frames:',result.length,'max removed triangles:',Math.max(...result.map(r=>r.removed)),'non-pair edges frames:',result.filter(r=>r.nonPairEdges).length);
