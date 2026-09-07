"""Append-only local timing. Wall timestamps identify events; monotonic clocks measure work.
Never logs argv, prompts, credentials or exception text. Parent/child spans overlap.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
import json, os, sys, time, uuid

_parent = ContextVar('timing_parent', default=None)
_log = ContextVar('timing_log', default=None)

def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

def emit(row):
    path = _log.get()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')
        f.flush()

@contextmanager
def span(step, kind='code', **identity):
    record = dict(schema='interior.timing/1', spanId=uuid.uuid4().hex,
                  parentSpanId=_parent.get(), step=step, kind=kind,
                  startedAt=now(), **identity)
    clock = time.perf_counter()
    emit(dict(record, event='start'))
    token = _parent.set(record['spanId'])
    try:
        yield record
        record['status'] = 'succeeded'
    except BaseException as exc:
        record['status'] = 'succeeded' if isinstance(exc, SystemExit) and exc.code in (0, None) else 'failed'
        if record['status'] == 'failed':
            record['errorType'] = type(exc).__name__
        raise
    finally:
        record.update(finishedAt=now(), elapsedMs=round((time.perf_counter()-clock)*1000, 3))
        emit(dict(record, event='finish'))
        _parent.reset(token)

def traced(step):
    def wrap(fn):
        @wraps(fn)
        def call(*args, **kwargs):
            with span(step):
                return fn(*args, **kwargs)
        return call
    return wrap

@contextmanager
def command(skill):
    args = sys.argv[1:]
    out = None
    for flag in ['--out', '--receipt', '--binding']:
        if flag in args and args.index(flag)+1 < len(args):
            out = Path(args[args.index(flag)+1]).resolve()
            break
    root = (out.parent if out.suffix else out) if out else Path.cwd()
    if skill=='booklet-production' and out:root=out.parent
    path = Path(os.environ['INTERIOR_TIMING_LOG']) if os.environ.get('INTERIOR_TIMING_LOG') else root/'timing.jsonl'
    token = _log.set(path)
    try:
        with span(skill + '.' + (args[0] if args else 'help')):
            yield
    finally:
        _log.reset(token)

def main():
    """Persist start/end around Agent reading, review, native calls or delivery waits."""
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','finish'])
    p.add_argument('--record',required=True);p.add_argument('--step');p.add_argument('--kind',default='agent')
    p.add_argument('--status',default='succeeded',choices=['succeeded','failed','cancelled'])
    a=p.parse_args();path=Path(a.record)
    if a.action=='start':
        if path.exists():raise ValueError('Use a new timing record for each attempt')
        row=dict(schema='interior.timing/1',spanId=uuid.uuid4().hex,step=a.step,kind=a.kind,startedAt=now(),status='running')
    else:
        row=json.loads(path.read_text(encoding='utf8'))
        if row.get('finishedAt'):raise ValueError('This attempt already has a completion time')
        row.update(finishedAt=now(),status=a.status)
        row['elapsedMs']=round((datetime.fromisoformat(row['finishedAt'])-datetime.fromisoformat(row['startedAt'])).total_seconds()*1000,3)
        row['clock']='wall-clock-across-processes'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(row,ensure_ascii=False))

if __name__=='__main__':main()
