"""Summarize a brief period of DimmiOuija activity"""
import datetime
import json
import re
import sqlite3
from typing import TYPE_CHECKING

import praw

if TYPE_CHECKING:
    from praw.models import Comment, Submission

import bot
import ruota

ANSWERED_FLAIR = bot.ANSWERED["text"]
GOODBYE = bot.GOODBYE
RUOTA_ANSWERED = ruota.ANSWERED["text"]


def find_solution(submission: "Submission", solution: str) -> "list[Comment] | None":
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
        reddit = praw.Reddit(check_for_updates=False, client_secret=None)
        self.subreddit = reddit.subreddit(subreddit)
        self._con = sqlite3.connect("data/dump.sqlite3")
        self.week: str | None = None

    def get_questions(self) -> list[dict]:
        """Check the hot submission of answered posts"""
        submissions = self.subreddit.top(time_filter="week", limit=None)
        questions = []  # type: list[dict]

        def parse_submission(submission: "Submission") -> None:
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
            if not submission.link_flair_text or not submission.link_flair_text.startswith(
                ANSWERED_FLAIR
            ):
                print("Skipped: ", submission.permalink)
                continue
            parse_submission(submission)
            self._update_week(questions)
        return questions

    def _update_week(self, questions):
        self.week = datetime.datetime.fromtimestamp(questions[0]["created_utc"]).strftime("%Y_%W")

    def get_ruota(self) -> list[dict]:
        """Check the hot submission of answered ruota"""
        submissions = self.subreddit.top(time_filter="week", limit=None)
        questions = []  # type: list[dict]

        def parse_submission(submission: "Submission") -> None:
            """Add the submission to text"""
            answer_row = submission.selftext.strip().split("\n")[2]
            params = {
                "title": submission.title,
                "url": submission.url,
                "name": submission.name,
                "score": submission.score,
                "created_utc": submission.created_utc,
                "_thread": submission,
                "author": author(submission),
                "permalink": submission.permalink,
                "answer": ":".join(answer_row.split(":")[1:]).strip(),
            }
            questions.append(params)

        for submission in submissions:
            if not submission.link_flair_text or not submission.link_flair_text.startswith(
                RUOTA_ANSWERED
            ):
                continue
            parse_submission(submission)
            print("Ruota: ", submission.permalink)
        return questions

    @staticmethod
    def add_ruota(questions) -> None:
        """Add comments section to ruota"""

        def parse_comment(comment: "Comment") -> dict:
            """Add the submission to text"""
            params = {
                "body": comment.body.strip(),
                "name": comment.name,
                "score": comment.score,
                "permalink": comment.permalink,
                "created_utc": comment.created_utc,
                "author": author(comment),
            }
            return params

        for question in questions:
            comments = []
            question["_thread"].comments.replace_more(limit=None)
            solution = False
            for c in question["_thread"].comments.list():
                if c.removed:
                    continue
                if c.distinguished:
                    continue
                if c.locked:
                    continue
                body = c.body.strip().upper()
                if len(body) > 1:
                    if re.sub(r"\W+", "", body) != re.sub(r"\W+", "", question["answer"]):
                        continue
                    solution = True
                comments.append(parse_comment(c))
            if not solution:
                print("No solution found:", question["_thread"])
                question["comments"] = []
            else:
                comments = sorted(comments, key=lambda c: (len(c["body"]), c["created_utc"]))
                question["comments"] = comments
            del question["_thread"]

    @staticmethod
    def add_threads(questions) -> None:
        """Add comments section to questions"""

        def parse_comment(comment: "Comment") -> dict:
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

    def write_json(self, questions, ruote):
        """Write variablies to JSON"""
        with open(f"data/{self.week}.json", "w", encoding="utf-8") as fout:
            json.dump(questions, fout, indent=4)
        with open(f"data/{self.week}-ruote.json", "w", encoding="utf-8") as fout:
            json.dump(ruote, fout, indent=4)

    def to_sql(self, questions, ruote) -> None:
        """Write variablies to Sqlite file"""
        cur = self._con.cursor()
        cur.executemany(
            """INSERT OR REPLACE INTO questions(
            id,
            title,
            score,
            created_utc,
            author,
            permalink,
            answer,
            week) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
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
            """INSERT OR REPLACE into comments(
            id,
            parent_id,
            body,
            created_utc,
            author,
            score) VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (c["name"], q["name"], c["body"], int(c["created_utc"]), c["author"], c["score"])
                for q in questions
                for c in q["comments"]
            ],
        )
        cur.executemany(
            """INSERT OR REPLACE INTO ruote(
            id,
            title,
            score,
            created_utc,
            author,
            permalink,
            answer,
            week) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
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
                for q in ruote
            ],
        )
        cur.executemany(
            """INSERT OR REPLACE into rcomments(
            id,
            parent_id,
            body,
            created_utc,
            author,
            score) VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (c["name"], q["name"], c["body"], int(c["created_utc"]), c["author"], c["score"])
                for q in ruote
                for c in q["comments"]
            ],
        )
        self._con.commit()


def main():
    """Perform all bot actions"""
    summary = Dumper("DimmiOuija")
    questions = summary.get_questions()
    # summary.add_threads(questions)
    ruote = summary.get_ruota()
    summary.add_ruota(ruote)
    summary.to_sql(questions, ruote)
    summary.write_json(questions, ruote)


if __name__ == "__main__":
    main()
