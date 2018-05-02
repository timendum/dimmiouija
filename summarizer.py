"""Summarize a brief period of DimmiOuija activity"""
import datetime
import json
import unicodedata
from collections import defaultdict
from statistics import median_grouped as median
from statistics import mean, mode, StatisticsError
from typing import Dict, List, Tuple, Union

import praw
from praw.models.reddit.comment import Comment
from praw.models.reddit.submission import Submission

import bot

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
        self.title_wiki = 'Risposte del {day}'.format(**dates)
        self.title_stats = 'Statistiche dal {day}'.format(**dates)
        self.name = dates['week']

    @staticmethod
    def __dates():
        today = datetime.date.today()
        day = today - datetime.timedelta(days=1)
        return {'week': today.strftime('%Y_%W'), 'day': day.strftime(DATE_FORMAT)}

    def write_answers(self, questions: List[Dict]) -> None:
        """Transfer parsed pages to subreddit wiki"""
        text = ''.join([ANSWER_FORMAT.format(**question) for question in questions])
        text = self.title_wiki + '\n\n' + text
        with open(self.name + ".md", "w", encoding="utf-8") as fout:
            fout.write(text)
        # Disabled, Reddit returns an error
        # self.subreddit.wiki[self.title].create(text, 'Pagina creata')

    @staticmethod
    def make_stats(questions: List[Dict]) -> Dict[str, List[Tuple[str, int]]]:
        """Return statistics of parsed questions with answer"""
        authors = defaultdict(int)  # type: Dict[str, int]
        solvers = defaultdict(int)  # type: Dict[str, int]
        goodbyers = defaultdict(int)  # type: Dict[str, int]
        chars = defaultdict(int)  # type: Dict[str, int]
        open_time = {}  # type: Dict[str, int]
        for question in questions:
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
                char = comment.body.strip().upper()
                char = unicodedata.normalize('NFD', char).encode('ascii', 'ignore').decode('utf8')
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
        text += 'Le risposte più lunghe sono state:\n\n'
        value = None
        for idx, answer in enumerate(reversed(solutions)):
            if value != answer[1] and idx > 4:
                break
            value = answer[1]
            text += '1. [{text}]({url}) ({extra:d})\n'.format(
                text=answer[1],
                url=self.reddit.submission(id=answer[0]).permalink,
                extra=len(answer[1]))
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
            text += 'La risposta più corta ({:d} caratteri) è stata: '.format(minsize)
            text += '[{text}]({url})\n\n'.format(
                text=minsized[0][1], url=self.reddit.submission(id=minsized[0][0]).permalink)
        else:
            text += 'Le risposte più corte ({:d} caratteri) sono state: \n\n'.format(minsize)
            for answer in minsized:
                text += '* [{text}]({url})\n'.format(
                    text=answer[1], url=self.reddit.submission(id=answer[0]).permalink)
            text += '\n'
        # averange
        text += '### Statistiche\n\n'
        text += 'La lunghezza media delle risposte è stata: {:g}  \n'.format(
            mean([len(solution[1]) for solution in solutions]))
        text += 'La mediana della lunghezze delle risposte è stata: {:g}  \n'.format(
            median([len(solution[1]) for solution in solutions]))
        try:
            text += 'La moda della lunghezze delle risposte è stata: {:g}\n'.format(
                mode([len(solution[1]) for solution in solutions]))
        except StatisticsError:
            pass
        return text

    @staticmethod
    def _authors(authors: List[Tuple[str, int]]) -> str:
        text = '## Autori delle domande\n\n'
        text += 'Gli utenti che hanno posto più domande sono stati: \n\n'
        value = None
        for idx, user in enumerate(reversed(authors)):
            if value != user[1] and idx > 4:
                break
            value = user[1]
            text += '1. /u/{text} ({extra})\n'.format(text=user[0], extra=user[1])
        return text

    @staticmethod
    def _solvers(solvers: List[Tuple[str, int]]) -> str:
        text = '## Autori delle risposte\n\n'
        text += 'Alle risposte hanno partecipato {:d} spiriti.\n\n'.format(len(solvers))
        text += 'Gli utenti che hanno contribuito di più alle risposte sono stati: \n\n'
        value = None
        for idx, user in enumerate(reversed(solvers)):
            if value != user[1] and idx > 9:
                break
            value = user[1]
            text += '1. /u/{text} ({extra})\n'.format(text=user[0], extra=user[1])
        # averange
        text += '\n### Statistiche\n\n'
        text += 'Il numero medio di lettere per utente è stato: {:g}  \n'.format(
            mean([solver[1] for solver in solvers]))
        text += 'La mediana del numero di lettere per utente è stato: {:g}  \n'.format(
            median([solver[1] for solver in solvers]))
        text += 'La moda del numero di lettere per utente è stato: {:g}\n'.format(
            mode([solver[1] for solver in solvers]))
        return text

    def _open_time(self, open_time: List[Tuple[str, int]]) -> str:
        def time_string(open_time: Union[float, int]) -> str:
            """It converts Numeric seconds to italian string"""
            if open_time < 60 * 60 * 2:
                return '{:d} minuti'.format(round(open_time / 60))
            return '{:d} ore'.format(round(open_time / 60 / 60))

        text = '## Tempi delle risposte\n\n'
        text += 'La classifica delle tempi di chiusura: \n\n'
        submission = None
        for idx, question in enumerate(open_time):
            if idx > 4:
                break
            submission = self.reddit.submission(id=question[0])
            text += '1. [{text}]({url}) ({extra:d} minuti)\n'.format(
                text=submission.title, url=submission.permalink, extra=round(question[1] / 60))
        text += '\n...\n\n'
        submission = self.reddit.submission(id=open_time[-1][0])
        text += 'Ultimo: [{text}]({url})'.format(text=submission.title, url=submission.permalink)
        text += '({})\n'.format(time_string(open_time[-1][1]))
        # averange
        text += '\n### Statistiche\n\n'
        text += 'Le domande hanno dovuto attendere per una risposta mediamente {}  \n'.format(
            time_string(mean([timing[1] for timing in open_time])))
        text += 'Il tempo mediano di apertura per le domande è stato: {}\n'.format(
            time_string(median([timing[1] for timing in open_time])))
        return text

    @staticmethod
    def _goodbyers(goodbyers: List[Tuple[str, int]]) -> str:
        if next(reversed(goodbyers))[1] == 1:
            return ''
        text = '## Autori dei Goodbye\n\n'
        text += 'Gli utenti che hanno inserito più Goodbye: \n\n'
        value = None
        for idx, user in enumerate(reversed(goodbyers)):
            if value != user[1] and idx > 4:
                break
            text += '1. /u/{user} ({extra})\n'.format(user=user[0], extra=user[1])
        return text

    @staticmethod
    def _chars(charstats: List[Tuple[str, int]]) -> str:
        text = '## I caratteri\n\n'
        text += 'Sono stati utilizzati {:d} caratteri diversi: \n\n'.format(len(charstats))
        text += 'I caratteri più utilizzati sono stati: \n\n'
        text += 'Char | Freq\n---|---\n'
        for charstat in reversed(charstats):
            text += '{} | {}\n'.format(charstat[0], charstat[1])
        text += '\n^(Nota: i caratteri sono stati normalizzati su codifica ASCII)\n'
        return text

    @staticmethod
    def _basics(solutions, stats) -> str:
        text = '## Partecipazione\n\n'
        text += 'Gli spiriti hanno risposto a {:d} domande.\n\n'.format(len(solutions))
        text += 'Che sono presentate presentate da {:d} questionanti.\n\n'.format(
            len(stats['authors']))
        mediums = set([author[0] for author in stats['solvers']]) | \
                  set([author[0] for author in stats['goodbyers']])
        text += 'Hanno partecipato {:d} medium.\n\n'.format(len(mediums))
        text += 'Le risposte complessivamente sono lunghe {:d} caratteri.\n'.format(
            sum([charstat[1] for charstat in stats['chars']]))
        return text

    def write_stats(self, solutions: List[Tuple[str, str]], stats) -> None:
        """Write a <time>_stats.md file with statistics"""
        text = '#' + self.title_stats + '\n\n'
        text += self._basics(solutions, stats) + '\n'
        text += self._answer_size(solutions) + '\n'
        text += self._authors(stats['authors']) + '\n'
        text += self._solvers(stats['solvers']) + '\n'
        text += self._goodbyers(stats['goodbyers']) + '\n'
        text += self._chars(stats['chars']) + '\n'
        text += self._open_time(stats['open_time']) + '\n'
        with open(self.name + "_stats.md", "w", encoding="utf-8") as fout:
            fout.write(text)

    @staticmethod
    def solutions(questions: List[Dict]) -> List[Tuple[str, str]]:
        """Return a List of (id of submission, solution text)"""
        solutions = {}  # type: Dict[str, str]
        for question in questions:
            submission = question['thread']
            solutions[submission.id] = question['answer']
        return sorted(solutions.items(), key=lambda item: len(item[1]))

    def get_questions(self) -> List[Dict]:
        """Check the hot submission of answered posts"""
        submissions = self.subreddit.top(time_filter='week', limit=None)
        questions = []  # type: List[Dict]

        def parse_submission(submission: Submission) -> None:
            """Add the submission to text"""
            params = {
                'title': submission.title,
                'url': submission.url,
                'thread': submission,
                'answer': submission.link_flair_text.replace(ANSWERED_FLAIR, '')
            }
            questions.append(params)

        for submission in submissions:
            if submission.distinguished:
                continue
            if submission.stickied:
                continue
            if not submission.link_flair_text:
                continue
            if not submission.link_flair_text.startswith(ANSWERED_FLAIR):
                continue
            parse_submission(submission)
        return questions

    def save_infos(self, solutions, stats):
        """Write variablies to JSON"""
        state = {'solutions': solutions, 'stats': stats}
        with open('{}.json'.format(self.name), 'wt', encoding="utf-8") as fout:
            json.dump(state, fout)

    def load_infos(self):
        """Read variablies from JSON"""
        with open('{}.json'.format(self.name), 'rt', encoding="utf-8") as fin:
            state = json.load(fin)
        return state['solutions'], state['stats']


def main():
    """Perform all bot actions"""
    summary = Summarizer('DimmiOuija')
    questions = summary.get_questions()
    summary.write_answers(questions)
    solutions = summary.solutions(questions)
    if len(questions) < 1:
        print('No question found')
        return
    stats = summary.make_stats(questions)
    summary.save_infos(solutions, stats)
    # solutions, stats = summary.load_infos()
    summary.write_stats(solutions, stats)


if __name__ == "__main__":
    main()
