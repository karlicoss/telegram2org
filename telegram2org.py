#!/usr/bin/env python3.6
from datetime import datetime
import logging
from os.path import isfile
import re
from typing import List, Dict, Any, Tuple, NamedTuple

from telethon import TelegramClient # type: ignore
from telethon.tl.types import MessageMediaWebPage, MessageMediaPhoto, MessageMediaDocument # type: ignore
from telethon.tl.types import MessageService # type: ignore


from kython import json_loads, atomic_write, json_dumps, group_by_key, json_load
from kython.org import date2org
from config import STATE_PATH, ORG_TAG, ORG_FILE_PATH, TG_APP_HASH, TG_APP_ID, TELETHON_SESSION

from kython.logging import setup_logzero

logger = logging.getLogger("telegram2org")
setup_logzero(logger, level=logging.DEBUG)


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

def get_tg_tasks():
    import logging
    ll = logging.getLogger('telethon.telegram_bare_client')
    ll.setLevel(level=logging.INFO)
    ll = logging.getLogger('telethon.extensions.tcp_client')
    ll.setLevel(level=logging.INFO)

    client = TelegramClient(TELETHON_SESSION, TG_APP_ID, TG_APP_HASH)
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

def as_org(task) -> str:
    id_, name, notes = task
    name = re.sub(r'\s', ' ', name)

    dt = datetime.now()

    tag = '' if ORG_TAG is None else f':{ORG_TAG}:'
    res = f"""* TODO {name} {tag}
  SCHEDULED: <{date2org(dt)}>
:PROPERTIES:
:CREATED:  [{date2org(dt)}]
:END:
""" + "\n".join(notes)
    return res


def main():
    tasks = get_new_tasks()

    if len(tasks) == 0:
        logger.info(f"No new tasks, exiting..")
        return

    orgs = [as_org(t) for t in tasks]
    ss = '\n\n'.join(orgs) + '\n\n'

    # https://stackoverflow.com/a/13232181 should be atomic?
    import io
    with io.open(ORG_FILE_PATH, 'a') as fo:
        fo.write(ss)

    for date, _, _ in tasks:
        pass
        # mark_completed(date)


if __name__ == '__main__':
    main()
