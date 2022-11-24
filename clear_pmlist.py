"""Clear pmlist"""
# pylint: disable=C0103
import logging
import sys
import time

import praw

AGENT = "python:dimmi-ouja:0.3.2 (by /u/timendum)"

OK_LIMIT = 2
MAX_AGE = 60 * 60 * 24 * 14 * 6  # 6 editions
LOGGER = logging.getLogger(__file__)
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.INFO)


class Cleaner:
    """Manage a list of user to message"""

    def __init__(self, subreddit) -> None:
        self.reddit = praw.Reddit(check_for_updates=False)
        rsubreddit = self.reddit.subreddit(subreddit)
        self.subreddit = subreddit
        self.wiki_main = rsubreddit.wiki["pmlist"]
        self.mods = [moderator.name for moderator in rsubreddit.moderator()]
        LOGGER.info("Mods: %s", self.mods)
        self._fetch_authors(rsubreddit)

    def _fetch_authors(self, rsubreddit) -> None:
        time_limit = time.time() - MAX_AGE
        LOGGER.info("Retrieved comments")
        comments = list(rsubreddit.comments(limit=None))
        LOGGER.info("Retrieved %d comments", len(comments))
        comments = [comment for comment in comments if comment.created >= time_limit]
        LOGGER.info("Valid (before %s) comments: %d", (time_limit, len(comments)))
        self.authors = set([comment.author.name for comment in comments if comment.author])
        LOGGER.info("Found %d authors", len(self.authors))

    def start(self) -> None:
        """Parse and clear the list"""
        users = self.wiki_main.content_md.split("\n")
        users = [user.strip() for user in users]
        users = [user for user in users if user]
        saved_users = []
        removed_users = []
        for user in users:
            if user in self.authors:
                saved_users.append(user)
            elif user in self.mods:
                saved_users.append(user)
            else:
                removed_users.append(user)
        LOGGER.info("Saved: %s", ', '.join(saved_users))
        LOGGER.info("Removed: %s", ', '.join(removed_users))
        self.wiki_main.edit("\n\n".join(saved_users), reason="Clean up")


def main():
    """Perform action"""

    cleaner = Cleaner("DimmiOuija")
    cleaner.start()


if __name__ == "__main__":
    main()
