#!/usr/bin/env python3
from typing import Collection

from datetime import datetime
import logging
from os.path import isfile
import sys
from sys import argv
import re
from typing import List, Dict, Any, Tuple, NamedTuple
import pytz

import telethon.sync # type: ignore
from telethon import TelegramClient # type: ignore
from telethon.tl.types import MessageMediaWebPage, MessageMediaPhoto, MessageMediaDocument # type: ignore
from telethon.tl.types import MessageService, WebPageEmpty # type: ignore


from kython import json_loads, atomic_write, json_dumps, group_by_key, json_load
from kython import import_from
from kython.org import date2org, datetime2org
from kython.klogging import setup_logzero

orger = import_from('/L/coding', 'orger')
from orger import OrgViewAppend, OrgWithKey
from orger.org_utils import OrgTree, as_org

from config import STATE_PATH, ORG_TAG, ORG_FILE_PATH, TG_APP_HASH, TG_APP_ID, TELETHON_SESSION, GROUP_NAME


Timestamp = int
From = str
Lines = List[str]

def format_group(group: List, logger) -> Tuple[Timestamp, From, Lines]:
    date = int(group[0].date.timestamp())

    def get_from(m):
        fw = m.forward
        if fw is not None:
            if fw.sender is None:
                if fw.chat is not None:
                    return fw.chat.title
                else:
                    return "ERROR UNKNOWN SENDER"
            u = fw.sender
            if u.username is not None:
                return u.username
            else:
                return f"{u.first_name} {u.last_name}"
        else:
            return "me"

    from_ = ', '.join(sorted({get_from(m) for m in group}))


    texts: List[str] = []
    for m in group:
        texts.append(m.text)
        if m.media is None:
            continue
        e = m.media
        if isinstance(e, MessageMediaWebPage):
            page = e.webpage
            uu: str
            if isinstance(page, WebPageEmpty):
                uu = "*empty web page*"
            else:
                uu = f"{page.url} {page.title}"
            texts.append(uu)
        elif isinstance(e, MessageMediaPhoto):
            texts.append("*PHOTO*")
        elif isinstance(e, MessageMediaDocument):
            texts.append("*DOCUMENT*")
        else:
            logger.error(f"Unknown media {type(e)}")

    link = f"https://web.telegram.org/#/im?p=@{from_}" # TODO err. from_ wouldn't work here...

    texts = list(reversed(texts))

    if len(texts) > 0: # why wouldn't it be? ... but whatever
        from_ += " " + texts[0]
        texts = texts[1:]
    while len(texts) > 0 and len(from_) < 150:
        from_ += " " + texts[0]
        texts = texts[1:]

    texts.append(link)
    return (date, from_, texts)


def _fetch_tg_tasks(logger):
    client = TelegramClient(TELETHON_SESSION, TG_APP_ID, TG_APP_HASH)
    client.connect()
    client.start()
    [todo_dialog] = [d for d in client.get_dialogs() if d.name == GROUP_NAME]
    api_messages = client.get_messages(todo_dialog.input_entity, limit=1000000)

    messages = [m for m in api_messages if not isinstance(m, MessageService)] # wtf is that...
    grouped = group_by_key(messages, lambda f: f.date) # group together multiple forwarded messages. not sure if there is a more robust way but that works well
    tasks = []
    for _, group in sorted(grouped.items(), key=lambda f: f[0]):
        id_, title, texts = format_group(group, logger=logger)
        tasks.append((id_, title, texts))
    return tasks


def fetch_tg_tasks(logger):
    try:
        return [
            (1234, 'me', [
                'line 1',
                'line 2',
            ]),
        ]
        # TODO FIXME return _fetch_tg_tasks(logger=logger)
    except telethon.errors.rpcerrorlist.RpcMcgetFailError as e:
        logger.error(f"Telegram has internal issues...")
        logger.exception(e)
        # TODO backoff?
        if 'Telegram is having internal issues, please try again later' in str(e):
            logger.info('ignoring the exception, it just happens sometimes...')
            return []
        else:
            raise e


class Telegram2Org(OrgViewAppend):
    file = __file__
    logger_tag = 'telegram2org'


    def get_items(self) -> Collection[OrgWithKey]:
        for _ in fetch_tg_tasks(logger=self.logger):
            raise NotImplementedError
        # raise RuntimeError # TODO should query telegram here?


def main():
    logging.getLogger('telethon.telegram_bare_client').setLevel(logging.INFO)
    logging.getLogger('telethon.extensions.tcp_client').setLevel(logging.INFO)
    Telegram2Org.main(default_to=ORG_FILE_PATH, default_state=STATE_PATH)


def as_org(task) -> str:
    id_, name, notes = task
    name = re.sub(r'\s', ' ', name)

    london_tz = pytz.timezone('Europe/London')
    dt = datetime.now(london_tz)

    tag = '' if ORG_TAG is None else f':{ORG_TAG}:'
    res = f"""* TODO {name} {tag}
  SCHEDULED: <{date2org(dt)}>
:PROPERTIES:
:CREATED:  [{datetime2org(dt)}]
:END:
""" + "\n".join(notes)
    return res


    # # https://stackoverflow.com/a/13232181 should be atomic?
    # import io
    # with io.open(ORG_FILE_PATH, 'a') as fo:
    #     fo.write(ss)

if __name__ == '__main__':
    main()
