"""Ruota"""

import argparse
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta

import praw

MAX_LETTERS = 1  #   max attempts in DELTA_LETTERS hours
MAX_ANSWERS = 2  #   max attempts in DELTA_ANSWERS hours
DELTA_LETTERS = 1  # after how many hours we reset the number of attempts for LETTERS
DELTA_ANSWERS = 2  # after how many hours we reset the number of attempts for ANSWERS

UNANSWERED = {
    "text": "Ruota della fortuna",
    "css_class": "unanswered",
    "flair_template_id": "64726886-8231-11ee-8f3d-0edd18bab5f8",
}
ANSWERED = {
    "text": "Indovinato!",
    "css_class": "answered",
    "flair_template_id": "7094d068-8231-11ee-b8f5-16ef56049ed2",
}
TIME_LIMIT = 24 * 60 * 60 * 1000
YESTERDAY = time.time() - TIME_LIMIT
OLD = time.time() - (TIME_LIMIT / 2)

LOGGER = logging.getLogger(__file__)
LOGGER.addHandler(logging.NullHandler())
LOGGER.setLevel(logging.ERROR)

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZÀÈÉÌÒÙ"

LETTER_MAX = """Ciao,
devi aspettare di più per poter chiedere un'altra lettera.
"""
LETTER_OK = """Ciao u/{author},  
la lettera "`{body}`" appare nella frase.
"""  # noqa
LETTER_NO = """Ciao u/{author},  
la lettera "`{body}`" NON compare nella frase.
"""  # noqa
LETTER_INVALID = """La lettera "`{body}`" non è tra quelle valide:

> {LETTERS}
"""
ANSWER_MAX = """Ciao,  
devi aspettare di più per poter fare un'altro tentativo.
"""  # noqa
ANSWER_OK = """Ottimo lavoro u/{author},  
Hai indovinato la soluzione: `{body}`

Erano state rivelate {ncurrent} lettere.
"""  # noqa
ANSWER_NO = """Ciao u/{author},  
purtroppo il tuo commento non è la frase da indovinare.

> {body}
"""  # noqa


class OuijaPost:
    """A post in ouija"""

    def __init__(self, post: "praw.reddit.models.Submission", solution: str) -> None:
        """Initialize."""
        self._post = post
        self.solution = solution
        self.uletters = defaultdict(int)  # type: dict[str, int]
        self.uanswers = defaultdict(int)  # type: dict[str, int]
        if not self._post.link_flair_text:
            return
        if (
            self._post.link_flair_text != UNANSWERED["text"]
            and self._post.link_flair_text != ANSWERED["text"]
        ):
            return
        self.current = post.selftext.strip().split("\n")[2]
        if self._post.link_flair_text != UNANSWERED["text"]:
            return
        self.missing = set(
            post.selftext.strip().split("\n")[4].split(":")[1].strip().replace(" ", "")
        )
        now = datetime.now()
        self._latest_letter = (now - timedelta(hours=DELTA_LETTERS)).timestamp()
        self._latest_answer = (now - timedelta(hours=DELTA_ANSWERS)).timestamp()
        LOGGER.debug("Post: %s", post.permalink)
        LOGGER.debug("Current: %s", self.current)
        LOGGER.debug("Target : %s", self.solution)
        if len(self.solution) != len(self.current):
            e = f"Wrong solution: {self.solution} vs {self.current}"
            raise ValueError(e)
        LOGGER.debug("Missing: %s", self.missing)

    def is_unanswered(self) -> bool:
        """Check if the submission is Unanswered"""
        if not self._post.link_flair_text:
            return False
        return self._post.link_flair_text == UNANSWERED["text"]

    def process(self) -> bool:
        """Check for answers in the comments and delete wrong comments"""
        self._post.comment_sort = "new"
        self._post.comments.replace_more(limit=None)
        return self.browse_comments(self._post)

    def already_replied(self, comment: "praw.reddit.models.Comment") -> bool | str:
        """Return False or the username in the reply from the bot"""
        for r in comment.replies:
            if r.author != self._post.author:
                continue
            if r.removed:
                continue
            try:
                return re.search(r"u/([A-Za-z0-9_-]+)", r.body)[1]
            except TypeError:
                return True
        return False

    @staticmethod
    def _reply(comment: "praw.reddit.models.Comment", remove: bool, stmpl: str, **fargs):
        author = comment.author.name
        body = comment.body.strip().upper()
        comment.reply(body=stmpl.format(author=author, body=body, **fargs)).mod.lock()
        if remove:
            comment.mod.remove()

    def _check_letter(self, comment: "praw.reddit.models.Comment") -> bool:
        """Return True if it's a new comment, to be handled"""
        rauthor = self.already_replied(comment)
        if rauthor and rauthor is not True:
            # comment already handled
            if comment.created_utc >= self._latest_letter:
                # it's newer than DELTA_LETTERS
                # so we are going to count it
                self.uletters[rauthor] = 1 + self.uletters[rauthor]
            return False
        if not comment.author:
            # deleted
            return False
        return True

    def _check_answer(self, comment: "praw.reddit.models.Comment") -> bool:
        """Return True if it's a new comment, to be handled"""
        rauthor = self.already_replied(comment)
        if rauthor and rauthor is not True:
            # comment already handled
            if comment.created_utc >= self._latest_answer:
                # it's newer than DELTA_LETTERS
                # so we are going to count it
                self.uanswers[rauthor] = 1 + self.uanswers[rauthor]
            return False
        if not comment.author:
            # deleted
            return False
        return True

    def _handle_answer(self, comment: "praw.reddit.models.Comment") -> bool:
        """Return True if it's a the correct answer"""
        author = comment.author.name
        if self.uanswers[author] >= MAX_ANSWERS:
            self._reply(comment, True, ANSWER_MAX)
            return False
        self.uanswers[author] = 1 + self.uanswers[author]
        body = comment.body.strip().upper()
        if re.sub(r"\W+", "", body) == re.sub(r"\W+", "", self.solution):
            ncurrent = len(set(re.sub(r"\W+", "", self.solution)) - {"- "})
            self._reply(comment, False, ANSWER_OK, ncurrent=ncurrent)
            self._post.mod.sticky(state=False)
            return True
        else:
            self._reply(comment, False, ANSWER_NO)
        return False

    def _handle_letter(
        self, comment: "praw.reddit.models.Comment", to_reveal: set[str], new_missing: set[str]
    ) -> bool:
        # Handle new letter
        author = comment.author.name
        if self.uletters[author] >= MAX_LETTERS:
            self._reply(comment, True, LETTER_MAX)
            return False
        body = comment.body.strip().upper()
        if body not in LETTERS:
            self._reply(comment, True, LETTER_INVALID)
            return False
        self.uletters[author] = 1 + self.uletters[author]
        if body in self.solution:
            self._reply(comment, False, LETTER_OK)
            if body not in self.current and body not in to_reveal:
                to_reveal.add(body)
            return True
        else:
            self._reply(comment, False, LETTER_NO)
            if body not in self.missing:
                new_missing.add(body)
        return False

    def browse_comments(self, parent: "praw.reddit.models.Submission") -> bool:
        new_letters = []
        new_answers = []
        # loop for every child comment
        for comment in parent.comments:
            # skip comments by mods or removed comments
            if comment.stickied or comment.distinguished or comment.removed:
                continue
            if len(comment.body.strip()) > 1:
                # answer
                if self._check_answer(comment):
                    new_answers.append(comment)
            else:
                # letter
                if self._check_letter(comment):
                    new_letters.append(comment)
        new_answers.reverse()  # Older to newer (hopefully)
        LOGGER.debug("Old user letters: %s", self.uletters)
        LOGGER.debug("Old user answers: %s", self.uanswers)
        LOGGER.debug("Letters to be checked: %s", new_letters)
        LOGGER.debug("Anwers to be checked: %s", new_answers)
        # now handle new answers
        for comment in new_answers:
            found = self._handle_answer(comment)
            if found:
                self._reveal_selftext(comment.author.name)
                return True
        # now check new letters
        to_reveal = set()  # type: set[str]
        new_missing = set()  # type: set[str]
        for comment in new_letters:
            self._handle_letter(comment, to_reveal, new_missing)
        self._update_selftext(to_reveal, new_missing)
        return False

    def _update_selftext(self, to_reveal: set[str], new_missing: set[str]) -> bool:
        if not to_reveal and not new_missing:
            return False
        LOGGER.debug("Updating text with: %s and %s", to_reveal, new_missing)
        new_current = "".join(
            [c if c in to_reveal else self.current[i] for i, c in enumerate(self.solution)]
        )
        new_text = self._post.selftext.strip().split("\n")
        new_text[2] = new_current
        self.missing = self.missing.union(new_missing)
        new_text[4] = new_text[4].split(":")[0] + ": " + " ".join(sorted(self.missing))
        self._post.edit(body="\n".join(new_text))
        return True

    def _reveal_selftext(self, username) -> bool:
        LOGGER.debug("Revealing solution with: %s ", username)
        new_text = self._post.selftext.strip().split("\n")
        new_text[2] = "Soluzione: " + self.solution
        new_text[4] = "Ha indovinato la frase: u/" + username
        self._post.edit(body="\n".join(new_text))
        return True


class Ouija:
    """Contain all bot logic."""

    def __init__(self, subreddit: str) -> None:
        """Initialize.

        subreddit = DimmiOuija subreddit
        """
        reddit = praw.Reddit(check_for_updates=False, client_secret=None)
        reddit.validate_on_submit = True
        self._reddit = reddit
        self.me = reddit.user.me()
        self.subreddit = reddit.subreddit(subreddit)
        self.solution = self.subreddit.wiki["rdellaf"].content_md.upper()

    def _title_count(self) -> str:
        return " ".join(
            [
                str(len(s))
                for s in re.split(r"([" + LETTERS + "]+)", self.solution)
                if s and s[0] in LETTERS
            ]
        )

    def open(self) -> None:
        title = "Ruota della fortuna - " + self._title_count()
        text = f"""Indovina la frase:

{re.sub(r"[" + LETTERS + "]", "–", self.solution, flags=re.I)}

Lettere non presenti:

---

Il gioco prevede due azioni:

- Puoi commentare con una lettera, in questo caso se il carattere è presente,
verrà rivelato all'interno della frase.
- Puoi commentre con una frase (cioè con più di un carattere),
se quello che hai scritto corrisponde alla frase da indovinare, avrai vinto il gioco

Ogni giocatore può:

- tentare con UNA lettera ogni ora.
- tentare con DUE frasi ogni DUE ore.

"""
        submission = self.subreddit.submit(title, selftext=text)
        submission.mod.suggested_sort(sort="new")
        submission.mod.flair(**UNANSWERED)
        submission.mod.sticky(bottom=True)
        LOGGER.info("Opened %s", submission)

    def check_submission(self) -> bool:
        """Check the submission for an unanswered post"""
        submissions = self.subreddit.new(limit=100)
        for submission in submissions:
            if not submission.link_flair_text:
                continue
            if submission.link_flair_text == UNANSWERED["text"]:
                post = OuijaPost(submission, self.solution)
                if post.is_unanswered():
                    answer = post.process()
                    if answer:
                        submission.mod.flair(**ANSWERED)
                return True
            if submission.link_flair_text == ANSWERED["text"]:
                try:
                    post = OuijaPost(submission, self.solution)
                    if self.solution in post.current:
                        LOGGER.debug("Found solved %s", post)
                        return True
                except ValueError:
                    continue
        return False

    def work(self):
        wpage = self.subreddit.wiki["rdellaf"]
        now = datetime.now()
        if (now - timedelta(hours=24)).timestamp() > wpage.revision_date:
            LOGGER.debug("Old answer")
            return
        found = self.check_submission()
        if not found:
            self.open()


def main() -> None:
    """Perform a bot action"""

    bot = Ouija("DimmiOuija")
    parser = argparse.ArgumentParser(description="Activate mod bot on /r/DimmiOuija ")
    parser.add_argument(
        "action",
        choices=["check", "open", "work"],
        default="work",
        help="The action to perform (default: %(default)s)",
    )
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        import sys

        LOGGER.addHandler(logging.StreamHandler(sys.stdout))
        LOGGER.setLevel(logging.DEBUG)

    if args.action == "check":
        bot.check_submission()
    elif args.action == "open":
        bot.open()
    elif args.action == "work":
        bot.work()


if __name__ == "__main__":
    main()
