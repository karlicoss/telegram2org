#!/usr/bin/env python3.6
from hashlib import md5
import re
import codecs

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
        raise RuntimeError(f"Couldn't extract from: {fwd_from}")

    texts: List[str] = []
    for m in group:
        if 'text' in m:
            texts.append(m['text'])
        if 'media' in m:
            texts.append("<SOME MEDIA>")
            # TODO handle urls

    link = f"https://web.telegram.org/#/im?p=@{from_}"

    from_ += " " + ' '.join(texts)[:40]
    id_ = re.sub('\s+', '_', from_) + "_" + md5(from_.encode('utf-8')).hexdigest()
    # TODO hmm, maybe using exported messages as a state wasn't such a great idea... use date?
    texts.append(link)

    return (id_, from_, texts)

def load_state() -> List[str]:
    if not isfile(STATE_PATH):
        return []
    else:
        with open(STATE_PATH, 'r') as fo:
            return json_load(fo)

def save_state(ids: List[str]):
    with atomic_write(STATE_PATH, overwrite=True, mode='w') as fo:
        json_dumps(fo, ids)

def mark_completed(id_: str):
    # well not super effecient, but who cares
    state = load_state()
    state.append(id_)
    save_state(state)

def submit_tasks(api: EnhancedRtm, tasks):
    state = load_state()

    for id_, name, notes in tasks:
        cname = name
        for c in ['!', '#', '*', '^', '@', '/']:
            cname = name.replace("c", " ")
            # cleanup for smart add # TODO move to enhanced rtm?
        tname = cname + " ^today #" + RTM_TAG
        task = api.addTask_(description=tname)
        for note in notes:
            api.addNote(task=task, text=note, long_note_hack=True)
        mark_completed(id_)

def get_tg_tasks():
    forwarded = []
    with codecs.open(BACKUP_PATH, 'r', 'utf-8') as bp:
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

def iter_new_tasks():
    tasks = get_tg_tasks()
    state = load_state()

    for t in tasks:
        id_, name, notes = t
        if id_ in state:
            logging.debug(f"Skipping {id_}")
            continue
        else:
            logging.info(f"Handling new task: {name}")
            yield t

def get_new_tasks():
    return list(iter_new_tasks())

def main():
    tasks = get_new_tasks()
    logging.info(f"Fetched {len(tasks)} tasks from telegram")

    logging.info("Submitting to RTM... (tagged as {})".format(RTM_TAG))
    api = EnhancedRtm(RTM_API_KEY, RTM_API_SECRET, token=RTM_API_TOKEN)
    submit_tasks(api, tasks)

if __name__ == '__main__':
    setup_logging()
    main()
