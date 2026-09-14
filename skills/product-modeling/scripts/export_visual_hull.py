#!/usr/bin/env python3
"""Export the immutable carved geometry into the shared product workbench format."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import trimesh
from mask_utils import canonical_sha256

def export(state_path,out,mm_per_unit):
    state=json.loads(state_path.read_text())
    if state.get('stateSha256')!=canonical_sha256(state,{'stateSha256'}):raise ValueError('State hash mismatch')
    if mm_per_unit<=0:raise ValueError('Measured millimetres per world unit must be positive')
    scene=trimesh.Scene();groups=[]
    for c in state['components']:
        # Carving uses X width/Y depth/Z height; glTF uses X width/Y height/Z depth.
        xyz=np.asarray(c['mesh']['positions']).reshape(-1,3)[:,[0,2,1]]*mm_per_unit/1000
        faces=np.asarray(c['mesh']['indices']).reshape(-1,3)[:,[0,2,1]]
        mesh=trimesh.Trimesh(vertices=xyz,faces=faces,process=False)
        color=c['material'].get('color','#c0b8a8')
        if len(color)==4:color='#'+''.join(v*2 for v in color[1:])
        rgba=[int(color[i:i+2],16) for i in (1,3,5)]+[255]
        mesh.visual=trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(baseColorFactor=rgba))
        scene.add_geometry(mesh,node_name=c['componentId'],geom_name=c['componentId']);groups.append({'id':c['componentId'],'label':c['label']})
    out.mkdir(parents=True,exist_ok=True);(out/'model.glb').write_bytes(scene.export(file_type='glb'))
    spec={'format':'product-modeling','schemaVersion':1,'id':state['planId'],'name':'多视图还原产品','revision':'1','mode':'mesh','model':'model.glb','overview':'从唯一视觉体导出的部件网格；修改后需重新验收原视图。','source':{'reference':state_path.name,'status':state['status'],'stateSha256':state['stateSha256'],'mm_per_unit':mm_per_unit,'notes':['源世界单位由用户尺寸登记；隐藏结构按原状态推定。']},'parameters':{},'assemblies':groups,'materials':{},'parts':[]}
    dest=out/'carved.product.json';dest.write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n');return dest
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('state',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--mm-per-unit',type=float,required=True);a=p.parse_args();print(export(a.state,a.out,a.mm_per_unit))
