#!/usr/bin/env python3
"""Serial task timing: start/end analysis steps or run one command (no shell)."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import time
import uuid


def append(path, event):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + '\n')


@contextmanager
def timed(name, category='tool', **details):
    """Opt-in internal telemetry via INVEST_LOG; elapsed uses monotonic clock."""
    path = os.environ.get('INVEST_LOG')
    start = time.perf_counter()
    event = dict(id=uuid.uuid4().hex, step=name, category=category,
                 started_at=datetime.now().astimezone().isoformat(), details=details)
    if path:
        append(path, dict(event, event='start'))
    try:
        yield details
    except BaseException as exc:
        details['error'] = str(exc)
        raise
    finally:
        if path:
            append(path, dict(event, event='end', ended_at=datetime.now().astimezone().isoformat(),
                              elapsed_seconds=round(time.perf_counter()-start, 6)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('start', 'end'):
        p = sub.add_parser(action)
        p.add_argument('step')
        p.add_argument('--category', default='analysis')
    run = sub.add_parser('run')
    run.add_argument('--step', required=True)
    run.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == 'run':
        command = args.command
        if command and command[0] == '--':
            command = command[1:]
        if not command:
            parser.error('run 需要命令')
        os.environ['INVEST_LOG'] = str(args.log.resolve())
        with timed(args.step, command=command) as details:
            details['returncode'] = subprocess.call(command)
        return details['returncode']
    events = [json.loads(line) for line in args.log.read_text(encoding='utf-8').splitlines()] if args.log.exists() else []
    ended = {e['id'] for e in events if e['event'] == 'end'}
    active = [e for e in events if e['event'] == 'start' and e['id'] not in ended and e['step'] == args.step]
    now = datetime.now().astimezone()
    if args.action == 'start':
        if active:
            parser.error('步骤已经开始；先结束或使用不同步骤名')
        append(args.log, dict(event='start', id=uuid.uuid4().hex, step=args.step,
                             category=args.category, started_at=now.isoformat()))
    else:
        if not active:
            parser.error('没有对应的未结束步骤')
        event = active[-1]
        append(args.log, dict(event, event='end', ended_at=now.isoformat(),
                             elapsed_seconds=(now-datetime.fromisoformat(event['started_at'])).total_seconds(),
                             clock='wall; 跨进程人工步骤，包含等待，不代表纯思考时间'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
