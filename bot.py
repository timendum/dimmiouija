"""Produce a summery for AskOuija thread"""
# pylint: disable=C0103
import logging
import re
from praw import Reddit
from praw.models.comment_forest import CommentForest

AGENT = 'python:dimmi-ouja:0.1 (by /u/timendum)'

LOGGER = logging.getLogger(__file__)
LOGGER.addHandler(logging.StreamHandler())
LOGGER.setLevel(logging.DEBUG)

GOODBYE = re.compile(r'^(Goodbye|Arrivederci)', re.IGNORECASE)
UNANSWERED = {'text': 'Senza risposta', 'class': 'unanswered'}
ANSWERED = {'text': 'Ouija dice: ', 'class': 'answered'}


class OuijaPost(object):
    """A post in ouija"""

    def __init__(self, post):
        """Initialize."""
        self._post = post
        self.author = post.author.name
        self.question = post.title
        self.answer_text = None
        self.answer_score = float('-inf')

    def is_unanswered(self):
        """Check if the submission is Unanswered"""
        if not self._post.link_flair_text:
            return True
        return self._post.link_flair_text == UNANSWERED['text']

    def flair(self):
        """Flair the post based on answer_text"""
        if not self.answer_text:
            if not self._post.link_flair_text:
                self._post.mod.flair(UNANSWERED['text'], UNANSWERED['class'])
                LOGGER.debug("Flair - UNANSWERED - https://www.reddit.com%s", self._post.permalink)
        else:
            text = ANSWERED['text'] + self.answer_text
            if len(text) > 64:
                text = text[0:61] + '...'
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
            LOGGER.info("Deleting - OP = author - %s", self.permalink(comment))
            comment.mod.remove()
            return True
        if comment.author.name == parent.author.name:
            LOGGER.info("Deleting - parent = author - %s", self.permalink(comment))
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
        if isinstance(parent, CommentForest):
            parent.replace_more(limit=None)
        try: 
            comments = parent.replies
        except:
            comments = parent.comments
        for comment in comments:
            # skip comments by mods
            if comment.stickied:
                continue
            if comment.distinguished:
                continue
            # check body
            body = comment.body.strip()
            if self.moderation(comment, parent):
                continue
            if GOODBYE.match(body):
                if self.accept_answer(comment):
                    found = True
            elif len(body) == 1:
                if self.find_answers(comment):
                    self.answer_text = body + self.answer_text
                    found = True
            else:
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
                post.flair()

    def check_report(self):
        pass

    def main(self):
        self.check_hot()
        self.check_report()

if __name__ == "__main__":
    o = Ouija('DimmiOuija')
    o.main()
