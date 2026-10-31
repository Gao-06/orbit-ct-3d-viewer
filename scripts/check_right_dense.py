import json
import numpy as np
from build_eye_fields import ROOT,surface_from_field,mesh_stats
p=ROOT/'web/aligned_scene';c=json.loads((p/'morph.json').read_text());a=c['axes']['right'];n=a['resolution'];fs=[np.fromfile(ROOT/x['url'],dtype='<i2').reshape((n,)*3).astype(float) for x in a['fields'][3:]]
checks=[]
for j in range(101):
 f=j/100;st=mesh_stats(surface_from_field((fs[0]*(1-f)+fs[1]*f)*.01,a['origin'],a['spacingMm']));checks.append(dict(fraction=f,**st))
(p/'qa/right_dense_checks.json').write_text(json.dumps(checks,indent=2));bad=[x for x in checks if x['components']!=1 or x['boundaryOrNonManifoldEdges']];print('101 frames; bad:',len(bad));print([(x['fraction'],x['components']) for x in bad])
