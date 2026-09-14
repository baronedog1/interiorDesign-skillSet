#!/usr/bin/env python3
"""Real offline viewer interactions; requires Playwright plus an installed Chromium."""
from pathlib import Path
import argparse,base64,json,os,shutil
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
def main(out:Path):
    out.mkdir(parents=True,exist_ok=True);checks=[]
    def ok(name,actual=True):
        assert actual,name
        checks.append({'name':name,'pass':True})
    with sync_playwright() as p:
        exe=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser')
        args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']
        browser=p.chromium.launch(executable_path=exe,headless=True,args=args)
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];external=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) else None)
        page.set_content((ROOT/'Product_Workbench.html').read_text(encoding='utf8'),wait_until='load')
        page.wait_for_function('window.WORKBENCH_READY===true')
        ok('shared HTML starts without embedded product',page.evaluate('PRODUCT.stats().meshes===0'))
        paths=[ROOT/'expected_outcome/cabinet/cabinet.product.json',ROOT/'expected_outcome/mesh-demo/mesh.product.json',ROOT/'expected_outcome/mesh-demo/mesh.glb']
        page.locator('#files').set_input_files([str(v) for v in paths]);page.wait_for_function('window.PRODUCT_READY===true',timeout=90000)
        ok('one HTML accepts two product definitions',page.locator('#catalog option').count()==2)
        ok('cabinet actual default mesh count',page.evaluate('PRODUCT.stats().meshes===17'))
        page.locator('#stage').screenshot(path=str(out/'cabinet.png'))
        page.locator('[data-tab=params]').click();page.locator('#parameter-width').fill('1000');page.locator('#parameter-width').press('Tab');page.wait_for_function('PRODUCT.spec.values.width===1000')
        ok('changing width keeps side thickness 18mm',page.evaluate('ProductKernel.solve(PRODUCT.spec).parts.find(p=>p.id==="side-left").size_mm[0]===18'))
        page.locator('#parameter-variant').select_option('open');page.wait_for_function('PRODUCT.stats().meshes===13');ok('switch to open changes actual geometry')
        page.locator('#parameter-variant').select_option('drawers');page.wait_for_function('PRODUCT.spec.values.variant==="drawers"');ok('drawers contain drawer geometry',page.evaluate('PRODUCT.meshes.some(m=>m.name.includes("drawer"))'))
        page.locator('#parameter-width').fill('0');page.locator('#parameter-width').press('Tab');page.wait_for_timeout(100);ok('invalid parameter leaves last valid state',page.evaluate('PRODUCT.spec.values.width===1000'))
        with page.expect_download() as dl:page.locator('#saveProduct').click()
        saved=out/'cabinet-edited.product.json';dl.value.save_as(saved);ok('save JSON contains edited parameters',json.loads(saved.read_text())['values']['width']==1000)
        with page.expect_download() as dl:page.locator('#exportGLB').click()
        exported=out/'cabinet-edited.glb';dl.value.save_as(exported);ok('real binary GLB exported',exported.read_bytes()[:4]==b'glTF')
        page.locator('#catalog').select_option('1');page.wait_for_function('PRODUCT.spec.id==="mesh-demo"',timeout=120000)
        ok('3 synthetic meshes and 2 assembly groups loaded',page.evaluate('PRODUCT.stats().meshes===3&&PRODUCT.stats().assemblies===2'))
        page.locator('#stage').screenshot(path=str(out/'mesh-demo.png'))
        page.locator('[data-tab=parts]').click()
        page.evaluate('PRODUCT.choose(PRODUCT.meshes.find(m=>m.userData.assembly==="group-a"))')
        count=page.evaluate('PRODUCT.meshes.filter(m=>m.userData.assembly==="group-a").length')
        page.locator('#moveX').fill('100');page.locator('#moveX').press('Tab')
        ok('assembly-linked displacement reaches all members',page.evaluate('PRODUCT.meshes.filter(m=>m.userData.assembly==="group-a").every(m=>PRODUCT.spec.edits[m.userData.partId].offset_mm[0]===100)'))
        page.locator('#selectedRough').fill('0.75');page.locator('#selectedRough').press('Tab')
        ok('material factor applies to linked meshes',page.evaluate('PRODUCT.meshes.filter(m=>m.userData.assembly==="group-a").every(m=>Math.abs(m.material.roughness-.75)<1e-6)'))
        page.locator('#isolate').click();ok('isolate is actual visible subset',page.evaluate('PRODUCT.stats().visible')==count)
        with page.expect_download() as dl:page.locator('#exportGLB').click()
        isolate=out/'mesh-demo-component.glb';dl.value.save_as(isolate)
        data=page.evaluate('async()=>{const a=await PRODUCT.exportGLB(false);const result=await ProductGLB.load(a.buffer);let n=0;result.root.traverse(o=>{if(o.isMesh)n++;});return {count:n,docMeshes:result.doc.meshes.length,rough:result.doc.materials[0].pbrMetallicRoughness.roughnessFactor,ids:result.doc.meshes.map(m=>m.extras.part_id)};}')
        ok('re-import exported subset without hidden full mesh-demo',data['count']==count and data['docMeshes']==count)
        ok('re-export keeps material and part IDs',data['rough']==.75 and all(data['ids']))
        page.locator('#showall').click();page.locator('#explode').fill('65');page.locator('#explode').dispatch_event('input');page.locator('#stage').screenshot(path=str(out/'exploded.png'));ok('explode rendering completed',page.evaluate('PRODUCT.stats().glError===0'))
        page.locator('#catalog').select_option('0');page.wait_for_function('PRODUCT.spec.id==="cabinet-32-system"');ok('switching products retains earlier parameters',page.evaluate('PRODUCT.spec.values.width===1000&&PRODUCT.spec.values.variant==="drawers"'))
        page.locator('#files').set_input_files(str(saved));page.wait_for_function('PRODUCT.spec.id==="cabinet-32-system"&&PRODUCT.spec.values.width===1000');ok('saved JSON reopens with exact current width')
        page.locator('#files').set_input_files(str(isolate));page.wait_for_function('PRODUCT.spec.id.startsWith("import-")');ok('raw static GLB path works',page.evaluate('PRODUCT.stats().meshes')==count)
        page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(200);ok('mobile viewport no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=390'))
        ok('no external network request',not external);ok('no uncaught JavaScript error',not errors)
        browser.close()
    report={'ok':True,'checks':checks,'passed':len(checks),'browser':'Chromium / WebGL2 software-rendered','navigation':'set_content of actual delivered HTML; file:// and Windows double-click not tested','external_requests':external,'javascript_errors':errors,'blender_tested':False}
    (out/'browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False,indent=2));return report
if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',type=Path,required=True);main(a.parse_args().out)
