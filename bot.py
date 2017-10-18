"""Produce a summery for AskOuija thread"""
# pylint: disable=C0103
import argparse
import logging
import re
import time
from praw import Reddit
from praw.models.comment_forest import CommentForest
from slacker import Slacker

AGENT = 'python:dimmi-ouja:0.1 (by /u/timendum)'

GOODBYE = re.compile(r'^(?:Goodbye|Arrivederci|Addio)', re.IGNORECASE)
UNANSWERED = {'text': 'Senza risposta', 'class': 'unanswered'}
ANSWERED = {'text': 'Ouija dice: ', 'class': 'answered'}

TIME_LIMIT = 24 * 60 * 60 * 1000
YESTERDAY = time.time() - TIME_LIMIT


class Slack():
    """Transmit messages to slack channel"""

    def __init__(self):
        dummy_reddit = Reddit(check_for_updates=False)
        config = dummy_reddit.config.CONFIG['SLACK']
        self.channel = config['channel']
        del dummy_reddit
        self.slack = Slacker(config['token'])
        self._logger = logging.getLogger(__file__)
        self._logger.addHandler(logging.NullHandler())
        self._logger.setLevel(logging.INFO)
        self._formatter = logging.Formatter()

    def _format(self, level, msg, *args, **kwargs):
        """Fromat message with default logging formatter"""
        record = logging.LogRecord(None, level, None, None, msg, args, kwargs)
        return self._formatter.format(record)

    def setLevel(self, level):
        """
        Set the logging level of this logger.  level must be an int or a str.
        """
        self._logger.setLevel(level)

    def debug(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'DEBUG'.
        """
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug(msg, *args, **kwargs)
            chat_message = self._format(logging.DEBUG, msg, *args, **kwargs)
            self.slack.chat.post_message(self.channel, chat_message)

    def info(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'INFO'.
        """
        if self._logger.isEnabledFor(logging.INFO):
            self._logger.info(msg, *args, **kwargs)
            chat_message = self._format(logging.INFO, msg, *args, **kwargs)
            self.slack.chat.post_message(self.channel, chat_message)


LOGGER = Slack()


class OuijaPost(object):
    """A post in ouija"""

    def __init__(self, post):
        """Initialize."""
        self._post = post
        self.author = post.author.name
        self.question = post.title
        self.answer_text = None
        self.answer_score = float('-inf')
        self.flair = None
        if post.link_flair_text and post.link_flair_text != UNANSWERED['text']:
            self.flair = post.link_flair_text

    def is_unanswered(self):
        """Check if the submission is Unanswered"""
        if not self._post.link_flair_text:
            return True
        return self._post.link_flair_text == UNANSWERED['text']

    def is_fresh(self):
        """Check if the submission is younger then YESTERDAY"""
        return self._post.created_utc > YESTERDAY

    def change_flair(self):
        """Flair the post based on answer_text"""
        if not self.answer_text:
            if not self._post.link_flair_text:
                self._post.mod.flair(UNANSWERED['text'], UNANSWERED['class'])
                LOGGER.debug("Flair - UNANSWERED - https://www.reddit.com%s", self._post.permalink)
        else:
            text = ANSWERED['text'] + self.answer_text
            if len(text) > 64:
                text = text[0:61] + '...'
            if text != self.flair:
                self._post.mod.flair(text, ANSWERED['class'])
                LOGGER.debug("Flair - %s - https://www.reddit.com%s", text, self._post.permalink)

    def process(self):
        """Check for answers in the comments and delete wrong comments"""
        self._post.comment_sort = 'top'
        self._post.comments.replace_more(limit=None)
        return self.find_answers(self._post)

    def accept_answer(self, comment):
        """
        Check if the comment contain a better answer.

        Return True if accepted, False otherwise.
        """
        if comment.score > self.answer_score:
            self.answer_text = ''
            self.answer_score = comment.score
            return True
        return False

    def moderation(self, comment, parent):
        """
        Delete the comment according to rule.

        Return True if deleted, False otherwise.
        """
        if comment.author.name == self.author:
            LOGGER.info("Deleting - OP = author - %s", self.permalink(parent))
            comment.mod.remove()
            return True
        if comment.author.name == parent.author.name:
            LOGGER.info("Deleting - parent = author - %s?context=1", self.permalink(comment))
            comment.mod.remove()
            return True
        return False

    def permalink(self, comment):
        """Produce a shorter permalink"""
        return 'https://www.reddit.com/r/{}/comments/{}//{}'.format(
            self._post.subreddit.display_name, self._post.id, comment.id)

    def find_answers(self, parent):
        """Given a comment return a list of open and closed replies"""
        found = False
        existing = {}
        if isinstance(parent, CommentForest):
            parent.replace_more(limit=None)
        # try replies for parent=comment
        try:
            comments = parent.replies
        except AttributeError:
            # try comments for parent=submission
            comments = parent.comments
        # loop for every child comment
        for comment in comments:
            # skip comments by mods or removed comments
            if comment.stickied or comment.distinguished or comment.removed:
                continue
            # if modeation is applied (comment removed), skip
            if self.moderation(comment, parent):
                continue
            # check body
            body = comment.body.strip()
            if GOODBYE.match(body):
                found = found or self.accept_answer(comment)
            elif len(body) == 1:
                if existing.get(body):
                    # the letter is already insered
                    if comment.created > existing[body].created and not comment.replies:
                        # the new comment is newer and does not have replies: delete it
                        LOGGER.info("Deleting - duplicated - %s?", self.permalink(parent))
                        comment.mod.remove()
                        continue
                    if not existing[body].replies:
                        # the previous comment has not replies: delete it
                        LOGGER.info("Deleting - duplicated - %s", self.permalink(parent))
                        existing[body].mod.remove()
                        existing[body] = comment
                        continue
                # the letter is not already insered, save it
                existing[body] = comment
                if self.find_answers(comment):
                    # compose the answer
                    self.answer_text = body + self.answer_text
                    # to uppercase
                    self.answer_text = self.answer_text.upper()
                    found = True
            else:
                # comment is by user and longer than 1 char (unicode ok), delete it
                LOGGER.info("Deleting - length <> 1 - %s", self.permalink(comment))
                comment.mod.remove()
        return found


class Ouija(object):
    """Contain all bot logic."""

    def __init__(self, subreddit):
        """Initialize."""
        reddit = Reddit(check_for_updates=False)
        self.subreddit = reddit.subreddit(subreddit)

    def check_hot(self):
        """Check the hot submission for unanswered post"""
        submissions = self.subreddit.hot(limit=100)
        for submission in submissions:
            if submission.distinguished:
                continue
            if submission.stickied:
                continue
            post = OuijaPost(submission)
            if post.is_unanswered():
                answer = post.process()
                if answer:
                    if post.answer_score <= 1:
                        post.answer_text = None
                post.change_flair()

    def open(self):
        """Open the subreddit to new submission"""
        self.subreddit.mod.update(subreddit_type='public')
        LOGGER.info("Subreddit aperto! https://www.reddit.com/r/%s" % self.subreddit.display_name)

    def close(self):
        """Close the subreddit to new submission"""
        self.subreddit.mod.update(subreddit_type='restricted')
        LOGGER.info("Subreddit chiuso")


def main():
    """Perform a bot action"""
    parser = argparse.ArgumentParser(description='Activate mod bot on /r/DimmiOuija ')
    parser.add_argument(
        'action',
        choices=['hot', 'open', 'close'],
        default='hot',
        help='The action to perform (default: %(default)s)')
    args = parser.parse_args()

    bot = Ouija('DimmiOuija')
    if args.action == 'hot':
        bot.check_hot()
    elif args.action == 'open':
        bot.open()
    elif args.action == 'close':
        bot.close()


if __name__ == "__main__":
    main()
