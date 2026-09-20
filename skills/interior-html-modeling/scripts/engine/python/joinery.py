"""Construct an editable cabinet run through the shared browser/Node methods."""
import subprocess,json
from common import read,write,SHARED

def cabinet_run(layout,request,out):
    js="const j=require(process.argv[1]);let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{const v=JSON.parse(s);console.log(JSON.stringify(j.run(v.layout,v.request)));});"
    r=subprocess.run(['node','-e',js,str(SHARED/'runtime/joinery-kernel.js')],input=json.dumps({'layout':read(layout),'request':read(request)}),text=True,capture_output=True,check=True)
    write(out,json.loads(r.stdout));return {'ok':True,'layout':str(out)}
