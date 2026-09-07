"""Validate or explicitly install a style recipe. No auto-downloaded assets or code execution."""
from common import read,write,resources,require_schema,SHARED
ROLES={'plaster','cream','porcelain','oak','walnut','travertine','linen','boucle','sand','clay','sage','rug','bronze','black','mirror','glass','sheer','leaf','leaf2','soil','dark','led','screen','white'}
def validate_style(recipe):
    require_schema(recipe,'style.schema.json')
    if set(recipe['materialRecipes'])-ROLES:raise ValueError('Unknown material role')
    return {'ok':True,'styleId':recipe['id'],'name':recipe['name'],'forms':recipe['forms']}
def add_style(path):
    recipe=read(path);result=validate_style(recipe);catalog=read(SHARED/'catalog/styles.json')
    if any(s['id']==recipe['id'] for s in catalog['styles']):raise ValueError('A style with that id exists; choose a new id')
    catalog['styles'].append(recipe);write(SHARED/'catalog/styles.json',catalog)
    folder=SHARED/'styles'/recipe['id'];folder.mkdir(parents=True,exist_ok=True)
    (folder/'PLAYBOOK.md').write_text('# '+recipe['name']+'\n\n'+'\n\n'.join('## '+k+'\n\n'+v for k,v in recipe['playbook'].items()),encoding='utf-8')
    return result

def resolve_style(query):
    """Resolve known presets, otherwise ask the host research capability; no silent fallback."""
    _,catalog=resources();q=query.strip().casefold()
    if not q:raise ValueError('Style query is empty')
    recipe=next((s for s in catalog['styles'] if q in [s['id'].casefold(),s['name'].casefold(),s.get('englishName','').casefold()]),None)
    if recipe:return {'ok':True,'status':'resolved','recipe':recipe}
    return {'ok':True,'schema':'interior.style-research/1','query':query,'status':'research-required','queries':[query+' interior design materials furniture lighting',query+' 室内设计 材料 配色 家具'],'requiredFacts':['palette','materials','forms','details','lighting','componentBindings'],'sources':[],'note':'由当前Agent真实联网查证，逐源记录URL、日期和支持结论；无法检索时保持此状态，不回退奶油风。'}

def check_evidence(recipe):
    from urllib.parse import urlsplit
    from datetime import datetime
    validate_style(recipe);e=recipe.get('evidence')
    if not e or not e.get('sources'):raise ValueError('Unknown style needs actual research evidence; empty URLs are not verification')
    datetime.fromisoformat(e['retrievedAt'].replace('Z','+00:00'))
    for s in e['sources']:
        u=urlsplit(s['url'])
        if u.scheme!='https' or not u.netloc or not s.get('supports'):raise ValueError('Invalid source evidence')
    return {'ok':True,'styleId':recipe['id'],'sources':len(e['sources']),'evidenceStatus':'recorded-host-research-not-independently-fetched'}
