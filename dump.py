"""Summarize a brief period of DimmiOuija activity"""
from __future__ import annotations

import datetime
import json
import sqlite3
from typing import TYPE_CHECKING, Dict, List, Optional

import praw

if TYPE_CHECKING:
    from praw.models.reddit.comment import Comment
    from praw.models.reddit.submission import Submission

import bot

ANSWERED_FLAIR = bot.ANSWERED["text"]
GOODBYE = bot.GOODBYE


def find_solution(submission: Submission, solution: str) -> Optional[List[Comment]]:
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
            sol = ""
            while tree[0].parent() != submission:
                tree = [tree[0].parent()] + tree
                sol = tree[0].body.strip().lstrip("\\").upper() + sol
            if sol == solution:
                return tree
    # Solution not found, include deleted
    for comment in submission.comments.list():
        if comment.removed:
            continue
        if comment.distinguished:
            continue
        if GOODBYE.match(comment.body.strip()):
            # solution candidate!
            tree = [comment]
            sol = ""
            while tree[0].parent() != submission:
                tree = [tree[0].parent()] + tree
                if tree[0].body == "[deleted]" and solution[-len(sol) :] == sol:
                    # comment is deleted and the solution so far is good
                    sol = solution[-len(sol) - 1] + sol
                elif tree[0].body == "[deleted]" and len(sol) == 0:
                    # comment is deleted and solution is empty
                    sol = solution[-1]
                else:
                    sol = tree[0].body.strip().lstrip("\\").upper() + sol
            if sol == solution:
                # tree is ok
                for i, c in enumerate(tree):
                    if c.body == "[deleted]":
                        # overwrite body
                        c.__dict__["body"] = solution[i]
                return tree
    return None


def author(content: praw.models.reddit.mixins.UserContentMixin) -> str:
    """Extract author from"""
    if content.author:
        return content.author.name
    return "[deleted]"


class Dumper:
    """Save answered thead in a json"""

    def __init__(self, subreddit: str) -> None:
        """Initialize."""
        reddit = praw.Reddit(check_for_updates=False)
        self.subreddit = reddit.subreddit(subreddit)
        self._con = sqlite3.connect("data/dump.sqlite3")
        self.week: Optional[str] = None

    def get_questions(self) -> List[Dict]:
        """Check the hot submission of answered posts"""
        submissions = self.subreddit.top(time_filter="week", limit=None)
        questions = []  # type: List[Dict]

        def parse_submission(submission: Submission) -> None:
            """Add the submission to text"""
            params = {
                "title": submission.title,
                "url": submission.url,
                "name": submission.name,
                "score": submission.score,
                "created_utc": submission.created_utc,
                "_thread": submission,
                "author": author(submission),
                "permalink": submission.permalink,
                "answer": submission.link_flair_text.replace(ANSWERED_FLAIR, ""),
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
            self._update_week(questions)
        return questions

    def _update_week(self, questions):
        self.week = datetime.datetime.fromtimestamp(questions[0]["created_utc"]).strftime("%Y_%W")

    @staticmethod
    def add_threads(questions) -> None:
        """Add comments section to questions"""

        def parse_comment(comment: Comment) -> Dict:
            """Add the submission to text"""
            params = {
                "body": comment.body,
                "name": comment.name,
                "score": comment.score,
                "permalink": comment.permalink,
                "created_utc": comment.created_utc,
                "author": author(comment),
            }
            return params

        for question in questions:
            comments = find_solution(question["_thread"], question["answer"])
            if not comments:
                print("No solution found:", question["_thread"])
            else:
                question["comments"] = [parse_comment(comment) for comment in comments]
            del question["_thread"]

    def write_json(self, questions):
        """Write variablies to JSON"""
        with open("data/{}.json".format(self.week), "wt", encoding="utf-8") as fout:
            json.dump(questions, fout, indent=4)

    def to_sql(self, questions) -> None:
        """Write variablies to Sqlite file"""
        cur = self._con.cursor()
        cur.executemany(
            """insert into questions(
            id,
            title,
            score,
            created_utc,
            author,
            permalink,
            answer,
            week) values (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    q["name"],
                    q["title"],
                    q["score"],
                    int(q["created_utc"]),
                    q["author"],
                    q["permalink"],
                    q["answer"],
                    self.week,
                )
                for q in questions
            ],
        )
        cur.executemany(
            """insert into comments(
            id,
            parent_id,
            body,
            created_utc,
            author,
            score) values (?, ?, ?, ?, ?, ?)""",
            [
                (c["name"], q["name"], c["body"], int(c["created_utc"]), c["author"], c["score"])
                for q in questions
                for c in q["comments"]
            ],
        )
        self._con.commit()


def main():
    """Perform all bot actions"""
    summary = Dumper("DimmiOuija")
    questions = summary.get_questions()
    summary.add_threads(questions)
    summary.to_sql(questions)
    summary.write_json(questions)


if __name__ == "__main__":
    main()
