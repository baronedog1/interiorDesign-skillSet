#!/usr/bin/env python3
"""Optional loopback-only server for auto-loading product URLs; no network publication."""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path
import argparse
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=8765);a=p.parse_args()
root=Path(__file__).resolve().parents[1]
url=f'http://127.0.0.1:{a.port}/Product_Workbench.html?product=expected_outcome/cabinet/cabinet.product.json'
print(url,flush=True)
ThreadingHTTPServer(('127.0.0.1',a.port),partial(SimpleHTTPRequestHandler,directory=str(root))).serve_forever()
