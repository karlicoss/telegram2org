#!/usr/bin/env python3
"""
Imagine a friend asked you for something, or sent you a link or a video, but you don't have time to process that right at the moment.

Normally I'd share their message to my TODO list app so I can process it later.
However, official Android app for Telegram doesn't have sharing capabilities.

This is a tool that allows you to overcome this restriction by forwarding messages you want to
remember about to a special private channel. Then it grabs the messages from this private channel and creates TODO items from it!

That way you keep your focus while not being mean ignoring your friends' messages.
"""

from datetime import datetime
from itertools import groupby
import logging
import re
from typing import List, Tuple, Set

import pytz

# telethon.sync is necessary to prevent using async api
import telethon.sync  # type: ignore[import-untyped]
import telethon
from telethon.tl.types import (  # type: ignore[import-untyped]
    InputMessagesFilterPinned,
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaVenue,
    MessageMediaWebPage,
    MessageService,
    WebPageEmpty,
    WebPagePending,
)

from orger import InteractiveView
from orger.common import todo
from orger.inorganic import link

from config import ORG_TAG, TG_APP_HASH, TG_APP_ID, TELETHON_SESSION, GROUP_NAME, TIMEZONE, NAME_TO_TAG


Timestamp = int
From = str
Lines = List[str]
Tags = Set[str]


def format_group(group: List, logger) -> Tuple[Timestamp, From, Tags, Lines]:
    date = int(group[0].date.timestamp())

    def get_from(m) -> str:
        chat = m.get_chat()
        is_special_group = getattr(chat, 'title', None) == GROUP_NAME

        if is_special_group:
            fw = m.forward
            if fw is None:
                # this is just a message typed manually into the special chat
                return 'me'

            if fw.sender is None:
                if fw.chat is not None:
                    return fw.chat.title
                else:
                    return "ERROR UNKNOWN SENDER"
            u = fw.sender
        else:
            u = m.sender

        if u.username is not None:
            return u.username
        else:
            return f"{u.first_name} {u.last_name}"

    froms = [get_from(m) for m in group]
    tags = {NAME_TO_TAG[f] for f in froms if f in NAME_TO_TAG}

    from_ = ', '.join(link(url=f'https://t.me/{f}', title=f) for f in sorted(set(froms)))

    texts: List[str] = []
    for m in group:
        texts.append(m.message)
        # TODO hmm, _text contains markdown? could convert it to org...
        # TODO use m.entities??
        if m.media is None:
            continue
        e = m.media
        if isinstance(e, MessageMediaWebPage):
            page = e.webpage
            uu: str
            if isinstance(page, WebPageEmpty):
                uu = "*empty web page*"
            elif isinstance(page, WebPagePending):
                # doesn't have title/url
                uu = "*pending web page*"
            else:
                title = page.display_url if page.title is None else page.title
                uu = link(url=page.url, title=title)
                if page.description is not None:
                    uu += ' ' + page.description
            texts.append(uu)
        elif isinstance(e, MessageMediaPhoto):
            # TODO no file location? :(
            texts.append("*PHOTO*")
            # print(vars(e))
        elif isinstance(e, MessageMediaDocument):
            texts.append("*DOCUMENT*")
            # print(vars(e.document))
        elif isinstance(e, MessageMediaVenue):
            texts.append("*VENUE* " + e.title)
        else:
            logger.error(f"Unknown media {type(e)}")
            # raise RuntimeError
            # TODO contribute 1 to exit code? or emit Error?

    # chat = dialog.name
    # mid = group[0].id
    # TODO ugh. doesn't seem to be possible to jump to private dialog :(
    # and couldn't get original forwarded message id from message object..
    # in_context = f'https://t.me/{chat}/{mid}'
    # TODO detect by data-msg-id?
    texts = list(reversed(texts))

    heading = from_
    if len(group) == 1 and group[0].pinned:
        heading = 'pinned: ' + from_  # meh..

    LIMIT = 400
    lines = '\n'.join(texts).splitlines()  # meh
    for line in lines:
        if len(heading) + len(line) <= LIMIT:
            heading += " " + line
        else:
            break

    heading = re.sub(r'\s', ' ', heading) # TODO rely on inorganic for that?
    return (date, heading, tags, texts)


def _fetch_tg_tasks(logger):
    client = telethon.TelegramClient(TELETHON_SESSION, TG_APP_ID, TG_APP_HASH)
    client.connect()
    client.start()

    messages = []

    all_dialogs = client.get_dialogs()

    for dialog in all_dialogs:
        if not dialog.is_user:
            # skip channels -- they tend to have lots of irrelevant pinned messages
            continue
        pinned_messages = client.get_messages(
            dialog.input_entity,
            filter=InputMessagesFilterPinned,
            limit=1000,  # TODO careful about the limit?
        )
        messages.extend(pinned_messages)

    # handle multiple dialogs just in case.. it might happen if you converted to supergroup at some point or did something like that
    # seems like the old dialog is still in API even though it doesn't display in the app?
    todo_dialogs = [d for d in all_dialogs if d.name == GROUP_NAME]
    for todo_dialog in todo_dialogs:
        api_messages = client.get_messages(todo_dialog.input_entity, limit=1000000)  # TODO careful about the limit?
        messages.extend(m for m in api_messages if not isinstance(m, MessageService))  # wtf is that...


    # group together multiple forwarded messages. not sure if there is a more robust way but that works well
    key = lambda f: f.date
    grouped = groupby(sorted(messages, key=key), key=key)
    tasks = []
    for _, group in grouped:
        res = format_group(list(group), logger=logger)
        tasks.append(res)
    return tasks


def fetch_tg_tasks(logger):
    try:
        # return [
        #     (1234, 'me', {}, [
        #         'line 1',
        #         'line 2',
        #     ]),
        #     (24314, 'llll', {}, [
        #         'something',
        #     ]),
        # ]
        return _fetch_tg_tasks(logger=logger)
    except telethon.errors.rpcerrorlist.RpcMcgetFailError as e:
        logger.error(f"Telegram has internal issues...")
        logger.exception(e)
        # TODO backoff?
        if 'Telegram is having internal issues, please try again later' in str(e):
            logger.info('ignoring the exception, it just happens sometimes...')
            return []
        else:
            raise e


def make_header() -> str:
    parts = []
    if ORG_TAG is not None:
         parts.append(f'#+FILETAGS: {ORG_TAG}')
    parts.append(f'# AUTOGENERATED by {__file__}')
    return '\n'.join(parts)


class Telegram2Org(InteractiveView):
    def __init__(self, *args, **kwargs) -> None:
        kwargs['file_header'] = make_header()
        super().__init__(*args, **kwargs)

    def get_items(self):
        now = datetime.now(tz=pytz.timezone(TIMEZONE))
        # TODO extract date from messages?
        for timestamp, name, tags, lines in fetch_tg_tasks(logger=self.logger):
            yield str(timestamp), todo(
                now,
                heading=name,
                tags=tags,
                body='\n'.join(lines + ['']),
            )
        # TODO automatic tag map?


def main() -> None:
    logging.getLogger('telethon.telegram_bare_client').setLevel(logging.INFO)
    logging.getLogger('telethon.extensions.tcp_client').setLevel(logging.INFO)
    Telegram2Org.main()


if __name__ == '__main__':
    main()
