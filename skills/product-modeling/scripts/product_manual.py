#!/usr/bin/env python3
"""Generate the product's PDF from the same definition/evaluated parts used by the viewer."""
from pathlib import Path
from xml.sax.saxutils import escape
import json,hashlib
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
STYLE={
 'h1':ParagraphStyle('h1',fontName='STSong-Light',fontSize=27,leading=36,spaceAfter=14,textColor=colors.HexColor('#253d49')),
 'h2':ParagraphStyle('h2',fontName='STSong-Light',fontSize=17,leading=24,spaceAfter=10,textColor=colors.HexColor('#253d49')),
 'body':ParagraphStyle('body',fontName='STSong-Light',fontSize=10.5,leading=17,spaceAfter=7,wordWrap='CJK'),
 'small':ParagraphStyle('small',fontName='STSong-Light',fontSize=8.5,leading=13,wordWrap='CJK'),
}
def para(s,style='body'):return Paragraph(escape(str(s)).replace('\n','<br/>'),STYLE[style])
def table(rows,widths):
    t=Table([[para(c,'small') for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5ebec')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#dce0df'))]));return t

def make_product_manual(source:Path,evaluated:dict,out:Path,preview:Path|None=None):
    raw=source.read_bytes();spec=json.loads(raw);out.parent.mkdir(parents=True,exist_ok=True)
    story=[para('PRODUCT / MODEL MANUAL','small'),Spacer(1,18),para(spec['name'],'h1'),para('产品说明书 · '+str(spec.get('revision','未指定修订')),'h2'),para(spec.get('overview',''))]
    if preview and preview.is_file():
        from PIL import Image as PILImage
        with PILImage.open(preview) as im:w,h=im.size
        story.extend([Spacer(1,10),Image(str(preview),width=495,height=495*h/w),Spacer(1,10)])
    story+=[para('产品ID：'+spec['id']),para('源码摘要 SHA256：'+hashlib.sha256(raw).hexdigest(),'small'),para('当前模式：'+('声明式结构重算' if spec['mode']=='parametric' else '已有分件网格；比例修改是近似变形')),para('本说明书由产品JSON与同一计算内核生成，不是生产加工图纸。'),PageBreak(),para('01 / 来源、尺度与边界','h1')]
    src=spec.get('source',{})
    for k,v in src.items():story.append(para(k+'：'+('\n'.join(v) if isinstance(v,list) else str(v))))
    if evaluated.get('bounds_mm'):story.append(para('本次几何包络（宽×高×深，mm）：'+' × '.join(f'{x:.2f}' for x in evaluated['bounds_mm'])))
    for s in spec.get('limits',[]):story.append(para('限制：'+s))
    story+=[PageBreak(),para('02 / 组成、分件与装配','h1')]
    groups={a['id']:a.get('label',a['id']) for a in spec.get('assemblies',[])}
    story.append(para(f"当前款式共 {len(evaluated['parts'])} 个定义部件；下表只列本次有效款式，不把互斥门/抽屉同时计入。"))
    rows=[['零件ID / 名称','组件 / 材质','尺寸（mm）或性质']]
    for p in evaluated['parts']:
        size=p.get('size_mm');dim=' × '.join(f'{v:.1f}' for v in size) if size else '已有曲面网格；见源文件'
        rows.append([p['id']+'\n'+p.get('label',''),groups.get(p.get('assembly'),p.get('assembly',''))+'\n'+p.get('material',''),dim])
    story.append(table(rows,[215,125,155]))
    story+=[Spacer(1,14),para('装配方法','h2')]
    for i,s in enumerate(spec.get('assembly_steps',[]),1):story.append(para(f'{i}. {s}'))
    story+=[PageBreak(),para('03 / 款式与可以调整的部分','h1')]
    rows=[['参数 / 当前值','可选范围','作用与限制']]
    for k,d in spec.get('parameters',{}).items():
        if d['type']=='number':rg=f"{d['min']}–{d['max']} {d.get('unit','')}"
        elif d['type']=='enum':rg=' / '.join(o if isinstance(o,str) else o.get('label',o['value']) for o in d['options'])
        else:rg='HEX颜色'
        rows.append([d.get('label',k)+'\n'+str(evaluated['values'][k]),rg,d.get('effect','')])
    story.append(table(rows,[145,145,205]))
    if spec.get('edits'):story.extend([Spacer(1,15),para('已保存的部件编辑','h2'),para(json.dumps(spec['edits'],ensure_ascii=False,indent=2),'small')])
    story+=[PageBreak(),para('04 / 材料、表面与连接','h1')]
    for k,m in spec.get('materials',{}).items():story.append(para(k+'：'+json.dumps(m,ensure_ascii=False)))
    if spec['mode']=='mesh':story.append(para('材质与纹理以内嵌GLB为准。颜色、金属度、粗糙度、法线等是外观参数；合成皮纹不是实物扫描，也不能识别皮革成分或涂层工艺。'))
    for row in spec.get('interfaces',[]):story.append(para(json.dumps(row,ensure_ascii=False)))
    story+=[para('节点、网格分组与物理可拆装关系不是同一概念。厂家五金、公差、孔深和承载须独立验证。'),PageBreak(),para('05 / 打开、保存与软件交接','h1')]
    for s in ['打开通用 Product_Workbench.html，选择本产品JSON及同目录模型；也可以一次选择多个产品目录，再通过产品选择器切换。','板式柜从小部件按参数重算；网格产品仅对已明确的比例参数做近似变形。左右手坐标：X宽、Y高、Z深；渲染与GLB采用米，结构参数标注毫米。','选择部件后可隐藏、隔离、分解和移动；联动模式让包边、针脚与所属软包一起移动。默认GLB导出不含分解展示位移，但保留明确的部件编辑位移。','修改后分别保存产品JSON与导出GLB。重新生成PDF时读取保存后的JSON，不以旧说明书解释新模型。','原始GLB与源码应保留。GLB用于静态交换；原生.blend须实际运行Blender构建和重新打开后才算验证。当前包不含已经生成的.blend。','最终文件分为产品源码包、共用HTML和产品PDF。产品包只包含此产品，不复制整套工作台、不夹带其他产品。']:
        story.append(para(s))
    def foot(c,doc):
        c.setStrokeColor(colors.HexColor('#d8dddd'));c.line(48,43,547,43);c.setFont('STSong-Light',8);c.setFillColor(colors.HexColor('#64737a'));c.drawString(48,29,spec['name']+' / '+str(spec.get('revision','')));c.drawRightString(547,29,str(doc.page))
    SimpleDocTemplate(str(out),pagesize=A4,leftMargin=50,rightMargin=50,topMargin=48,bottomMargin=58,title=spec['name']+'产品说明书',author='Product Modeling Skill').build(story,onFirstPage=foot,onLaterPages=foot)
    return out
