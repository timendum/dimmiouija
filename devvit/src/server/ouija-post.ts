// Port of OuijaPost from bot.py: reads the comment tree of a question,
// removes the comments that break the rules and composes the answer.

import {
  ANSWERED,
  GOODBYE,
  PM_ANSWER_BODY,
  PM_ANSWER_TITLE,
  SCORE_LIMIT,
  UNANSWERED,
} from './config';
import type { CommentNode, Logger, PostInfo, Reddit } from './port';

type Parent = { id: string; authorName: string | undefined };

const segmenter = new Intl.Segmenter('it', { granularity: 'grapheme' });

/** Number of code points, like Python len(). */
export function pyLen(text: string): number {
  return Array.from(text).length;
}

export function graphemeLength(text: string): number {
  let count = 0;
  for (const _ of segmenter.segment(text)) count++;
  return count;
}

/** Python 3 round(): ties go to the even number. */
export function pyRound(value: number): number {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (diff > 0.5) return floor + 1;
  if (diff < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/** Drop the t1_/t3_ prefix. */
function base36(thingId: string): string {
  return thingId.replace(/^t\d_/, '');
}

export function isUnanswered(post: PostInfo): boolean {
  if (!post.flairText) return true;
  return post.flairCssClass === UNANSWERED.cssClass;
}

export class OuijaPost {
  readonly post: PostInfo;
  readonly author: string | undefined;
  readonly flair: string | undefined;
  answerText: string | null = null;
  answerPermalink: string | null = null;
  answerScore = Number.NEGATIVE_INFINITY;

  readonly #reddit: Reddit;
  readonly #log: Logger;

  constructor(reddit: Reddit, post: PostInfo, log: Logger) {
    this.#reddit = reddit;
    this.#log = log;
    this.post = post;
    this.author = post.authorName;
    if (post.flairText && post.flairText !== UNANSWERED.text) {
      this.flair = post.flairText;
    }
  }

  isUnanswered(): boolean {
    return isUnanswered(this.post);
  }

  /** Return a int between 1 and SCORE_LIMIT based on the age of the post. */
  calcScore(now: number): number {
    const age = (now - this.post.createdAt.getTime()) / (1000 * 60 * 60); // in hours
    return pyRound(SCORE_LIMIT + 2 * (1 - age / 8));
  }

  /** Flair the post based on answerText and send a PM */
  async changeFlair(): Promise<void> {
    if (this.answerText === null) {
      if (!this.post.flairText) {
        await this.#reddit.setPostFlair(this.post.id, UNANSWERED);
        this.#log.info(`Flair - UNANSWERED - https://www.reddit.com${this.post.permalink}`);
      }
      return;
    }
    let text = ANSWERED.text + this.answerText;
    if (pyLen(text) > 64) {
      text = Array.from(text).slice(0, 61).join('') + '...';
    }
    if (text === this.flair) return;
    await this.#reddit.setPostFlair(this.post.id, { ...ANSWERED, text });
    if (this.post.authorName) {
      try {
        await this.#reddit.sendModmail(
          this.post.authorName,
          PM_ANSWER_TITLE,
          PM_ANSWER_BODY.replace('{question}', this.post.title)
            .replace('{answer}', this.answerText)
            .replace('{permalink}', this.answerPermalink ?? '')
        );
      } catch (error) {
        this.#log.error(`Error sending PM to ${this.post.authorName}`, error);
      }
    }
    this.#log.info(`Flair - ${text} - https://www.reddit.com${this.post.permalink}`);
  }

  /** Check for answers in the comments and delete wrong comments */
  async process(): Promise<boolean> {
    const comments = await this.#reddit.getCommentTree(this.post.id);
    return this.#browseComments({ id: this.post.id, authorName: this.author }, comments);
  }

  /** Check if the comment contain a better answer. */
  #acceptAnswer(comment: CommentNode): boolean {
    if (comment.score > this.answerScore) {
      this.answerText = ''; // remove previous text
      this.answerScore = comment.score;
      this.answerPermalink = comment.permalink;
      return true;
    }
    return false;
  }

  async #remove(comment: CommentNode): Promise<void> {
    await this.#reddit.remove(comment.id);
    comment.removed = true;
  }

  /** Delete comments and all children */
  async #deleteThread(comment: CommentNode): Promise<void> {
    for (const reply of comment.replies) {
      await this.#deleteThread(reply);
    }
    if (!comment.removed) await this.#remove(comment);
  }

  /** Delete the comment according to rule. Return true if deleted. */
  async #moderation(comment: CommentNode, parent: Parent): Promise<boolean> {
    if (comment.authorName === this.author) {
      this.#log.info(`Deleting - OP = author - ${this.#permalink(parent.id)}`);
      await this.#deleteThread(comment);
      return true;
    }
    if (comment.authorName === parent.authorName) {
      this.#log.info(`Deleting - parent = author - ${this.#permalink(comment.id)}?context=1`);
      await this.#deleteThread(comment);
      return true;
    }
    return false;
  }

  /** Produce a shorter permalink */
  #permalink(thingId: string): string {
    return `https://www.reddit.com/r/${this.#reddit.subredditName}/comments/${base36(this.post.id)}//${base36(thingId)}`;
  }

  /** Given the replies of a parent return true if an answer is found */
  async #browseComments(parent: Parent, comments: CommentNode[]): Promise<boolean> {
    let found = false;
    const existing = new Map<string, CommentNode>();
    for (const comment of comments) {
      // skip comments by mods or removed comments
      if (comment.stickied || comment.distinguished || comment.removed) continue;
      // skip [deleted] comments
      if (!comment.authorName) continue;
      // if moderation is applied (comment removed), skip
      if (await this.#moderation(comment, parent)) continue;
      // check body (remove space and escape chars)
      const body = comment.body.trim().replace(/^\\+/, '');
      if (GOODBYE.test(body)) {
        const previous = existing.get('GOODBYE');
        if (
          previous &&
          (comment.score < previous.score || comment.createdAt.getTime() > previous.createdAt.getTime())
        ) {
          this.#log.info(`Deleting - duplicated goodbye - ${this.#permalink(parent.id)}`);
          await this.#remove(comment);
          continue;
        }
        existing.set('GOODBYE', comment);
        // check if the new answer is an accepted one (and store the results)
        found = found || this.#acceptAnswer(comment);
      } else if (pyLen(body) === 1 || graphemeLength(body) === 1) {
        const previous = existing.get(body);
        if (previous) {
          // the letter is already inserted
          if (
            comment.createdAt.getTime() > previous.createdAt.getTime() &&
            comment.replies.length < 1
          ) {
            // the new comment is newer and does not have replies: delete it
            this.#log.info(`Deleting - duplicated - ${this.#permalink(parent.id)}`);
            await this.#remove(comment);
            continue;
          }
          if (previous.replies.length < 1) {
            // the previous comment has not replies: delete it
            this.#log.info(`Deleting - duplicated - ${this.#permalink(parent.id)}`);
            await this.#remove(previous);
            existing.set(body, comment);
            continue;
          }
        }
        // the letter is not already inserted, save it
        existing.set(body, comment);
        if (await this.#browseComments(comment, comment.replies)) {
          // compose the answer, to uppercase
          this.answerText = (body + (this.answerText ?? '')).toUpperCase();
          found = true;
        }
      } else {
        // comment is by user and longer than 1 char (unicode ok), delete it
        this.#log.info(`Deleting - length <> 1 - ${this.#permalink(comment.id)}`);
        await this.#remove(comment);
      }
    }
    return found;
  }
}
