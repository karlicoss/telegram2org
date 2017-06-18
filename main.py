#!/usr/bin/python3
from json import load, loads

from config import BACKUP_PATH

from dima import *


forwarded = []
with open(BACKUP_PATH, 'r') as bp:
    for line in bp.readlines():
        j = loads(line)
        if j['event'] == 'message':
            if 'fwd_from' in j:
                forwarded.append(j)

# returns title and comment
def format_group(group: List[Dict]) -> Tuple[str, str]:
    from_ = None
    fwd_from = group[0]['fwd_from']
    if 'username' in fwd_from:
        from_ = fwd_from['username']
    elif 'print_name' in fwd_from:
        from_ = fwd_from['print_name']
    elif 'title' in fwd_from:
        from_ = fwd_from['title']
    else:
        raise RuntimeError

    text = ""
    for m in group:
        if 'text' in m:
            text += m['text'] + "\n"
        if 'media' in m:
            text += "<SOME MEDIA> \n"
    return (from_ + " " + text[:10], text)

# apparently, date is appropriate as a 'unit of forwarding'
grouped = group_by_key(forwarded, lambda f: f['date'])
for _, group in sorted(grouped.items(), key=lambda f: f[0]):
    title, text = format_group(group)
