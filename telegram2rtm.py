#!/usr/bin/env python3.6
import sys, ipdb, traceback; exec("def info(type, value, tb):\n    traceback.print_exception(type, value, tb)\n    ipdb.pm()"); sys.excepthook = info # type: ignore
import logging

from hashlib import md5
import re
import codecs

from kython import json_loads, atomic_write, json_dumps, group_by_key, json_load

from kython.logging import setup_logzero
logger = logging.getLogger("telegram2org")
setup_logzero(logger, level=logging.DEBUG)

from typing import List, Dict, Any, Tuple

from os.path import isfile

from config import BACKUP_PATH, RTM_API_KEY, RTM_API_TOKEN, RTM_API_SECRET, STATE_PATH, RTM_TAG


from datetime import datetime
from typing import NamedTuple

# returns title and comment
def format_group(group: List) -> Tuple[int, str, List[str]]:
    date = int(group[0].date.timestamp())

    def get_from(m):
        fwd_from = m.fwd_from_entity
        if fwd_from is not None:
            if fwd_from.username is None:
                return f"{fwd_from.first_name} {fwd_from.last_name}"
            return fwd_from.username
        else:
            return 'me'

    from_ = ', '.join(sorted({get_from(m) for m in group}))

    from telethon.tl.types import MessageMediaWebPage, MessageMediaPhoto, MessageMediaDocument # type: ignore

    texts: List[str] = []
    for m in group:
        texts.append(m.text)
        if m.media is None:
            continue
        e = m.media
        if isinstance(e, MessageMediaWebPage):
            page = e.webpage
            uu = f"{page.url} {page.title}"
            texts.append(uu)
        elif isinstance(e, MessageMediaPhoto):
            texts.append("*PHOTO*")
        elif isinstance(e, MessageMediaDocument):
            texts.append("*DOCUMENT*")
        else:
            logger.error(f"Unknown media {type(e)}")
            import ipdb; ipdb.set_trace() 
            # TODO FIXME photos; other types

    link = f"https://web.telegram.org/#/im?p=@{from_}" # TODO err. from_ wouldn't work here...

    from_ += " " + ' '.join(texts)[:40]
    texts.append(link)

    return (date, from_, texts)

State = Dict[str, Any]
# contains: 'date' -- last date that was forwarded
# supplementary information, e.g. last message, mainly form debugging

def load_state() -> State:
    if not isfile(STATE_PATH):
        return {'date': -1}
    else:
        with open(STATE_PATH, 'r') as fo:
            return json_load(fo)

def save_state(state: State):
    with atomic_write(STATE_PATH, overwrite=True, mode='w') as fo:
        json_dumps(fo, state)

def mark_completed(new_date: int):
    # well not super effecient, but who cares
    state = load_state()
    last = state['date']
    assert new_date > last
    state['date'] = new_date
    save_state(state)

def submit_tasks(api, tasks):
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
    import logging
    ll = logging.getLogger('telethon.telegram_bare_client')
    ll.setLevel(level=logging.INFO)
    ll = logging.getLogger('telethon.extensions.tcp_client')
    ll.setLevel(level=logging.INFO)

    from telethon import TelegramClient # type: ignore
    from telethon.tl.types import MessageService # type: ignore

    from telegram_secrets import APP_ID, APP_HASH # type: ignore

    client = TelegramClient('session', APP_ID, APP_HASH)
    client.connect()
    client.start()
    rtm_dialog = next(d for d in client.get_dialogs() if d.name == 'RTM')
    api_messages = client.get_messages(rtm_dialog.input_entity, limit=1000000)


    messages = [m for m in api_messages if not isinstance(m, MessageService)] # wtf is that...
    grouped = group_by_key(messages, lambda f: f.date)
    tasks = []
    for _, group in sorted(grouped.items(), key=lambda f: f[0]):
        id_, title, texts = format_group(group)
        tasks.append((id_, title, texts))
    return tasks


def iter_new_tasks():
    tasks = get_tg_tasks()
    state = load_state()

    for t in tasks:
        date, name, notes = t
        if date <= state['date']:
            logger.debug(f"Skipping {date} {name}")
            continue
        else:
            logger.info(f"New task: {date} {name}")
            yield t

def get_new_tasks():
    return list(iter_new_tasks())

def main():
    tasks = get_new_tasks()
    logger.info(f"Fetched {len(tasks)} tasks from telegram")

    logger.info("Submitting to RTM... (tagged as {})".format(RTM_TAG))
    from kython.enhanced_rtm import EnhancedRtm

    api = EnhancedRtm(RTM_API_KEY, RTM_API_SECRET, token=RTM_API_TOKEN)
    submit_tasks(api, tasks)

if __name__ == '__main__':
    main()
