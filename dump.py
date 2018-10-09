"""Summarize a brief period of DimmiOuija activity"""
import datetime
import json
from typing import Dict, List

import praw
from praw.models.reddit.comment import Comment
from praw.models.reddit.submission import Submission

import bot

ANSWERED_FLAIR = bot.ANSWERED['text']
GOODBYE = bot.GOODBYE


def find_solution(submission: Submission, solution: str) -> List[Comment]:
    """Given a submission and the solution,
       RETURNS the list of comment, in order, including the Goodbye"""
    submission.comments.replace_more(limit=None)
    for comment in submission.comments.list():
        if comment.removed:
            continue
        if comment.distinguished:
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


class Dumper():
    """Save answered thead in a json"""
    def __init__(self, subreddit: str) -> None:
        """Initialize."""
        reddit = praw.Reddit(check_for_updates=False)
        self.subreddit = reddit.subreddit(subreddit)

    def get_questions(self) -> List[Dict]:
        """Check the hot submission of answered posts"""
        submissions = self.subreddit.top(time_filter='week', limit=None)
        questions = []  # type: List[Dict]

        def parse_submission(submission: Submission) -> None:
            """Add the submission to text"""
            params = {
                'title': submission.title,
                'url': submission.url,
                'name': submission.name,
                'score': submission.score,
                'created_utc': submission.created_utc,
                '_thread': submission,
                'author': author(submission),
                'permalink': submission.permalink,
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

    @staticmethod
    def add_threads(questions) -> None:
        """Add comments section to questions"""
        def parse_comment(comment: Comment) -> Dict:
            """Add the submission to text"""
            params = {
                'body': comment.body,
                'name': comment.name,
                'score': comment.score,
                'permalink': comment.permalink,
                'created_utc': comment.created_utc,
                'author': author(comment),
            }
            return params
        for question in questions:
            comments = find_solution(question['_thread'], question['answer'])
            if not comments:
                print('No solution found:', question['_thread'])
                continue
            question['comments'] = [parse_comment(comment) for comment in comments]
            del question['_thread']

    @staticmethod
    def write_json(questions):
        """Write variablies to JSON"""
        name = datetime.date.today().strftime('%Y_%W')
        with open('data/{}.json'.format(name), 'wt', encoding="utf-8") as fout:
            json.dump(questions, fout, indent=4)


def main():
    """Perform all bot actions"""
    summary = Dumper('DimmiOuija')
    questions = summary.get_questions()
    summary.add_threads(questions)
    summary.write_json(questions)


if __name__ == "__main__":
    main()
