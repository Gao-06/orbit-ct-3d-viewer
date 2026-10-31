import {mainSurface} from './morph-surface-cleanup.mjs';
import {MeshStandardMaterial} from './vendor/three.module.js';
import {MarchingCubes} from './vendor/MarchingCubes.js';

let config;
const fields = {}, engines = {};
self.onmessage = async ({data}) => {
  try {
    if(data.type === 'init') {
      config=data.config;
      await Promise.all(['left','right'].map(async side => {
        const axis=config.axes[side];
        fields[side]=await Promise.all(axis.fields.map(async item=>{
          const response=await fetch(new URL(item.url,data.baseURL),{cache:'no-cache'});
          if(!response.ok)throw new Error('距离场读取失败：'+item.url);
          const values=new Int16Array(await response.arrayBuffer());
          if(values.length!==axis.resolution**3)throw new Error('距离场尺寸不匹配：'+item.url);
          return values;
        }));
        const mc=new MarchingCubes(axis.resolution,new MeshStandardMaterial(),false,false,150000);
        mc.isolation=0;
        engines[side]=mc;
      }));
      self.postMessage({type:'ready'});
    } else if(data.type === 'blend') {
      const start=performance.now(),meshes=[],transfer=[];
      for(const side of ['left','right']) {
        const mc=engines[side],lo=fields[side][data.a],hi=fields[side][data.b],f=data.f;
        for(let i=0;i<mc.field.length;i++)mc.field[i]=(lo[i]*(1-f)+hi[i]*f)*config.distanceScale;
        mc.normal_cache.fill(0);
        mc.update();
        if(mc.count===0||mc.count>mc.positionArray.length/3)throw new Error('插值表面为空或超出网格容量');
        let positions=mc.positionArray.slice(0,mc.count*3),normals=mc.normalArray.slice(0,mc.count*3);
        if(side==='right'&&data.a===3&&data.b===4)({positions,normals}=mainSurface(positions,normals));
        meshes.push({side,positions,normals});
        transfer.push(positions.buffer,normals.buffer);
      }
      self.postMessage({type:'mesh',id:data.id,a:data.a,b:data.b,f:data.f,meshes,milliseconds:performance.now()-start},transfer);
    }
  } catch(error) {self.postMessage({type:'error',message:error.message});}
};
