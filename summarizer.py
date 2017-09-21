"""Summarize a brief period of DimmiOuija activity"""
import datetime
import time
import bot
import praw

DAYS = 7
TIME_LIMIT = DAYS * 24 * 60 * 60 * 1000
NEWER_THAN = time.time() - TIME_LIMIT

DATE_FORMAT = '%d/%m/%Y'
ANSWER_FORMAT = '#### [{title}]({url})\n\n> {answer}\n\n'

ANSWERED_FLAIR = bot.ANSWERED['text']


class Summarizer():
    """A post in ouija"""

    def __init__(self, subreddit: str) -> None:
        """Initialize."""
        reddit = praw.Reddit(check_for_updates=False)
        dates = Summarizer.__dates()
        self.subreddit = reddit.subreddit(subreddit)
        self.title = 'Risposte dal {from} al {to}'.format(**dates)
        self.name = dates['week']
        self.text = ''

    @staticmethod
    def __dates():
        today = datetime.date.today()
        from_day = today - datetime.timedelta(days=DAYS)
        return {
            'week': today.strftime('%Y_%W'),
            'to': today.strftime(DATE_FORMAT),
            'from': from_day.strftime(DATE_FORMAT)
        }

    def parse_submission(self, submission: praw.models.Submission) -> None:
        """Add the submission to text"""
        params = {
            'title': submission.title,
            'url': submission.url,
            'answer': submission.link_flair_text.replace(ANSWERED_FLAIR, '')
        }
        self.text += ANSWER_FORMAT.format(**params)

    def wiki(self) -> None:
        """Transfer parsed pages to subreddit wiki"""
        text = self.title + '\n\n' + self.text
        with open(self.name + ".md", "w", encoding="utf-8") as fout:
            fout.write(text)
        self.subreddit.wiki[self.title].edit(text, 'Pagina creata')

    def check_submissions(self):
        """Check the hot submission for unanswered post"""
        submissions = self.subreddit.top(time_filter='week', limit=None)
        for submission in submissions:
            if submission.distinguished:
                continue
            if submission.stickied:
                continue
            if not submission.link_flair_text:
                continue
            if not submission.link_flair_text.startswith(ANSWERED_FLAIR):
                continue
            self.parse_submission(submission)

    def main(self):
        """Perform all bot actions"""
        self.check_submissions()
        self.wiki()


if __name__ == "__main__":
    s = Summarizer('DimmiOuija')
    s.main()
