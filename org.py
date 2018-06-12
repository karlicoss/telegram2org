#!/usr/bin/env python3
from datetime import datetime
import re

from kython.org import date2org

from config import ORG_FILE_PATH
from telegram2rtm import get_new_tasks, mark_completed # TODO move to common?

def as_org(task) -> str:
    id_, name, notes = task
    name = re.sub(r'\s', ' ', name)

    dt = datetime.now()

    res = f"* TODO {name}\n  SCHEDULED: <{date2org(dt)}>\n" + "\n".join(notes)
    return res


def main():
    tasks = get_new_tasks()

    orgs = [as_org(t) for t in tasks]
    ss = '\n\n'.join(orgs) + '\n\n'

    # https://stackoverflow.com/a/13232181 should be atomic?
    import io
    ORG_FILE_PATH = 'res.org'
    with io.open(ORG_FILE_PATH, 'a') as fo:
        fo.write(ss)
    raise RuntimeError

    # for date, _, _ in tasks:
    #     mark_completed(date)


if __name__ == '__main__':
    main()
