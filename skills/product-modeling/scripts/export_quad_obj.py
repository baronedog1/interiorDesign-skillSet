#!/usr/bin/env python3
"""Export preserved four-sided source faces to OBJ, X-right/Y-up/+Z-front; no fake PBR."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np

def export(source:Path,out:Path)->dict:
    out.parent.mkdir(parents=True,exist_ok=True)
    with np.load(source,allow_pickle=False) as z:
        info=json.loads(z['metadata_json'].tobytes().decode('utf8'))
        # Metadata may be a top-level list or an object with a meshes list.
        parts=info if isinstance(info,list) else info['meshes']
        vo=uo=0;faces=0
        with out.open('w',encoding='utf8') as f:
            f.write('# Preserved polygons; source Z-up converted to Y-up. Units: meters.\n')
            for i,part in enumerate(parts):
                key=f'p{i:03d}_';v=z[key+'v'];n=z[key+'n'];uv=z[key+'uv'];idx=z[key+'f'];counts=z[key+'fc'];uv_idx=z[key+'fu']
                f.write('o '+part['name'].replace(' ','_')+'\n')
                f.write('g '+str(part.get('assembly','parts')).replace(' ','_')+'\n')
                for x,y,h in v:f.write(f'v {x:.8g} {h:.8g} {-y:.8g}\n')
                for x,y,h in n:f.write(f'vn {x:.8g} {h:.8g} {-y:.8g}\n')
                for u,t in uv:f.write(f'vt {u:.8g} {t:.8g}\n')
                off=0
                for c in counts:
                    c=int(c);vs=idx[off:off+c];us=uv_idx[off:off+c];off+=c
                    f.write('f '+' '.join(f'{int(a)+vo+1}/{int(b)+uo+1}/{int(a)+vo+1}' for a,b in zip(vs,us))+'\n');faces+=1
                vo+=len(v);uo+=len(uv)
    return {'objects':len(parts),'vertices':vo,'polygons':faces,'output':str(out),'pbr_note':'Use companion GLB for full materials.'}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    print(json.dumps(export(a.source,a.out),ensure_ascii=False,indent=2))
