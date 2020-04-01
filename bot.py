"""Manage a subreddit like AskOuija"""
# pylint: disable=C0103
import argparse
import logging
import re
import time

import grapheme
import praw

AGENT = "python:dimmi-ouja:0.3.2 (by /u/timendum)"

WAIT_NEXT = 60 * 60 * 24 * 14  # 14 days
SCORE_LIMIT = 0
GOODBYE = re.compile(r"^(?:Goodbye|Arrivederci|Addio)", re.IGNORECASE)
UNANSWERED = {"text": "Senza risposta", "class": "unanswered"}
ANSWERED = {"text": "Ouija dice: ", "class": "answered"}
MODPOST = {"text": "DimmiOuija", "class": "DimmiOuija"}
MESI = [
    None,
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
PROSSIMA_COMMENTO = """**Novità**  
Vuoi essere contattato ad OGNI apertura?  
[Scrivici in modmail](https://www.reddit.com/message/compose?to=%2Fr%2FDimmiOuija&subject=Aggiungimi) 
e sarai aggiunto alla lista.

Vuoi essere avvertito solo della prossima apertura?
Rispondi a QUESTO commento."""
APERTURA_COMMENTO = "Ciao,  \ngli spiriti sono arrivati r/DimmiOuija.\n\nUn saluto."
PM_ANSWER_TITLE = "GLI SPIRITI HANNO PARLATO"
PM_ANSWER_BODY = """Hai chiesto:  
> {question}

Gli spiriti dicono:  
> {answer}

[Commenta qui]({permalink}?context=10000)"""
TEXT_WIKI_CAFFE = "Oggi è aperto /r/DimmiOuija, dove si possono fare domande e ricevere risposte, una lettera alla volta. Partecipazione aperta a tutti."
TIME_LIMIT = 24 * 60 * 60 * 1000
YESTERDAY = time.time() - TIME_LIMIT

LOGGER = logging.getLogger(__file__)
LOGGER.addHandler(logging.NullHandler())
LOGGER.setLevel(logging.INFO)


class OuijaPost(object):
    """A post in ouija"""

    def __init__(self, post) -> None:
        """Initialize."""
        self._post = post
        if post.author:
            self.author = post.author.name
        else:
            self.author = None
        self.question = post.title
        self.answer_text = None  # type: str
        self.answer_permalink = None  # type: str
        self.answer_score = float("-inf")
        self.flair = None  # type: str
        if post.link_flair_text and post.link_flair_text != UNANSWERED["text"]:
            self.flair = post.link_flair_text

    def is_unanswered(self) -> bool:
        """Check if the submission is Unanswered"""
        if not self._post.link_flair_text:
            return True
        return self._post.link_flair_css_class == UNANSWERED["class"]

    def is_fresh(self) -> bool:
        """Check if the submission is younger then YESTERDAY"""
        return self._post.created_utc > YESTERDAY

    def change_flair(self):
        """Flair the post based on answer_text and send a PM"""
        if self.answer_text is None:
            if not self._post.link_flair_text:
                self._post.mod.flair(UNANSWERED["text"], UNANSWERED["class"])
                LOGGER.debug(
                    "Flair - UNANSWERED - https://www.reddit.com%s",
                    self._post.permalink,
                )
        else:
            text = ANSWERED["text"] + self.answer_text
            if len(text) > 64:
                text = text[0:61] + "..."
            if text != self.flair:
                self._post.mod.flair(text, ANSWERED["class"])
                if self._post.author:
                    self._post.author.message(
                        PM_ANSWER_TITLE,
                        PM_ANSWER_BODY.format(
                            question=self._post.title,
                            answer=self.answer_text,
                            permalink=self.answer_permalink,
                        ),
                    )
                LOGGER.debug(
                    "Flair - %s - https://www.reddit.com%s", text, self._post.permalink
                )

    def process(self) -> bool:
        """Check for answers in the comments and delete wrong comments"""
        self._post.comment_sort = "top"
        self._post.comments.replace_more(limit=None)
        return self.browse_comments(self._post, [self._post])

    def accept_answer(self, comment) -> bool:
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

    def moderation(self, comment, parent) -> bool:
        """
        Delete the comment according to rule.

        Return True if deleted, False otherwise.
        """

        def delete_thread(comment):
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
            LOGGER.info(
                "Deleting - parent = author - %s?context=1", self.permalink(comment)
            )
            delete_thread(comment)
            return True
        return False

    def permalink(self, comment: praw.models.reddit.comment) -> str:
        """Produce a shorter permalink"""
        return "https://www.reddit.com/r/{}/comments/{}//{}".format(
            self._post.subreddit.display_name, self._post.id, comment.id
        )

    def browse_comments(self, parent, superparents):
        """Given a comment return True if an answer is found"""
        found = False
        existing = {}
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
            body = comment.body.strip().lstrip("\\")
            if GOODBYE.match(body):
                if existing.get("GOODBYE"):
                    if (
                        comment.score < existing["GOODBYE"].score
                        or comment.created > existing["GOODBYE"].created
                    ):
                        LOGGER.info(
                            "Deleting - duplicated goodbye - %s", self.permalink(parent)
                        )
                        comment.mod.remove()
                        continue
                existing["GOODBYE"] = comment
                # check if the new answer is an accepted one (and store the results)
                found = found or self.accept_answer(comment)
            elif len(body) == 1 or grapheme.length(body) == 1:
                if existing.get(body):
                    # the letter is already insered
                    if (
                        comment.created > existing[body].created
                        and len(comment.replies) < 1
                    ):
                        # the new comment is newer and does not have replies: delete it
                        LOGGER.info(
                            "Deleting - duplicated - %s", self.permalink(parent)
                        )
                        comment.mod.remove()
                        continue
                    if len(existing[body].replies) < 1:
                        # the previous comment has not replies: delete it
                        LOGGER.info(
                            "Deleting - duplicated - %s", self.permalink(parent)
                        )
                        existing[body].mod.remove()
                        existing[body] = comment
                        continue
                # the letter is not already insered, save it
                existing[body] = comment
                if self.browse_comments(comment, superparents + [parent]):
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

    def __init__(self, reddit, subreddit) -> None:
        self.reddit = reddit
        self.wiki_main = subreddit.wiki["pmlist"]
        self.wiki_todo = subreddit.wiki["pmlist_todo"]

    def start(self):
        """Prepare for a new start"""
        self.wiki_todo.edit(self.wiki_main.content_md, reason="New opening")

    def send_next(self):
        """Send a new PM"""
        users = self.wiki_todo.content_md.split("\n")
        users = [user.strip() for user in users]
        users = [user for user in users if user]
        if not users:
            return
        user, users = users[0], users[1:]
        self.wiki_todo.edit("\n\n".join(users), reason="Done " + user)
        try:
            self.reddit.redditor(user).message(APERTURA_TITOLO, APERTURA_COMMENTO)
        except praw.exceptions.APIException as e:
            if e.error_type == "USER_DOESNT_EXIST":
                self.wiki_main.subreddit.message(user, "User not found")
            else:
                print(user, e)


class Ouija(object):
    """Contain all bot logic."""

    def __init__(self, subreddit: str) -> None:
        """Initialize.
        
        subreddit = DimmiOuija subreddit
        """
        reddit = praw.Reddit(check_for_updates=False)
        self._reddit = reddit
        self.me = reddit.user.me()
        self.subreddit = reddit.subreddit(subreddit)
        self.pmlist = PMList(reddit, self.subreddit)

    def check_submission(self):
        """Check the submission for unanswered post"""
        submissions = self.subreddit.new(limit=100)
        for submission in submissions:
            if submission.distinguished:
                if not submission.link_flair_text:
                    submission.mod.flair(MODPOST["text"], MODPOST["class"])
                continue
            if submission.stickied:
                if not submission.link_flair_text:
                    submission.mod.flair(MODPOST["text"], MODPOST["class"])
                continue
            post = OuijaPost(submission)
            if post.is_unanswered():
                answer = post.process()
                if answer:
                    if post.answer_score <= SCORE_LIMIT:
                        post.answer_text = None
                post.change_flair()
        self.pmlist.send_next()

    def open(self, swcaffe: str = None):
        """Open the subreddit to new submission"""
        self.subreddit.mod.update(subreddit_type="public")
        LOGGER.info(
            "Subreddit aperto! https://www.reddit.com/r/%s", self.subreddit.display_name
        )
        for submission in self.subreddit.hot():
            if submission.author == self.me and submission.distinguished:
                # submission is the PROSSIMA_TITOLO
                submission.mod.sticky(state=False)
                submission.replace_more(limit=None)
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
                "[](/oggi-start)\n", "[](/oggi-start)\n\n* {}".format(TEXT_WIKI_CAFFE)
            )
            wiki_caffe.edit(content_md, "DimmiOuija apertura")

    def close(self):
        """Close the subreddit to new submission"""
        self.subreddit.mod.update(subreddit_type="restricted")
        LOGGER.info("Subreddit chiuso")
        next_day = time.localtime(time.time() + WAIT_NEXT)
        title = PROSSIMA_TITOLO + str(next_day.tm_mday) + " "
        title = title + MESI[next_day.tm_mon]
        body = PROSSIMA_TESTO
        unanswered = []  # type: list[praw.models.reddit.Submission]
        for submission in self.subreddit.new(limit=100):
            if OuijaPost(submission).is_unanswered():
                unanswered.append(submission)
        if unanswered:
            body += PROSSIMA_APERTE
            body += "\n".join(
                ["* [{}]({})".format(sub.title, sub.permalink) for sub in unanswered]
            )
        submission = self.subreddit.submit(title, selftext=PROSSIMA_TESTO)
        submission.mod.sticky()
        submission.mod.distinguish()
        comment = submission.reply(PROSSIMA_COMMENTO)
        comment.mod.distinguish()


def main():
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
