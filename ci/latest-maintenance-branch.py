#!/usr/bin/env python
import sys
import re
import argparse
import re
import subprocess

p = argparse.ArgumentParser()
p.add_argument('repository')
args = p.parse_args()

lines = subprocess.check_output(['git', 'ls-remote', '--heads', args.repository])
lines = lines.decode(encoding='utf-8', errors='replace')

heads = []
for line in lines.splitlines(True):
    m = re.match('.*\s+refs/heads/(maintenance/.*?)\s+$', line)
    if m:
        branch = m.group(1).strip()
        parts = []
        for p in re.split('[./]', branch):
            try:
                p = int(p)
            except ValueError:
                pass
            parts.append(p)
        heads.append((parts, branch))

heads.sort()
latest = heads[-1]
print(latest[1])
