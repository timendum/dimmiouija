"""Clear pmlist"""
# pylint: disable=C0103
import logging
import sys
import time

import praw

AGENT = "python:dimmi-ouja:0.3.2 (by /u/timendum)"

OK_LIMIT = 2
MAX_AGE = 60 * 60 * 24 * 14 * 4  # 4 editions
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
        self.time_limit = time.time() - MAX_AGE

    def start(self):
        """Parse and clear the list"""
        users = self.wiki_main.content_md.split("\n")
        users = [user.strip() for user in users]
        users = [user for user in users if user]
        saved_users = []
        removed_users = []
        for user in users:
            if self.check_user(user):
                saved_users.append(user)
            else:
                removed_users.append(user)
        LOGGER.info("Saved: %s", saved_users)
        LOGGER.info("Removed: %s", removed_users)
        self.wiki_main.edit(
            "\n\n".join(saved_users), reason="Removed " + ", ".join(removed_users)
        )

    def check_user(self, user):
        """Check if user is mod or is active"""
        if user in self.mods:
            LOGGER.info("%s: mod", user)
            return True
        user = self.reddit.redditor(user)
        comments = 0
        for comment in user.comments.new(limit=None):
            if comment.created < self.time_limit:
                break
            if comment.subreddit.display_name == self.subreddit:
                comments += 1
                if comments >= OK_LIMIT:
                    break
        LOGGER.info("%s: %d", user.name, comments)
        return comments >= OK_LIMIT


def main():
    """Perform action"""

    cleaner = Cleaner("DimmiOuija")
    cleaner.start()


if __name__ == "__main__":
    main()
