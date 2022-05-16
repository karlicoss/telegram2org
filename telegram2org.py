#!/usr/bin/env python3
"""
Imagine a friend asked you for something, or sent you a link or a video, but you don't have time to process that right at the moment.

Normally I'd share their message to my TODO list app so I can process it later.
However, official Android app for Telegram doesn't have sharing capabilities.

This is a tool that allows you to overcome this restriction by forwarding messages you want to
remember about to a special private channel. Then it grabs the messages from this private channel and creates TODO items from it!

That way you keep your focus while not being mean ignoring your friends' messages.
"""

from pathlib import Path
from datetime import datetime
import logging
import re
from typing import Collection, Dict, List, Optional, Set, Tuple, Union
import os
import pytz

import telethon.sync  # type: ignore
from telethon import TelegramClient  # type: ignore
from telethon.tl.types import MessageMediaWebPage, MessageMediaPhoto, MessageMediaDocument, MessageMediaVenue  # type: ignore
from telethon.tl.types import Message, MessageService, WebPageEmpty  # type: ignore

from orger import InteractiveView
from orger.common import todo
from orger.inorganic import link

from config import ORG_TAG, TG_APP_HASH, TG_APP_ID, TELETHON_SESSION, GROUP_NAME, TIMEZONE, NAME_TO_TAG, MEDIA_DIR


Timestamp = int
From = str
Lines = List[str]
Tags = Set[str]

SAVE_DIR = Path(MEDIA_DIR)


def simple_download_progress(filename: str):
    try:
        from humanize.filesize import naturalsize
    except:
        naturalsize = lambda x: f"{x:.2f} bytes"

    def callback(current, total):
        print(
            f"[{filename}] Downloaded {naturalsize(current)} / {naturalsize(total)} [{current/total:.2%}]"
        )

    return callback


def download_document_if_not_present(
    message: Message, filename: str, logger
) -> Optional[Path]:
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    destination = SAVE_DIR / filename

    if destination.exists():
        if destination.is_dir():
            logger.error(f"Could not save file as {destination} as it is a directory.")
            return None

        logger.info(f"File {destination} exists already, skipping download.")
        return destination

    saved_dest = message.download_media(
        file=destination,
        progress_callback=simple_download_progress(destination.as_posix()),
    )

    return destination


def format_group(group: List, dialog, logger) -> Tuple[Timestamp, From, Tags, Lines]:
    date = int(group[0].date.timestamp())

    def get_from(m):
        fw = m.forward
        if fw is None:
            return 'me'

        if fw.sender is None:
            if fw.chat is not None:
                return fw.chat.title
            else:
                return "ERROR UNKNOWN SENDER"
        u = fw.sender
        if u.username is not None:
            return u.username
        elif u.last_name is None:
            return f"{u.first_name}"
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
            else:
                title = page.display_url if page.title is None else page.title
                uu = link(url=page.url, title=title)
                if page.description is not None:
                    uu += ' ' + page.description
            texts.append(uu)
        elif isinstance(e, MessageMediaPhoto):
            saved_location = download_document_if_not_present(
                message=m, filename=f"{e.photo.id}.jpg", logger=logger
            )
            if saved_location is not None:
                texts.append(f"[[file:{saved_location.as_posix()}]]")
            else:
                texts.append("ERROR SAVING PHOTO {m.photo.id}")
            # print(vars(e))
        elif isinstance(e, MessageMediaDocument):
            try:
                original_file_name = e.document.attributes[0].file_name
            except:
                naive_file_ext = e.document.mime_type.split("/")[-1]
                original_file_name = "{}.{}".format(e.document.id, naive_file_ext)

            saved_location = download_document_if_not_present(
                message=m, filename=original_file_name, logger=logger
            )
            if saved_location is not None:
                texts.append(f"[[file:{saved_location.as_posix()}]]")
            else:
                texts.append("ERROR SAVING DOCUMENT {m.document.id}")
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
    LIMIT = 400
    lines = '\n'.join(texts).splitlines() # meh
    for line in lines:
        if len(heading) + len(line) <= LIMIT:
            heading += " " + line
        else:
            break

    heading = re.sub(r'\s', ' ', heading) # TODO rely on inorganic for that?
    return (date, heading, tags, texts)


def _fetch_tg_tasks(logger):
    client = TelegramClient(TELETHON_SESSION, TG_APP_ID, TG_APP_HASH)
    client.connect()
    client.start()
    [todo_dialog] = [d for d in client.get_dialogs() if d.name == GROUP_NAME]
    api_messages = client.get_messages(todo_dialog.input_entity, limit=1000000) # TODO careful about limit?

    messages = [m for m in api_messages if not isinstance(m, MessageService)] # wtf is that...

    # group together multiple forwarded messages. not sure if there is a more robust way but that works well
    from itertools import groupby
    key = lambda f: f.date
    grouped = groupby(sorted(messages, key=key), key=key)
    tasks = []
    for _, group in grouped:
        res = format_group(list(group), dialog=todo_dialog, logger=logger)
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


def make_header():
    parts = []
    if ORG_TAG is not None:
         parts.append(f'#+FILETAGS: {ORG_TAG}')
    parts.append(f'# AUTOGENERATED by {__file__}')
    return '\n'.join(parts)


class Telegram2Org(InteractiveView):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__( # type: ignore
            *args,
            file_header=make_header(),
            **kwargs,
        )

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


def main():
    logging.getLogger('telethon.telegram_bare_client').setLevel(logging.INFO)
    logging.getLogger('telethon.extensions.tcp_client').setLevel(logging.INFO)
    Telegram2Org.main()


if __name__ == '__main__':
    main()
