#!/usr/bin/python3.6
from hashlib import md5
import re

from kython.enhanced_rtm import EnhancedRtm
from kython import *

from config import BACKUP_PATH, RTM_API_KEY, RTM_API_TOKEN, RTM_API_SECRET, STATE_PATH, RTM_TAG

# returns title and comment
def format_group(group: List[Dict]) -> Tuple[str, str, List[str]]:
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

    texts: List[str] = []
    for m in group:
        if 'text' in m:
            texts.append(m['text'])
        if 'media' in m:
            texts.append("<SOME MEDIA>")

    from_ += " " + ' '.join(texts)[:40]
    id_ = re.sub('\s+', '_', from_) + "_" + md5(from_.encode('utf-8')).hexdigest()
    return (id_, from_, texts)

def load_state() -> List[str]:
    if not isfile(STATE_PATH):
        return []
    else:
        with open(STATE_PATH, 'r') as fo:
            return json_load(fo)

def save_state(ids: List[str]):
    with open(STATE_PATH, 'w') as fo:
        # TODO atomicwrites, add to kython
        json_dumps(fo, ids)

def mark_completed(id_: str):
    # TODO well not super effecient, but who cares
    state = load_state()
    state.append(id_)
    save_state(state)

def submit_tasks(api: EnhancedRtm, tasks):
    state = load_state()

    for id_, name, notes in tasks:
        if id_ in state:
            logging.info(f"Skipping {id_}")
            continue
        else:
            logging.info(f"Submitting new task to RTM: {name}")

        cname = name
        for c in ['!', '#', '*', '^', '@', '/']:
            cname = name.replace("c", " ")
            # cleanup for smart add # TODO move to enhanced rtm?
        tname = cname + " ^today #" + RTM_TAG
        task = api.addTask_(description=tname)
        for note in notes:
            # TODO note might be too long for GET request
            api.addNote(task=task, text=note)
        mark_completed(id_)

def get_rtm_tasks():
    forwarded = []
    with open(BACKUP_PATH, 'r') as bp:
        for line in bp.readlines():
            j = json_loads(line)
            if j['event'] == 'message':
                if 'fwd_from' in j:
                    forwarded.append(j)

    # apparently, date is appropriate as a 'unit of forwarding'
    grouped = group_by_key(forwarded, lambda f: f['date'])
    tasks = []
    for _, group in sorted(grouped.items(), key=lambda f: f[0]):
        id_, title, texts = format_group(group)
        tasks.append((id_, title, texts))
    return tasks

def main():
    tasks = get_rtm_tasks()
    logging.info(f"Fetched {len(tasks)} tasks from telegram")

    logging.info("Submitting to RTM... (tagged as {})".format(RTM_TAG))
    api = EnhancedRtm(RTM_API_KEY, RTM_API_SECRET, token=RTM_API_TOKEN)
    submit_tasks(api, tasks)

if __name__ == '__main__':
    setup_logging()
    main()
