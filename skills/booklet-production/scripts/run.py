"""Offline editorial booklets; brief values are data, never executable HTML."""
import argparse,base64,hashlib,html,io,json,os,re,time
from pathlib import Path
from PIL import Image,ImageOps
from playwright.sync_api import sync_playwright
import pymupdf

ROOT=Path(__file__).resolve().parents[1]
def esc(x):return html.escape(str(x),quote=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
def picture(image,base,sendable,kind,observations,sources):
 p=(base/image['path']).resolve()
 if not p.is_file():raise ValueError('Missing image: '+str(p))
 with Image.open(p) as src:
  im=ImageOps.exif_transpose(src).convert('RGB');width,height=im.size
  if min(width,height)<700:observations.append({'image':p.name,'issue':'Low source resolution; inspect at print size'})
  im.thumbnail((1600,2000) if sendable else (3000,4000))
  buf=io.BytesIO();im.save(buf,format='JPEG',quality=82 if sendable else 95,optimize=True)
 src='data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()
 sources[str(p)]={'sha256':sha(p),'width':width,'height':height,'role':image.get('role'),'shotId':image.get('shotId'),'source':image.get('source')}
 fit='cover' if image.get('crop') is True and kind=='cover' else 'contain'
 focus=image.get('focus','50% 50%')
 if not re.fullmatch(r'\d{1,3}% \d{1,3}%',focus):raise ValueError('Invalid image focus')
 caption=image.get('caption','');credit=image.get('source','')
 return f'<figure><img alt="{esc(caption)}" src="{src}" style="object-fit:{fit};object-position:{focus}"><figcaption>{esc(caption)}'+(f' · {esc(credit)}' if credit else '')+'</figcaption></figure>'

def document(brief,base,sendable,observations,sources):
 css=(ROOT/'assets/magazine.css').read_text(encoding='utf8');accent=brief.get('theme',{}).get('accent','#68745c')
 if not re.fullmatch(r'#[0-9a-fA-F]{6}',accent):raise ValueError('Invalid accent')
 pages=[]
 for n,p in enumerate(brief['pages'],1):
  kind=p['kind']
  if kind not in ['cover','plan','story','full','gallery','materials','closing']:raise ValueError('Unknown page kind')
  if not p.get('layoutReason'):observations.append({'page':n,'issue':'Record why this layout serves its content'})
  images=p.get('images',[])
  if kind not in ['closing','materials'] and not images:observations.append({'page':n,'issue':'No image; stage material missing'})
  if {i.get('role') for i in images}>={'reference','render'}:
   refs={i.get('shotId') for i in images if i.get('role')=='reference'};renders={i.get('shotId') for i in images if i.get('role')=='render'}
   if refs!=renders or None in refs:observations.append({'page':n,'issue':'Reference/render pairing is not the same known shotId; do not label as direct comparison'})
  pics=''.join(picture(i,base,sendable,kind,observations,sources) for i in images)
  body=p.get('body',[])
  if isinstance(body,str):body=[body]
  # Small text units permit measured continuation without truncation or font shrinking.
  paras=[]
  for paragraph in body:
   units=re.findall(r'.{1,120}(?:[。！？；\n]|$)|.{1,120}',str(paragraph),re.S)
   paras.extend('<p>'+esc(u)+'</p>' for u in units)
  sw=[]
  for s in p.get('swatches',[]):
   if not re.fullmatch(r'#[0-9a-fA-F]{6}',s['color']):raise ValueError('Invalid swatch')
   sw.append(f'<div class="swatch"><i style="--sample:{s["color"]}"></i>{esc(s["name"])}</div>')
  heading='h1' if kind=='cover' else 'h2'
  pages.append(f'<section class="page {kind}"><header><span>{esc(brief.get("edition","INTERIOR / 设计提案"))}</span><span>{esc(brief.get("version",""))}</span></header><div><p class="kicker">{esc(p.get("kicker",""))}</p><{heading}>{esc(p["title"])}</{heading}></div><div class="body-zone">'+(f'<div class="pictures">{pics}</div>' if pics else '')+(f'<div class="swatches">{"".join(sw)}</div>' if sw else '')+f'<div class="copy">{"".join(paras)}</div></div><footer class="folio"><span>{esc(brief["title"])}</span><span>{esc(brief.get("status","阶段方案"))} · <b class="page-number"></b></span></footer></section>')
 return '<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(brief['title'])+'</title><style>'+css+':root{--accent:'+accent+'}</style><body>'+''.join(pages)+'</body></html>'

PAGINATE="""() => {
 const original=[...document.querySelectorAll('.page')];
 for(const source of original){let page=source,copy=page.querySelector('.copy'),guard=0;
  while(copy.children.length && copy.lastElementChild.getBoundingClientRect().bottom>page.querySelector('.folio').getBoundingClientRect().top-18){
   if(++guard>100)throw Error('Text pagination failed');
   const next=source.cloneNode(true);next.className='page continuation';next.querySelector('.pictures')?.remove();next.querySelector('.swatches')?.remove();next.querySelector('h1,h2').textContent=source.querySelector('h1,h2').textContent+' · 续';const target=next.querySelector('.copy');target.replaceChildren();
   while(copy.children.length && copy.lastElementChild.getBoundingClientRect().bottom>page.querySelector('.folio').getBoundingClientRect().top-18)target.prepend(copy.lastElementChild);
   page.after(next);page=next;copy=target;
  }
 }
 document.querySelectorAll('.page-number').forEach((el,i)=>el.textContent=String(i+1).padStart(2,'0'));
 return [...document.querySelectorAll('.page')].map((p,i)=>({page:i+1,overflow:[...p.querySelectorAll('.copy p,figure,.swatches,h1,h2')].some(e=>e.getBoundingClientRect().bottom>p.querySelector('.folio').getBoundingClientRect().top-5)}));
}"""

def inspect_pdf(path,out):
 out.mkdir(exist_ok=True);doc=pymupdf.open(path);pages=[]
 for index,page in enumerate(doc):
  pix=page.get_pixmap(matrix=pymupdf.Matrix(1.15,1.15),colorspace=pymupdf.csRGB,alpha=False);pix.save(str(out/f'page-{index+1:02}.png'))
  fonts=[]
  for f in page.get_fonts(full=True):
   embedded=bool(doc.extract_font(f[0])[3]) if f[0] else False;fonts.append({'name':f[3],'embedded':embedded})
  colors=sorted({str(im[5]) for im in page.get_images(full=True)})
  pages.append({'page':index+1,'size':[round(page.rect.width,2),round(page.rect.height,2)],'textCharacters':len(page.get_text()),'fonts':fonts,'imageColors':colors})
 doc.close();return {'pages':pages,'bytes':path.stat().st_size,'sha256':sha(path),'independentReopen':True}

def build(source,out):
 source=Path(source).resolve();out=Path(out).resolve()
 if out.exists() and any(out.iterdir()):raise ValueError('Choose a new output directory; previous deliverables are preserved')
 out.mkdir(parents=True,exist_ok=True);brief=json.loads(source.read_text(encoding='utf8'))
 if brief.get('schema')!='interior.booklet/3' or not brief.get('pages'):raise ValueError('Expected interior.booklet/3 with pages')
 report={'projectId':brief['projectId'],'version':brief['version'],'inputSha256':sha(source),'observations':[],'sources':{},'outputs':{},'nativeGenerationPerformed':False}
 executable=os.environ.get('CHROME_BIN',r'C:\Program Files\Google\Chrome\Application\chrome.exe')
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=executable,headless=True)
  try:
   for mode in ['highres','sendable']:
    page=browser.new_page(viewport={'width':1200,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    path=out/('booklet.html' if mode=='highres' else 'booklet-sendable.html');path.write_text(document(brief,source.parent,mode=='sendable',report['observations'],report['sources']),encoding='utf8')
    page.goto(path.as_uri());page.emulate_media(media='print');page.evaluate('document.fonts.ready');page.wait_for_function('Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)');layout=page.evaluate(PAGINATE)
    path.write_text(page.content(),encoding='utf8');pdf=out/f'booklet-{mode}.pdf';page.pdf(path=str(pdf),print_background=True,prefer_css_page_size=True)
    report['outputs'][mode]={**inspect_pdf(pdf,out/f'preview-{mode}'),'layout':layout,'browserErrors':errors}
    page.emulate_media(media='screen');page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(out/f'mobile-{mode}.png'));report['outputs'][mode]['mobileOverflow']=page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.close()
  finally:browser.close()
 report['observations']=[dict(t) for t in {tuple(sorted(o.items())) for o in report['observations']}]
 write(out/'manifest.json',report);return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('brief');p.add_argument('--out',required=True);a=p.parse_args()
 r=build(a.brief,a.out);print(json.dumps({'pages':len(r['outputs']['highres']['pages']),'observations':r['observations'],'out':a.out},ensure_ascii=False))
