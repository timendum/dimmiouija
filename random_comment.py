"""Randomize the list of comments in a solution. """
import random
import re
import sys

import praw

from bot import GOODBYE


def main(permalink: str) -> None:
    match = re.search(r"comments/([a-z0-9]+)/[^/]+/([a-z0-9]+)/?", permalink)
    if not match:
        print("Comment not found")
        return
    reddit = praw.Reddit(check_for_updates=False)
    goodbye = reddit.comment(match.group(2))
    if not GOODBYE.match(goodbye.body):
        print("Comment is not a GOODBYE")
        return
    if goodbye.submission.id != match.group(1):
        print("Comment don't match post!")
        return
    ancestor = goodbye
    tree = [goodbye]
    refresh_counter = 0
    while not ancestor.is_root:
        ancestor = ancestor.parent()
        tree.append(ancestor)
        if refresh_counter % 9 == 0:
            ancestor.refresh()
        refresh_counter += 1
    print("Label: " + "".join([c.body for c in reversed(tree[1:])]) + " " + tree[0].body)
    randomized = random.sample(tree, k=len(tree))
    for i, c in enumerate(randomized):
        print("{}. https://www.reddit.com{}?context=1000".format(i + 1, c.permalink))


if __name__ == "__main__":
    main(sys.argv[1])
