#!/usr/bin/env python3
import re

from config import ORG_FILE_PATH

from main import get_new_tasks, mark_completed # TODO move to common?

# TODO add date!
def as_org(task) -> str:
    id_, name, notes = task
    name = re.sub(r'\s', ' ', name)
    res = f"* TODO {name}\n" + "\n".join(notes)
    return res


def main():
    tasks = get_new_tasks()
    from pprint import pprint
    pprint(tasks)
    # TODO how to append atomically??

    orgs = [as_org(t) for t in tasks]
    ss = '\n\n'.join(orgs) + '\n\n'

    # https://stackoverflow.com/a/13232181 should be atomic
    import io
    with io.open(ORG_FILE_PATH, 'a') as fo:
        fo.write(ss)

    for id_, _, _ in tasks:
        mark_completed(id_)


if __name__ == '__main__':
    main()
