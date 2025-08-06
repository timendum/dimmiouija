"""Manage a subreddit like AskOuija"""

# pylint: disable=C0103
import argparse
import logging
import re
import time

import grapheme
import praw

AGENT = "python:dimmi-ouja:0.3.2 (by /u/timendum)"

WAIT_NEXT = 60 * 60 * (24 * 13 + 12)  # 13 days + 12 hours, for daylight saving
SCORE_LIMIT = 3  # comment score must be >=
GOODBYE = re.compile(r"^(?:Goodbye|Arrivederci|Addio)", re.IGNORECASE)
UNANSWERED = {
    "text": "Senza risposta",
    "css_class": "unanswered",
    "flair_template_id": "c08164be-2cf7-11e8-82fd-0e9dcb216a98",
}
ANSWERED = {
    "text": "Ouija dice: ",
    "css_class": "answered",
    "flair_template_id": "456a526e-8c01-11e7-bb65-0ed09cec4484",
}
MODPOST = {
    "text": "DimmiOuija",
    "css_class": "DimmiOuija",
    "flair_template_id": "4341ba2c-8c01-11e7-93f7-0e091235c204",
}
MESI = [
    "None",
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
]
PROSSIMA_TITOLO = "Riapriamo il "
PROSSIMA_TESTO = """Qui potete commentare i risultati di questo giro.

Nel frattempo non sarà possibile porre nuove domande, solo concludere quelle già aperte."""
PROSSIMA_APERTE = "\n\nLe domande aperte ad ora sono:\n\n"
APERTURA_TITOLO = "Sei stato convocato su DimmiOuija"
PROSSIMA_COMMENTO = """Vuoi essere contattato ad OGNI apertura?  
[Scrivici in modmail](https://www.reddit.com/message/compose?to=%2Fr%2FDimmiOuija&subject=Aggiungimi) 
e sarai aggiunto alla lista.

Vuoi essere avvertito solo della prossima apertura?
Rispondi a QUESTO commento."""  # noqa
APERTURA_COMMENTO = "Ciao,  \ngli spiriti sono arrivati r/DimmiOuija.\n\nUn saluto."
PM_ANSWER_TITLE = "GLI SPIRITI HANNO PARLATO"
PM_ANSWER_BODY = """Hai chiesto:  
> {question}

Gli spiriti dicono:  
> {answer}

[Commenta qui]({permalink}?context=100)"""  # noqa
TEXT_WIKI_CAFFE = (
    "Oggi è aperto /r/DimmiOuija, dove si possono fare domande "
    "e ricevere risposte, una lettera alla volta. Partecipazione aperta a tutti."
)
TIME_LIMIT = 14 * 24 * 60 * 60
PREVIOUS = time.time() - TIME_LIMIT
NOW = time.time()

LOGGER = logging.getLogger(__file__)
LOGGER.addHandler(logging.NullHandler())
LOGGER.setLevel(logging.INFO)


class OuijaPost:
    """A post in ouija"""

    def __init__(self, post: "praw.reddit.models.Submission") -> None:
        """Initialize."""
        self._post = post
        self.author: praw.reddit.models.Redditor | None = None
        if post.author:
            self.author = post.author.name
        self.question = post.title
        self.answer_text: str | None = None
        self.answer_permalink: str | None = None
        self.answer_score = float("-inf")
        self.flair: str | None = None
        if post.link_flair_text and post.link_flair_text != UNANSWERED["text"]:
            self.flair = post.link_flair_text

    def is_unanswered(self) -> bool:
        """Check if the submission is Unanswered"""
        if not self._post.link_flair_text:
            return True
        return self._post.link_flair_css_class == UNANSWERED["css_class"]

    def is_fresh(self) -> bool:
        """Check if the submission is younger then PREVIOUS"""
        return self._post.created_utc > PREVIOUS

    def calc_score(self) -> int:
        """Return a int between 1 and SCORE_LIMIT based on the age of the post."""
        age = (NOW - self._post.created_utc) / (60 * 60)  # in hours
        return round(SCORE_LIMIT + 2 * (1 - age / 8))

    def change_flair(self) -> None:
        """Flair the post based on answer_text and send a PM"""
        if self.answer_text is None:
            if not self._post.link_flair_text:
                self._post.mod.flair(**UNANSWERED)
                LOGGER.debug(
                    "Flair - UNANSWERED - https://www.reddit.com%s",
                    self._post.permalink,
                )
        else:
            text = ANSWERED["text"] + self.answer_text
            if len(text) > 64:
                text = text[0:61] + "..."
            if text != self.flair:
                self._post.mod.flair(
                    text=text,
                    css_class=ANSWERED["css_class"],
                    flair_template_id=ANSWERED["flair_template_id"],
                )
                if self._post.author:
                    try:
                        self._post.author.message(
                            subject=PM_ANSWER_TITLE,
                            message=PM_ANSWER_BODY.format(
                                question=self._post.title,
                                answer=self.answer_text,
                                permalink=self.answer_permalink,
                            ),
                        )
                    except praw.exceptions.RedditAPIException:
                        LOGGER.exception("Error sending PM to %s", self._post.author.name)
                LOGGER.debug("Flair - %s - https://www.reddit.com%s", text, self._post.permalink)

    def process(self) -> bool:
        """Check for answers in the comments and delete wrong comments"""
        self._post.comment_sort = "top"
        self._post.comments.replace_more(limit=None)
        return self.browse_comments(self._post)

    def accept_answer(self, comment: "praw.reddit.models.Comment") -> bool:
        """
        Check if the comment contain a better answer.

        Return True if accepted, False otherwise.
        """
        if comment.score > self.answer_score:
            self.answer_text = ""  # remove previous text
            self.answer_score = comment.score
            self.answer_permalink = comment.permalink
            return True
        return False

    def moderation(self, comment: "praw.reddit.models.Comment", parent) -> bool:
        """
        Delete the comment according to rule.

        Return True if deleted, False otherwise.
        """

        def delete_thread(comment) -> None:
            """Delete comments and all children"""
            replies = comment.replies
            replies.replace_more(limit=None)
            for reply in replies.list():
                reply.mod.remove()
            comment.mod.remove()

        if comment.author and comment.author.name == self.author:
            LOGGER.info("Deleting - OP = author - %s", self.permalink(parent))
            delete_thread(comment)
            return True
        if comment.author and comment.author.name == parent.author.name:
            LOGGER.info("Deleting - parent = author - %s?context=1", self.permalink(comment))
            delete_thread(comment)
            return True
        return False

    def permalink(
        self, comment: "praw.reddit.models.Comment | praw.reddit.models.Submission"
    ) -> str:
        """Produce a shorter permalink"""
        return f"https://www.reddit.com/r/{self._post.subreddit.display_name}/comments/{self._post.id}//{comment.id}"

    def browse_comments(
        self, parent: "praw.reddit.models.Comment | praw.reddit.models.Submission"
    ) -> bool:  # noqa: C901
        """Given a comment return True if an answer is found"""
        found = False
        existing = {}  # type: dict[str, praw.reddit.models.Comment]
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
            # skip [deleted] comments
            if not comment.author:
                continue
            # if modeation is applied (comment removed), skip
            if self.moderation(comment, parent):
                continue
            # check body (remove space and escape chars)
            body: str = comment.body.strip().lstrip("\\")
            if GOODBYE.match(body):
                if existing.get("GOODBYE"):
                    if (
                        comment.score < existing["GOODBYE"].score
                        or comment.created > existing["GOODBYE"].created
                    ):
                        LOGGER.info("Deleting - duplicated goodbye - %s", self.permalink(parent))
                        comment.mod.remove()
                        continue
                existing["GOODBYE"] = comment
                # check if the new answer is an accepted one (and store the results)
                found = found or self.accept_answer(comment)
            elif len(body) == 1 or grapheme.length(body) == 1:
                if existing.get(body):
                    # the letter is already insered
                    if comment.created > existing[body].created and len(comment.replies) < 1:
                        # the new comment is newer and does not have replies: delete it
                        LOGGER.info("Deleting - duplicated - %s", self.permalink(parent))
                        comment.mod.remove()
                        continue
                    if len(existing[body].replies) < 1:
                        # the previous comment has not replies: delete it
                        LOGGER.info("Deleting - duplicated - %s", self.permalink(parent))
                        existing[body].mod.remove()
                        existing[body] = comment
                        continue
                # the letter is not already insered, save it
                existing[body] = comment
                if self.browse_comments(comment):
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


class PMList:
    """Manage a list of user to message"""

    def __init__(self, reddit: "praw.Reddit", subreddit: "praw.reddit.models.Subreddit") -> None:
        self.reddit = reddit
        self.wiki_main = subreddit.wiki["pmlist"]
        self.wiki_todo = subreddit.wiki["pmlist_todo"]
        self.subreddit = subreddit

    def start(self):
        """Prepare for a new start"""
        self.wiki_todo.edit(content=self.wiki_main.content_md, reason="New opening")

    def send_next(self):
        """Send a new PM"""
        users = self.wiki_todo.content_md.split("\n")
        users = [user.strip() for user in users]
        users = [user for user in users if user]
        if not users:
            return
        user, users = users[0], users[1:]
        self.wiki_todo.edit(content="\n\n".join(users), reason="Done " + user)
        try:
            modconv = self.subreddit.modmail.create(
                recipient=user, subject=APERTURA_TITOLO, body=APERTURA_COMMENTO
            )
            modconv.archive()
        except praw.exceptions.RedditAPIException as e:
            for subexception in e.items:
                if subexception.error_type == "USER_DOESNT_EXIST":
                    self.subreddit.message(user, "User not found")
                    break
            else:
                print(user, e)


class Ouija:
    """Contain all bot logic."""

    def __init__(self, subreddit: str) -> None:
        """Initialize.

        subreddit = DimmiOuija subreddit
        """
        reddit = praw.Reddit(check_for_updates=False, client_secret=None)
        self._reddit = reddit
        self.me = reddit.user.me()
        self.subreddit = reddit.subreddit(subreddit)
        self.pmlist = PMList(reddit, self.subreddit)

    def check_submission(self) -> None:
        """Check the submission for unanswered post"""
        submissions = self.subreddit.new(limit=100)
        for submission in submissions:
            if submission.distinguished:
                if not submission.link_flair_text:
                    submission.mod.flair(**MODPOST)
                continue
            if submission.stickied:
                if not submission.link_flair_text:
                    submission.mod.flair(**MODPOST)
                continue
            if submission.author == self.me:
                continue
            post = OuijaPost(submission)
            if post.is_unanswered():
                answer = post.process()
                if answer:
                    # check if the answer score is under the limit
                    # but not if post is old and the answer score is above lower limit
                    if post.answer_score < SCORE_LIMIT and post.answer_score < post.calc_score():
                        # revert accept_answer
                        post.answer_text = None
                        post.answer_score = float("-inf")
                        post.answer_permalink = None
                post.change_flair()
        self.pmlist.send_next()

    def open(self, swcaffe: str | None = None) -> None:
        """Open the subreddit to new submission"""

        def open_automoderator():
            automoderator = self.subreddit.wiki["config/automoderator"]
            wiki_md = automoderator.content_md.split("\n")
            linen = [i for i, line in enumerate(wiki_md) if "DummyUtente9510" in line]
            if linen:
                line_n = linen[0] - 1
                wiki_md[line_n] = wiki_md[line_n].replace("~name:", "name:")
                automoderator.edit(content="\n".join(wiki_md), reason="Apertura")
            else:
                self.subreddit.message("ERRORE Apertura!!!", "Automod non gestito")

        open_automoderator()
        LOGGER.info("Subreddit aperto! https://www.reddit.com/r/%s", self.subreddit.display_name)
        for submission in self.subreddit.hot():
            if submission.author == self.me and submission.distinguished:
                # submission is the PROSSIMA_TITOLO
                submission.mod.sticky(state=False)
                submission.comments.replace_more(limit=None)
                for comment in submission.comments:
                    if comment.distinguished:
                        for to_notify in comment.replies:
                            to_notify.reply(APERTURA_COMMENTO)
                        break
                else:
                    for comment in submission.comments:
                        comment.reply(APERTURA_COMMENTO)
                break
        self.pmlist.start()
        # Update ambrogio_caffe
        if swcaffe:
            wiki_caffe = self._reddit.subreddit(swcaffe).wiki["ambrogio_caffe"]
            content_md = wiki_caffe.content_md.replace("\r", "").replace(
                "[](/oggi-start)\n", f"[](/oggi-start)\n\n* {TEXT_WIKI_CAFFE}"
            )
            wiki_caffe.edit(content=content_md, reason="DimmiOuija apertura")

    def close(self) -> None:
        """Close the subreddit to new submission"""
        LOGGER.info("Subreddit chiuso")

        def close_automoderator():
            automoderator = self.subreddit.wiki["config/automoderator"]
            wiki_md = automoderator.content_md.split("\n")
            linen = [i for i, line in enumerate(wiki_md) if "DummyUtente9510" in line]
            if linen:
                line_n = linen[0] - 1
                wiki_md[line_n] = wiki_md[line_n].replace(" name:", " ~name:")
                automoderator.edit(content="\n".join(wiki_md), reason="Chiusura")
            else:
                self.subreddit.message("ERRORE Chiusura!!!", "Automod non gestito")

        close_automoderator()
        next_day = time.localtime(time.time() + WAIT_NEXT)
        title = PROSSIMA_TITOLO + str(next_day.tm_mday) + " "
        title = title + MESI[next_day.tm_mon]
        body = PROSSIMA_TESTO
        unanswered = []  # type: list[praw.reddit.models.Submission]
        for submission in self.subreddit.new(limit=100):
            if OuijaPost(submission).is_unanswered():
                unanswered.append(submission)
        if unanswered:
            body += PROSSIMA_APERTE
            body += "\n".join([f"* [{sub.title}]({sub.permalink})" for sub in unanswered])
        submission = self.subreddit.submit(title, selftext=PROSSIMA_TESTO)
        submission.mod.sticky(bottom=False)
        submission.mod.distinguish()
        comment = submission.reply(PROSSIMA_COMMENTO)
        comment.mod.distinguish(sticky=True)


def main() -> None:
    """Perform a bot action"""
    parser = argparse.ArgumentParser(description="Activate mod bot on /r/DimmiOuija ")
    parser.add_argument(
        "action",
        choices=["check", "open", "close"],
        default="check",
        help="The action to perform (default: %(default)s)",
    )
    args = parser.parse_args()

    bot = Ouija("DimmiOuija")
    if args.action == "check":
        bot.check_submission()
    elif args.action == "open":
        bot.open("italy")
    elif args.action == "close":
        bot.close()


if __name__ == "__main__":
    main()


def auth() -> None:
    reddit = praw.Reddit(check_for_updates=False, client_secret=None)
    print(
        reddit.auth.url(
            scopes=[
                "modmail",
                "modconfig",
                "wikiedit",
                "submit",
                "modposts",
                "modflair",
                "read",
                "privatemessages",
                "identity",
                "wikiread",
                "edit",
                "modwiki",
                "flair",
            ],
            state="do",
        )
    )
    code = input("Code: ")
    reddit.auth.authorize(code=code)
