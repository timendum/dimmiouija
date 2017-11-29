"""Summarize a brief period of DimmiOuija activity"""
from collections import defaultdict
import datetime
import time
from typing import List, Dict, Tuple
import bot
import praw
from praw.models.reddit.comment import Comment
from praw.models.reddit.submission import Submission

DAYS = 7
TIME_LIMIT = DAYS * 24 * 60 * 60 * 1000
NEWER_THAN = time.time() - TIME_LIMIT

DATE_FORMAT = '%d/%m/%Y'
ANSWER_FORMAT = '#### [{title}]({url})\n\n> {answer}\n\n'

ANSWERED_FLAIR = bot.ANSWERED['text']
GOODBYE = bot.GOODBYE


def find_solution(submission: Submission, solution: str) -> List[Comment]:
    """Given a submission and the solution,
       RETURNS the list of comment, in order, including the Goodbye"""
    submission.comments.replace_more(limit=None)
    for comment in submission.comments.list():
        if comment.removed:
            continue
        if GOODBYE.match(comment.body.strip()):
            # solution candidate!
            tree = [comment]
            sol = ''
            while tree[0].parent() != submission:
                tree = [tree[0].parent()] + tree
                sol = tree[0].body.strip().upper() + sol
            if sol == solution:
                return tree
    return None


def author(content: praw.models.reddit.mixins.UserContentMixin) -> str:
    """Extract author from """
    if content.author:
        return content.author.name
    return '[deleted]'


class Summarizer():
    """A post in ouija"""

    def __init__(self, subreddit: str) -> None:
        """Initialize."""
        reddit = praw.Reddit(check_for_updates=False)
        dates = Summarizer.__dates()
        self.reddit = reddit
        self.subreddit = reddit.subreddit(subreddit)
        self.title_wiki = 'Risposte dal {from} al {to}'.format(**dates)
        self.title_stats = 'Statistiche dal {from} al {to}'.format(**dates)
        self.name = dates['week']
        self.questions = []  # type: List[Dict]

    @staticmethod
    def __dates():
        today = datetime.date.today()
        from_day = today - datetime.timedelta(days=DAYS)
        return {
            'week': today.strftime('%Y_%W'),
            'to': today.strftime(DATE_FORMAT),
            'from': from_day.strftime(DATE_FORMAT)
        }

    def parse_submission(self, submission: Submission) -> None:
        """Add the submission to text"""
        params = {
            'title': submission.title,
            'url': submission.url,
            'thread': submission,
            'answer': submission.link_flair_text.replace(ANSWERED_FLAIR, '')
        }
        self.questions.append(params)

    def write_answers(self) -> None:
        """Transfer parsed pages to subreddit wiki"""
        text = ''.join([ANSWER_FORMAT.format(**question) for question in self.questions])
        text = self.title_wiki + '\n\n' + text
        with open(self.name + ".md", "w", encoding="utf-8") as fout:
            fout.write(text)
        # Disabled, Reddit returns an error
        # self.subreddit.wiki[self.title].create(text, 'Pagina creata')

    def make_stats(self) -> Dict[str, List[Tuple[str, int]]]:
        """Return statistics of parsed questions with answer"""
        authors = defaultdict(int)  # type: Dict[str, int]
        solvers = defaultdict(int)  # type: Dict[str, int]
        goodbyers = defaultdict(int)  # type: Dict[str, int]
        chars = defaultdict(int)  # type: Dict[str, int]
        open_time = {}  # type: Dict[str, int]
        for question in self.questions:
            submission = question['thread']
            authors[author(submission)] += 1
            stree = find_solution(submission, question['answer'])  # solution tree
            if not stree:
                print(submission)
                continue
            goodbye = stree.pop()
            goodbyers[author(goodbye)] += 1
            open_time[submission.id] = goodbye.created_utc - submission.created_utc
            for comment in stree:
                solvers[author(comment)] += 1
                chars[comment.body.strip().upper()] += 1
        return {
            'authors': sorted(authors.items(), key=lambda item: item[1]),
            'solvers': sorted(solvers.items(), key=lambda item: item[1]),
            'goodbyers': sorted(goodbyers.items(), key=lambda item: item[1]),
            'chars': sorted(chars.items(), key=lambda item: item[1]),
            'open_time': sorted(open_time.items(), key=lambda item: item[1]),
        }

    def _answer_size(self, solutions: List[Tuple[str, str]]) -> str:
        text = '## Lunghezza delle risposte\n\n'
        # max
        text += 'Le risposte più lunghe sono state: \n\n'
        value = None
        for idx, answer in enumerate(reversed(solutions)):
            if value != answer[1] and idx > 4:
                break
            value = answer[1]
            text += '1. [%s](%s) (%d)\n' % (answer[1],
                                            self.reddit.submission(id=answer[0]).permalink,
                                            len(answer[1]))
        # min
        text += '\n'
        minsize = len(solutions[0][1])
        minsized = []
        for solution in solutions:
            if len(solution[1]) == minsize:
                minsized.append(solution)
            else:
                break
        if len(minsized) == 1:
            text += 'La risposta più corta (%d caratteri) è stata: ' % (minsize)
            text += '[%s](%s)\n\n' % (minsized[0][1],
                                      self.reddit.submission(id=minsized[0][0]).permalink)
        else:
            text += 'Le risposte più corte (%d caratteri) sono state: \n\n' % (minsize)
            for answer in minsized:
                text += '* [%s](%s)\n' % (answer[1], self.reddit.submission(id=answer[0]).permalink)
        return text

    def _authors(self, authors: List[Tuple[str, int]]) -> str:
        text = '## Autori delle domande\n\n'
        text += 'Gli utenti che hanno posto più domande sono stati: \n\n'
        value = None
        for idx, user in enumerate(reversed(authors)):
            if value != user[1] and idx > 4:
                break
            value = user[1]
            text += '1. /u/%s (%s)\n' % (user[0], user[1])
        return text

    def _solvers(self, solvers: List[Tuple[str, int]]) -> str:
        text = '## Autori delle risposte\n\n'
        text += 'Gli utenti che hanno contribuito di più alle risposte sono stati: \n\n'
        value = None
        for idx, user in enumerate(reversed(solvers)):
            if value != user[1] and idx > 9:
                break
            value = user[1]
            text += '1. /u/%s (%s)\n' % (user[0], user[1])
        return text

    def _open_time(self, open_time: List[Tuple[str, int]]) -> str:
        text = '## Tempi delle risposte\n\n'
        text += 'La classifica delle tempi di chiusura: \n\n'
        submission = None
        for idx, question in enumerate(open_time):
            if idx > 4:
                break
            submission = self.reddit.submission(id=question[0])
            text += '1. [%s](%s) (%s minuti)\n' % (submission.title, submission.permalink,
                                                   round(question[1] / 60))
        text += '\n...\n\n'
        submission = self.reddit.submission(id=open_time[-1][0])
        text += 'Ultimo: [%s](%s)' % (submission.title, submission.permalink)
        if open_time[-1][1] < 60 * 60 * 2:
            text += '(%s minuti)\n' % round(open_time[-1][1] / 60)
        else:
            text += '(%s ore)\n' % round(open_time[-1][1] / 60 / 60)
        return text

    def _goodbyers(self, goodbyers: List[Tuple[str, int]]) -> str:
        if next(reversed(goodbyers))[1] == 1:
            return ''
        text = '## Autori dei Goodbye\n\n'
        text += 'Gli utenti che hanno inserito più Goodbye: \n\n'
        value = None
        for idx, user in enumerate(reversed(goodbyers)):
            if value != user[1] and idx > 4:
                break
            text += '1. /u/%s (%s)\n' % (user[0], user[1])
        return text

    def _chars(self, chars: List[Tuple[str, int]]) -> str:
        text = '## I caratteri\n\n'
        text += 'I caratteri più utilizzati sono stati: \n\n'
        text += 'Char | Freq\n---|---\n'
        for c in reversed(chars):
            text += '%s | %d\n' % (c[0], c[1])
        return text

    def write_stats(self) -> None:
        stats = self.make_stats()
        solutions = self.solutions()
        text = '#' + self.title_stats + '\n\n'
        text += self._answer_size(solutions) + '\n'
        text += self._authors(stats['authors']) + '\n'
        text += self._solvers(stats['solvers']) + '\n'
        text += self._goodbyers(stats['goodbyers']) + '\n'
        text += self._chars(stats['chars']) + '\n'
        text += self._open_time(stats['open_time']) + '\n'
        with open(self.name + "_stats.md", "w", encoding="utf-8") as fout:
            fout.write(text)

    def solutions(self) -> List[Tuple[str, str]]:
        """Return a List of (id of submission, solution text)"""
        solutions = {}  # type: Dict[str, str]
        for question in self.questions:
            submission = question['thread']
            solutions[submission.id] = question['answer']
        return sorted(solutions.items(), key=lambda item: len(item[1]))

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
        #self.wiki()


if __name__ == "__main__":
    SUMMARY = Summarizer('DimmiOuija')
    SUMMARY.check_submissions()
    SUMMARY.write_stats()
