"""Node adapter to the same geometry/semantic kernel used during browser edits."""
import json,subprocess
from common import SHARED

def evaluate(layout, action='compile'):
    result=subprocess.run(['node',str(SHARED/'runtime/model-kernel.js')],input=json.dumps({'action':action,'layout':layout}),capture_output=True,text=True,encoding="utf-8")
    if result.returncode:raise ValueError('Model kernel: '+result.stderr.strip())
    return json.loads(result.stdout)
