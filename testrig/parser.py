from __future__ import absolute_import, division, print_function

import sys
import re
import os
import io


def parse_nose(text, cwd):
    failures = {}
    test_count = -1

    state = 'initial'
    name = ''
    message = []

    for line in text.splitlines():
        line = line.rstrip()

        m = re.match('^========+$', line)
        if m:
            if state == 'content':
                failures[name] = "\n".join(message)
            state = 'top-header'
            continue

        m = re.match('^(ERROR|FAIL): (.*)$', line)
        if m and state == 'top-header':
            name = m.group(2).strip()
            message = [line]
            state = 'name'
            continue

        m = re.match('^--------+$', line)
        if m and state == 'name':
            state = 'content'
            message.append(line)
            continue
        elif m and state == 'content':
            failures[name] = "\n".join(message)
            state = 'initial'
            continue

        m = re.match('^Ran ([0-9]+) tests? in .*$', line)
        if m and state == 'initial':
            test_count = int(m.group(1))
            continue

        if state == 'content':
            message.append(line)
            continue

    if test_count < 0:
        err_msg = "ERROR: parsing nose output failed"
    else:
        err_msg = None

    warns = _parse_warnings(text, suite="nose")

    return failures, warns, test_count, err_msg


def parse_pytest_log(text, cwd):
    log_fn = os.path.join(cwd, 'pytest.log')

    if not os.path.isfile(log_fn):
        return {}, -1, "ERROR: log file 'pytest.log' not found"

    failures = {}
    test_count = 0
    err_msg = None

    message = []

    with io.open(log_fn, 'r', encoding='utf-8', errors='replace') as f:
        while True:
            line = f.readline()
            if not line:
                break
            line = line.rstrip("\n")

            if line[:1] in ('F', 'E'):
                test_count += 1
                name = line[1:].strip()
                message = ["-"*79, line]
                failures[name] = message
            elif line.startswith(' '):
                message.append(line[1:])
                continue
            else:
                test_count += 1
                message = []

    for key in list(failures.keys()):
        failures[key] = "\n".join(failures[key])

    # Check the test suite ran to the end
    m = re.match(r'.*in [0-9.,]+ seconds ==\s*$', text, re.S)
    if not m:
        test_count = -1
        err_msg = "ERROR: test suite did not run to the end"

    warns = _parse_warnings(text, suite="pytest")

    return failures, warns, test_count, err_msg


def _parse_warnings(text, suite):
    test_name = ''
    key = None
    w = {}

    for line in text.splitlines():
        line = line.rstrip()

        if suite == 'nose':
            m = re.search(r'^(.*)\s+\.\.\.\s+', line)
            if m:
                key = None
                test_name = m.group(1).strip()
        elif suite == 'pytest':
            m = re.search('^([^\t ]+::test_[^\t ]+)\s+', line)
            if m:
                key = None
                test_name = m.group(1).strip()
        else:
            raise ValueError()

        m = re.search(r'(/.+\.py):(\d+): (.*Warning: .*)$', line)
        if m:
            key = "{0}\n    {1}:{2}".format(m.group(3),
                                            m.group(1),
                                            m.group(2))
            w.setdefault(key, set()).add(test_name)
            continue

        if key is not None and line.startswith('  '):
            items = w[key]
            del w[key]
            key += "\n" + line.rstrip()
            w[key] = items.union(w.get(key, set()))
        else:
            key = None

    for key in list(w.keys()):
        w[key] = "WARNING: {0}\n{1}\n---".format(key, "\n".join(sorted(w[key])))

    return w


def get_parser(name):
    parsers = {'nose': parse_nose,
               'pytest-log': parse_pytest_log}
    try:
        return parsers[name]
    except KeyError:
        raise ValueError("Unknown parser name: {0}; not one of {1}".format(name,
                                                                           sorted(parsers.keys())))
