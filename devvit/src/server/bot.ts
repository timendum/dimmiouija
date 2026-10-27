// Port of PMList and Ouija (check / open / close) from bot.py

import {
  APERTURA_COMMENTO,
  APERTURA_TITOLO,
  AUTOMOD_MARKER,
  MESI,
  MODPOST,
  PROSSIMA_COMMENTO,
  PROSSIMA_TESTO,
  PROSSIMA_TITOLO,
  SCORE_LIMIT,
  TEXT_WIKI_CAFFE,
  TIME_ZONE,
  WAIT_NEXT,
} from './config';
import { OuijaPost, isUnanswered } from './ouija-post';
import type { Logger, PostInfo, Reddit, Store } from './port';

export type Deps = {
  reddit: Reddit;
  store: Store;
  log: Logger;
  /** Usernames whose posts count as posts by the bot (app account, legacy bot) */
  botNames: string[];
  now: () => number;
};

const CURSOR_KEY = 'check:cursor';
const LOCK_KEY = 'check:lock';

/**
 * Run `fn` unless another run holds the lock (scheduler and menu action can overlap).
 * Return false when skipped.
 */
export async function withLock(
  store: Store,
  ttlMs: number,
  fn: () => Promise<void>
): Promise<boolean> {
  const token = `${Date.now()}-${Math.random()}`;
  await store.set(LOCK_KEY, token, { nx: true, expiration: new Date(Date.now() + ttlMs) });
  if ((await store.get(LOCK_KEY)) !== token) return false;
  try {
    await fn();
  } finally {
    await store.del(LOCK_KEY);
  }
  return true;
}

/** Manage a list of user to message */
export class PMList {
  readonly #reddit: Reddit;
  readonly #log: Logger;

  constructor(reddit: Reddit, log: Logger) {
    this.#reddit = reddit;
    this.#log = log;
  }

  /** Prepare for a new start */
  async start(): Promise<void> {
    const main = await this.#reddit.getWikiPage(this.#reddit.subredditName, 'pmlist');
    await this.#reddit.updateWikiPage(this.#reddit.subredditName, 'pmlist_todo', main, 'New opening');
  }

  /** Send a new PM */
  async sendNext(): Promise<void> {
    const todo = await this.#reddit.getWikiPage(this.#reddit.subredditName, 'pmlist_todo');
    const users = todo
      .split('\n')
      .map((user) => user.trim().replaceAll('\\', ''))
      .filter((user) => user);
    const [user, ...rest] = users;
    if (!user) return;
    await this.#reddit.updateWikiPage(
      this.#reddit.subredditName,
      'pmlist_todo',
      rest.join('\n\n'),
      `Done ${user}`
    );
    try {
      await this.#reddit.sendModmail(user, APERTURA_TITOLO, APERTURA_COMMENTO);
    } catch (error) {
      if (String(error).includes('USER_DOESNT_EXIST')) {
        await this.#reddit.notifyMods(user, 'User not found');
      } else {
        this.#log.error(`Error sending PM to ${user}`, error);
      }
    }
  }
}

function isBotPost(post: PostInfo, botNames: string[]): boolean {
  const author = post.authorName?.toLowerCase();
  return author !== undefined && botNames.some((name) => name.toLowerCase() === author);
}

/**
 * Check the submissions for unanswered posts.
 *
 * A Devvit request lasts at most 30 seconds, so posts are processed until
 * `deadline` and the next run resumes after the last processed post.
 */
export async function checkSubmissions(deps: Deps, deadline: number): Promise<void> {
  const { reddit, store, log, botNames, now } = deps;
  const candidates: PostInfo[] = [];
  for (const post of await reddit.getNewPosts(100)) {
    if (post.distinguished || post.stickied) {
      if (!post.flairText) await reddit.setPostFlair(post.id, MODPOST);
      continue;
    }
    if (isBotPost(post, botNames)) continue;
    if (isUnanswered(post)) candidates.push(post);
  }

  const cursor = await store.get(CURSOR_KEY);
  const start = cursor ? candidates.findIndex((post) => post.id === cursor) + 1 : 0;
  let index = start;
  for (; index < candidates.length && now() < deadline; index++) {
    const post = new OuijaPost(reddit, candidates[index]!, log);
    const answer = await post.process();
    if (answer) {
      // check if the answer score is under the limit
      // but not if post is old and the answer score is above lower limit
      if (post.answerScore < SCORE_LIMIT && post.answerScore < post.calcScore(now())) {
        // revert acceptAnswer
        post.answerText = null;
        post.answerScore = Number.NEGATIVE_INFINITY;
        post.answerPermalink = null;
      }
    }
    await post.changeFlair();
  }
  if (index >= candidates.length) {
    await store.del(CURSOR_KEY);
  } else if (index > start) {
    log.info(`Time is up, ${candidates.length - index} posts left for the next run`);
    await store.set(CURSOR_KEY, candidates[index - 1]!.id);
  }

  try {
    await new PMList(reddit, log).sendNext();
  } catch (error) {
    log.error('PM list failed', error);
  }
}

async function toggleAutomoderator(
  reddit: Reddit,
  from: string,
  to: string,
  reason: string,
  errorSubject: string
): Promise<void> {
  const page = 'config/automoderator';
  const lines = (await reddit.getWikiPage(reddit.subredditName, page)).split('\n');
  const index = lines.findIndex((line) => line.includes(AUTOMOD_MARKER));
  if (index < 1) {
    await reddit.notifyMods(errorSubject, 'Automod non gestito');
    return;
  }
  lines[index - 1] = lines[index - 1]!.replaceAll(from, to);
  await reddit.updateWikiPage(reddit.subredditName, page, lines.join('\n'), reason);
}

/** Open the subreddit to new submission */
export async function openSubreddit(deps: Deps, caffeSubreddit: string): Promise<void> {
  const { reddit, log, botNames } = deps;
  await toggleAutomoderator(reddit, '~name:', 'name:', 'Apertura', 'ERRORE Apertura!!!');
  log.info(`Subreddit aperto! https://www.reddit.com/r/${reddit.subredditName}`);

  for (const post of await reddit.getHotPosts(100)) {
    if (!isBotPost(post, botNames) || !post.distinguished) continue;
    // post is the PROSSIMA_TITOLO
    await reddit.unstickyPost(post.id);
    const comments = await reddit.getCommentTree(post.id);
    const announcement = comments.find((comment) => comment.distinguished);
    const toNotify = announcement ? announcement.replies : comments;
    for (const comment of toNotify) {
      try {
        await reddit.reply(comment.id, APERTURA_COMMENTO);
      } catch (error) {
        log.error(`Error replying to ${comment.id}`, error);
      }
    }
    break;
  }

  await new PMList(reddit, log).start();

  // Update ambrogio_caffe
  if (caffeSubreddit) {
    const content = (await reddit.getWikiPage(caffeSubreddit, 'ambrogio_caffe'))
      .replaceAll('\r', '')
      .replaceAll('[](/oggi-start)\n', `[](/oggi-start)\n\n* ${TEXT_WIKI_CAFFE}`);
    await reddit.updateWikiPage(caffeSubreddit, 'ambrogio_caffe', content, 'DimmiOuija apertura');
  }
}

/** Title of the post announcing the next opening, using the Italian calendar */
export function nextOpeningTitle(now: number): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: TIME_ZONE,
    day: 'numeric',
    month: 'numeric',
  }).formatToParts(new Date(now + WAIT_NEXT));
  const day = parts.find((part) => part.type === 'day')!.value;
  const month = Number(parts.find((part) => part.type === 'month')!.value);
  return `${PROSSIMA_TITOLO}${day} ${MESI[month]}`;
}

/** Close the subreddit to new submission */
export async function closeSubreddit(deps: Deps): Promise<void> {
  const { reddit, log, now } = deps;
  log.info('Subreddit chiuso');
  await toggleAutomoderator(reddit, ' name:', ' ~name:', 'Chiusura', 'ERRORE Chiusura!!!');

  // bot.py builds the list of open questions but then posts PROSSIMA_TESTO only:
  // the same text is kept here.
  const postId = await reddit.submitPost(nextOpeningTitle(now()), PROSSIMA_TESTO);
  await reddit.stickyPost(postId);
  await reddit.distinguishPost(postId);
  const commentId = await reddit.reply(postId, PROSSIMA_COMMENTO);
  await reddit.distinguishComment(commentId, true);
}
