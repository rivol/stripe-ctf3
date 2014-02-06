#!/usr/bin/env python

import sys

path = sys.argv[1] if len(sys.argv) > 1 else '/usr/share/dict/words'
entries = set()
for line in open(path, 'r'):
    entries.add(line.strip())

for line in sys.stdin:
    if line[-1] == '\n':
        line = line[:-1]
    if line == '':
        print
        continue

    output_tokens = []
    for word in line.split(' '):
        if word.lower() not in entries:
            output_tokens.append('<%s>' % word)
        else:
            output_tokens.append(word)

    print ' '.join(output_tokens)
