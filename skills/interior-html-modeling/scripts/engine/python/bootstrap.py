"""Use the dedicated Windows environment, without mutating device Python defaults."""
import os,sys
from pathlib import Path
def ensure_runtime():
    target=Path(r'C:\ProgramData\GCPManager\runtimes\interior-design-gpt6-v2\Scripts\python.exe')
    if sys.platform=='win32' and target.is_file() and Path(sys.executable).resolve()!=target.resolve():
        os.execv(str(target),[str(target),'-X','utf8',*sys.argv])
