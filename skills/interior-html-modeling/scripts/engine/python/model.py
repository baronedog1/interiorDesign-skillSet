"""Build the single offline studio from layout JSON and the pinned shared runtime."""
from __future__ import annotations
import json,re,math
from pathlib import Path
from common import SHARED,read,write,digest,file_sha,canonical,runtime_identity,atomic_bytes,resources
from validate import validate_layout
from cameras import generic_presets,corners
from timing import traced
SCRIPTS=['three-r164.js','materials.js','styles.js','geometry.js','architecture-kit.js','components-base.js','style-components.js','components.js','scene.js','exporter.js','optimization.js','controls.js','lights.js','spatial.js','native-assets.js','workspace.js','app.js']
def js_json(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
def shell():
    text=(SHARED/'runtime/studio.html').read_text(encoding='utf-8-sig');catalog,styles=resources()
    scripts=[]
    for name in SCRIPTS:
        src=(SHARED/'runtime'/name).read_text(encoding='utf-8-sig')
        if re.search('</script',src,re.I):raise ValueError('Inline script closing tag in '+name)
        scripts.append('<script>\n'+src+'\n</script>')
    return text.replace('__RUNTIME_SCRIPTS__','\n'.join(scripts)).replace('__COMPONENT_JSON__',js_json(catalog)).replace('__STYLE_JSON__',js_json(styles))
@traced('model.compile')
def build_model(layout_path,out_dir,presets_path=None,style_id=None):
    layout=read(layout_path)
    if style_id:
        import copy
        catalog=resources()[1]['styles']
        original=layout.get('customStyle') or next(x for x in catalog if x['id']==layout['styleId'])
        target=copy.deepcopy(next(x for x in catalog if x['id']==style_id))
        target['forms']=copy.deepcopy(original['forms']);target['lighting']=copy.deepcopy(original['lighting'])
        layout['styleId']=style_id
        layout['customStyle']=target
    from styles import validate_style
    _,catalog=resources();style=layout.get('customStyle') or next((x for x in catalog['styles'] if x['id']==layout['styleId']),None)
    if style and style['id']!=layout['styleId']:raise ValueError('Custom style id mismatch')
    if not style:raise ValueError('Unknown styleId')
    validate_style(style)
    report=validate_layout(layout,strict=True);out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    presets=generic_presets(layout)
    if presets_path:
        supplied=read(presets_path)
        for k,v in supplied.items():
            if not isinstance(v,dict) or not all(x in v for x in ['title','pos','target','fov']):raise ValueError('Invalid preview preset '+k)
            if any(len(v[x])!=3 or not all(isinstance(a,(int,float)) and not isinstance(a,bool) and math.isfinite(a) for a in v[x]) for x in ['pos','target']):raise ValueError('Invalid preview camera vector')
            if math.dist(v['pos'],v['target'])<.05:raise ValueError('Preview position and target coincide')
            if not 20<=v['fov']<=100:raise ValueError('Invalid preview FOV')
        presets.update(supplied)
    editor_path=Path(layout_path).with_suffix('.editor.json')
    editor=read(editor_path) if editor_path.exists() else None
    runtime_hash=runtime_identity();key=digest({'layout':digest(layout),'runtime':runtime_hash,'presets':presets,'editorState':editor})
    html=shell().replace('__PROJECT_JSON__',js_json(layout)).replace('__PRESETS_JSON__',js_json(presets)).replace('__SCENE_KEY_JSON__',js_json(key)).replace('__STRUCTURE_KEY_JSON__',js_json(digest({k:layout[k] for k in ['floor','walls','openings','rooms','openConnections']})))
    if editor:
        # Existing editor import owns camera, view and display restoration. Store data, never execute source HTML.
        editor['layout']=layout;editor['styleRecipe']=style
        html=html.replace('<script>','<script type="application/json" id="saved-project" data-compiled>'+js_json(editor)+'</script>\n<script>',1)
    atomic_bytes(out/'model.html',html.encode('utf-8'));write(out/'layout.json',layout)
    scene={'schema':'interior.scene/1','sceneKey':key,'layoutHash':digest(layout),'runtimeHash':runtime_hash,'htmlFile':'model.html','htmlSha256':file_sha(out/'model.html'),'layoutFile':'layout.json','layout':layout,'presets':presets,'boxAuthority':'normalized-component-footprints','entities':[{'id':p['id'],'componentId':p['componentId'],'roomId':p['roomId'],'corners':corners(p)} for p in layout['placements']]}
    if editor:scene['editorState']=editor
    write(out/'scene.json',scene);write(out/'layout-check.json',report);return scene
