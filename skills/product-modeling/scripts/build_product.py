#!/usr/bin/env python3
"""Evaluate one product, build GLB and a same-source PDF; never copy the shared viewer."""
from __future__ import annotations
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
import numpy as np
import trimesh
from product_manual import make_product_manual
ROOT=Path(__file__).resolve().parents[1]
def evaluate(path:Path):
    p=subprocess.run(['node',str(ROOT/'scripts/evaluate.cjs'),str(path)],capture_output=True,text=True,encoding='utf8')
    if p.returncode:raise ValueError(p.stderr.strip())
    return json.loads(p.stdout)
def safe_resource(base:Path,name:str):
    p=(base/name).resolve()
    if not p.is_relative_to(base.resolve()) or not p.is_file():raise ValueError('产品资源缺失或路径越界：'+name)
    return p

def build(path:Path,out:Path,preview:Path|None=None):
    path=path.resolve();out=out.resolve();out.mkdir(parents=True,exist_ok=True)
    spec=json.loads(path.read_text(encoding='utf8'));data=evaluate(path)
    if spec['mode']=='parametric':
        scene=trimesh.Scene()
        for p in data['parts']:
            dims=np.array(p['size_mm'])/1000
            if p['primitive']=='box':m=trimesh.creation.box(extents=dims)
            elif p['primitive']=='sphere':m=trimesh.creation.icosphere(subdivisions=3,radius=dims[0]/2)
            else:
                m=trimesh.creation.revolve([[0,-dims[1]/2],[dims[2]/2,-dims[1]/2],[dims[0]/2,dims[1]/2],[0,dims[1]/2]],sections=32)
                m.apply_transform(trimesh.transformations.rotation_matrix(-np.pi/2,[1,0,0]))
            m.apply_translation(np.array(p['position_mm'])/1000)
            mat=data['materials'][p['material']];hexcolor=data['values'].get(mat.get('colorParameter'),mat.get('color','#bba98e'))
            color=[int(hexcolor[i:i+2],16) for i in [1,3,5]]+[255]
            m.visual=trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(name=mat.get('label',p['material']),baseColorFactor=color,roughnessFactor=data['values'].get(mat.get('roughnessParameter'),mat.get('roughness',.5)),metallicFactor=mat.get('metalness',0)))
            e=spec.get('edits',{}).get(p['id'],{})
            if e.get('hidden'):continue
            if e.get('offset_mm'):m.apply_translation(np.array(e['offset_mm'])/1000)
            if e.get('color'):m.visual.material.baseColorFactor=[int(e['color'][i:i+2],16) for i in [1,3,5]]+[255]
            if 'roughness' in e:m.visual.material.roughnessFactor=e['roughness']
            m.metadata.update(part_id=p['id'],assembly=p['assembly']);scene.add_geometry(m,node_name=p['id'],geom_name=p['id'])
        if not scene.geometry:raise ValueError('没有可导出的可见部件')
        model=out/'model.glb';model.write_bytes(scene.export(file_type='glb'))
        data['bounds_mm']=(scene.extents*1000).tolist()
    else:
        model=safe_resource(path.parent,spec['model']);target=out/spec['model'];target.parent.mkdir(parents=True,exist_ok=True)
        if model!=target:shutil.copyfile(model,target)
        scene=trimesh.load(model,force='scene');data['bounds_mm']=(scene.extents*1000).tolist()
        # Do not pretend this copies browser mesh deformations into the GLB.
        if any(v!=1 for k,v in data['values'].items() if k.startswith('scale_')) or spec.get('edits'):
            raise ValueError('已有网格的编辑结果请先从工作台导出GLB并更新model；脚本不会把未烘焙修改伪装成新模型。')
        for key in ['mesh_source']:
            if spec.get(key):
                src=safe_resource(path.parent,spec[key]);dst=out/spec[key];dst.parent.mkdir(parents=True,exist_ok=True)
                if src!=dst:shutil.copyfile(src,dst)
    dst=out/path.name
    if path!=dst:shutil.copyfile(path,dst)
    (out/'evaluated.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    make_product_manual(dst,data,out/'PRODUCT_MANUAL.pdf',preview)
    files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.rglob('*') if p.is_file() and p.name!='PRODUCT_MANIFEST.json'}
    (out/'PRODUCT_MANIFEST.json').write_text(json.dumps({'id':spec['id'],'revision':spec.get('revision'),'files':files,'manufacturing_verified':False,'blender_tested':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return {'id':spec['id'],'parts':len(data['parts']),'output':str(out),'product_definition':dst.name}
if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('product',type=Path);a.add_argument('--out',type=Path,required=True);a.add_argument('--preview',type=Path);args=a.parse_args()
    try:print(json.dumps(build(args.product,args.out,args.preview),ensure_ascii=False,indent=2))
    except (ValueError,OSError,subprocess.SubprocessError) as e:print(str(e),file=sys.stderr);sys.exit(2)
