#!/usr/bin/env python3
"""Build the one offline HTML from its maintained source files; no product embedding."""
from pathlib import Path
import argparse
ROOT=Path(__file__).resolve().parents[1]
def build(out:Path):
    src=ROOT/'assets/workbench'
    html=(src/'workbench.html').read_text(encoding='utf8')
    js='\n'.join((src/n).read_text(encoding='utf8') for n in ['three-r164.js','product-kernel.js','gltf-io.js','workbench.js'])
    html=html.replace('<!--BUNDLED_SCRIPTS-->','<script>\n'+js.replace('</script','<\\/script')+'\n</script>')
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(html,encoding='utf8');return out
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'Product_Workbench.html');a=p.parse_args();print(build(a.out))
