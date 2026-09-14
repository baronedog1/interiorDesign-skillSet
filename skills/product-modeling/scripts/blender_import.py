"""Run with blender --background --python blender_import.py -- MODEL.glb OUT.blend.
This is a static GLB import/save helper, not recovery of modifiers or design history.
"""
from pathlib import Path
import sys

def main():
    import bpy
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    if len(args)!=2:raise SystemExit('需要输入GLB和输出.blend两个路径')
    src,out=map(lambda s:Path(s).resolve(),args)
    if src.suffix.lower()!='.glb' or not src.is_file():raise SystemExit('输入GLB不存在')
    if out.suffix.lower()!='.blend':raise SystemExit('输出必须为.blend')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(src))
    count=sum(o.type=='MESH' for o in bpy.data.objects)
    if not count:raise RuntimeError('未导入网格')
    bpy.context.scene.unit_settings.system='METRIC'
    out.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    bpy.ops.wm.open_mainfile(filepath=str(out))
    if sum(o.type=='MESH' for o in bpy.data.objects)!=count:raise RuntimeError('重开网格数量变化')
    print('BLEND_REOPEN_OK',count,str(out))
if __name__=='__main__':main()
