"""Summarize a brief period of DimmiOuija activity"""
import datetime
import json
from collections import Counter
from pathlib import Path
from statistics import StatisticsError, mean, mode
from statistics import median_grouped as median
from typing import Any

import praw
from jinja2 import Environment, FileSystemLoader

DATE_FORMAT = "%d/%m/%Y"


def top_counter(count: Counter, size: int) -> list[tuple[Any, int]]:
    """Return at least 'size' most common, return more in case of same value elements"""
    sorted_values = sorted(count.values(), reverse=True)
    value_limit = sorted_values[size]
    real_size = len([value for value in sorted_values if value >= value_limit])
    return count.most_common(real_size)


def bottom_counter(count: Counter) -> list[tuple[Any, int]]:
    """Return the least common elements"""
    sorted_values = sorted(count.values())
    value_limit = sorted(count.values())[0]
    real_size = len([value for value in sorted_values if value >= value_limit])
    return count.most_common()[real_size:]


def top_answer(questions: dict, size: int):
    """Return at least 'size' most common, return more in case of same value elements"""
    solutions = sorted(questions, key=lambda item: len(item["answer"]), reverse=True)
    limit = len(solutions[size]["answer"])
    longers = [solution for solution in solutions if len(solution["answer"]) >= limit]
    return longers


def bottom_answer(questions: dict):
    """Return the least common elements"""
    solutions = sorted(questions, key=lambda item: len(item["answer"]))
    limit = len(solutions[0]["answer"])
    shorters = [solution for solution in solutions if len(solution["answer"]) == limit]
    return shorters


def time_string(open_time: float | int) -> str:
    """It converts Numeric seconds to italian string"""
    if open_time < 60 * 60 * 2:
        return f"{round(open_time / 60):d} minuti"
    return f"{round(open_time / 60 / 60):d} ore"


class Summarizer:
    """A post in ouija"""

    def __init__(self, subreddit: str) -> None:
        """Initialize."""
        reddit = praw.Reddit(check_for_updates=False)
        self._reddit = reddit
        self.subreddit = reddit.subreddit(subreddit)
        self.load_infos()

    def load_infos(self) -> dict:
        """Read variablies from JSON"""
        # find most recent json file
        ffilepaths = sorted(
            Path("./data").glob("[0-9][0-9][0-9][0-9]_[0-9][0-9].json"), reverse=True
        )
        if not ffilepaths:
            raise ValueError("No data.json found")
        ffilepath = ffilepaths[0]
        if datetime.datetime.now().timestamp() - ffilepath.stat().st_mtime > 60 * 60 * 24 * 14:
            # too old
            raise ValueError("No recent data.json found")
        self.name = ffilepath.parts[-1].split(".")[0]
        with ffilepath.open("rt", encoding="utf-8") as fin:
            questions = json.load(fin)
        self.fullname = datetime.datetime.fromtimestamp(questions[0]["created_utc"]).strftime(
            DATE_FORMAT
        )
        return questions

    def write_answers(self, questions) -> None:
        """Transfer parsed pages to subreddit wiki"""
        env = Environment(loader=FileSystemLoader("."))
        template = env.get_template("wiki.md")
        text = template.render(day=self.fullname, questions=questions)
        with open(f"data/{self.name}.md", "w", encoding="utf-8") as fout:
            fout.write(text)
        self.subreddit.wiki.create(self.name, text, "Pagina creata")

    @staticmethod
    def make_stats(questions):
        """Return statistics of parsed questions with answer"""
        authors = Counter([question["author"] for question in questions])
        solvers = Counter(
            [comment["author"] for question in questions for comment in question["comments"][0:-1]]
        )
        goodbyers = Counter([question["comments"][-1]["author"] for question in questions])
        chars = Counter(
            [
                comment["body"].strip().upper()
                for question in questions
                for comment in question["comments"][0:-1]
            ]
        )
        open_time = [
            (
                question["comments"][-1]["created_utc"] - question["created_utc"],
                question,
            )
            for question in questions
        ]
        open_time = sorted(open_time, key=lambda item: item[0])
        return {
            "authors": authors,
            "solvers": solvers,
            "goodbyers": goodbyers,
            "chars": chars,
            "open_time": open_time,
        }

    def write_stats(self, questions, stats) -> None:
        """Write a <date>_stats.md file with statistics"""
        variables = {
            "day": self.fullname,
            "questions": questions,
            "authors": stats["authors"],
            "solvers": stats["solvers"],
            "goodbyers": stats["goodbyers"],
            "chars": stats["chars"],
            "open_time": stats["open_time"],
            "mediums": len(set(stats["solvers"]) | set(stats["goodbyers"])),
            "charlenght": sum(stats["chars"].values()),
        }
        try:
            answer_len = [len(question["answer"]) for question in questions]
            variables["size"] = {
                "mean": mean(answer_len),
                "median": median(answer_len),
                "mode": mode(answer_len),
            }
        except StatisticsError:
            pass
        try:
            solvers_answer = [answer for answer in stats["solvers"].values()]
            variables["solver"] = {
                "mean": mean(solvers_answer),
                "median": median(solvers_answer),
                "mode": mode(solvers_answer),
            }
        except StatisticsError:
            pass
        try:
            times = [time for time, _ in stats["open_time"]]
            variables["otime"] = {"mean": mean(times), "median": median(times)}
        except StatisticsError:
            pass
        env = Environment(loader=FileSystemLoader("."))
        env.filters["top_counter"] = top_counter
        env.filters["time_string"] = time_string
        env.filters["top_answer"] = top_answer
        env.filters["bottom_answer"] = bottom_answer
        template = env.get_template("stats.md")
        text = template.render(**variables)
        with open(f"data/{self.name}_stats.md", "w", encoding="utf-8") as fout:
            fout.write(text)
        self.subreddit.wiki.create(self.name + "_stats", text, "Pagina creata")
        self.add_wiki()
        with open(f"data/{self.name}_stats.json", "w", encoding="utf-8") as fout:
            json.dump(variables, fout, indent=4)

    def add_wiki(self):
        """Add links in wiki index page"""
        separator = "[](/list-separator)"
        index = self.subreddit.wiki["index"]
        wikitemplate = index.content_md.split(separator)
        new_row = """

### [{text}](/r/{sub}/wiki/{short}) - [Statistiche](/r/{sub}/wiki/{short}_stats)"""
        wikitemplate[1] = (
            new_row.format(text=self.fullname, short=self.name, sub=self.subreddit.display_name)
            + wikitemplate[1]
        )
        text = separator.join(wikitemplate)
        index.edit(text, self.fullname)
        self.subreddit.sticky(1).reply(
            """Un riassunto delle domande e risposte
è [disponibile sulla wiki](/r/{sub}/wiki/{short}),
insieme alle [statistiche](/r/{sub}/wiki/{short}_stats) relative.""".format(
                short=self.name, sub=self.subreddit.display_name
            )
        )

    def caffe_wiki(self, swcaffe: str | None = None):
        wiki_caffe = self._reddit.subreddit(swcaffe).wiki["ambrogio_caffe"]
        lines = wiki_caffe.content_md.replace("\r", "").split("\n")
        section = False
        for i, line in enumerate(lines):
            if "[](/ieri-start)" in line:
                section = True
                continue
            if "[](/ieri-end)" in line:
                break
            if section and self.subreddit.display_name in line:
                line = """* Ieri abbiamo giocato su r/DimmiOuija,
è disponibile un [riassunto](/r/{sub}/wiki/{short})
e le [statistiche](/r/{sub}/wiki/{short}_stats) relative""".format(
                    short=self.name, sub=self.subreddit.display_name
                )
                lines[i] = line
                break
        wiki_caffe.edit("\n".join(lines), "DimmiOuija chiusura")


def load_all():
    ffilepaths = Path("./data").glob("[0-9][0-9][0-9][0-9]_[0-9][0-9].json")
    if not ffilepaths:
        raise ValueError("No data/*.json found")

    plays = []
    for ffilepath in ffilepaths:
        try:
            with ffilepath.open("rt", encoding="utf-8") as fin:
                plays.extend(json.load(fin))
        except json.decoder.JSONDecodeError as e:
            print(e, ffilepath)
    return plays


def sql_all():
    from dump import Dumper

    ffilepaths = Path("./data").glob("[0-9][0-9][0-9][0-9]_[0-9][0-9].json")
    if not ffilepaths:
        raise ValueError("No data/*.json found")

    summary = Dumper("DimmiOuija")
    questions = []
    for ffilepath in ffilepaths:
        try:
            with ffilepath.open("rt", encoding="utf-8") as fin:
                questions = json.load(fin)
        except json.decoder.JSONDecodeError as e:
            print(e, ffilepath)
        summary._update_week(questions)
        summary.to_sql(questions)
        print("ok", ffilepath, len(questions))


def main():
    """Perform all bot actions"""
    summary = Summarizer("DimmiOuija")
    questions = summary.load_infos()
    if not questions:
        print("ERROR - Data missing - Please run dump.py first")
        return
    summary.write_answers(questions)
    stats = summary.make_stats(questions)
    summary.write_stats(questions, stats)
    summary.caffe_wiki("italy")


if __name__ == "__main__":
    main()
