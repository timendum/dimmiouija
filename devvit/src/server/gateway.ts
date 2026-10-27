// Devvit implementation of the Reddit and Store ports.

import { context, reddit, redis } from '@devvit/web/server';
import type { Comment, Post } from '@devvit/web/server';
import type { FlairSpec } from './config';
import type { CommentNode, Logger, PostInfo, Reddit, Store } from './port';

type T1 = `t1_${string}`;
type T3 = `t3_${string}`;
type T5 = `t5_${string}`;

function isT1(id: string): id is T1 {
  return id.startsWith('t1_');
}

function isT3(id: string): id is T3 {
  return id.startsWith('t3_');
}

function isT5(id: string | undefined): id is T5 {
  return id?.startsWith('t5_') ?? false;
}

function asT1(id: string): T1 {
  if (!isT1(id)) throw new Error(`Not a comment id: ${id}`);
  return id;
}

function asT3(id: string): T3 {
  if (!isT3(id)) throw new Error(`Not a post id: ${id}`);
  return id;
}

function asThing(id: string): T1 | T3 {
  return id.startsWith('t1_') ? asT1(id) : asT3(id);
}

function authorOf(name: string): string | undefined {
  return name && name !== '[deleted]' ? name : undefined;
}

function toPostInfo(post: Post): PostInfo {
  return {
    id: post.id,
    title: post.title,
    authorName: authorOf(post.authorName),
    createdAt: post.createdAt,
    permalink: post.permalink,
    flairText: post.flair?.text || undefined,
    flairCssClass: post.flair?.cssClass || undefined,
    distinguished: Boolean(post.distinguishedBy),
    stickied: post.stickied,
  };
}

async function toCommentNode(comment: Comment): Promise<CommentNode> {
  const replies = await comment.replies.all();
  return {
    id: comment.id,
    authorName: authorOf(comment.authorName),
    body: comment.body,
    score: comment.score,
    createdAt: comment.createdAt,
    permalink: comment.permalink,
    removed: comment.removed,
    stickied: comment.stickied,
    distinguished: Boolean(comment.distinguishedBy),
    replies: await Promise.all(replies.map(toCommentNode)),
  };
}

export class RedditGateway implements Reddit {
  readonly subredditName: string;
  readonly #subredditId: T5;
  /** Flair template id to use instead of the one in config.ts, by css class */
  readonly #flairTemplateIds: Record<string, string>;

  constructor(flairTemplateIds: Record<string, string> = {}) {
    this.#flairTemplateIds = flairTemplateIds;
    const { subredditName, subredditId } = context;
    if (!subredditName || !isT5(subredditId)) {
      throw new Error('Subreddit context is required');
    }
    this.subredditName = subredditName;
    this.#subredditId = subredditId;
  }

  async getAppUsername(): Promise<string> {
    const user = await reddit.getAppUser();
    return user?.username ?? context.appName;
  }

  async getNewPosts(limit: number): Promise<PostInfo[]> {
    const posts = await reddit.getNewPosts({ subredditName: this.subredditName, limit }).all();
    return posts.map(toPostInfo);
  }

  async getHotPosts(limit: number): Promise<PostInfo[]> {
    const posts = await reddit.getHotPosts({ subredditName: this.subredditName, limit }).all();
    return posts.map(toPostInfo);
  }

  async getCommentTree(postId: string): Promise<CommentNode[]> {
    const comments = await reddit.getComments({ postId: asT3(postId), sort: 'top' }).all();
    return Promise.all(comments.map(toCommentNode));
  }

  async remove(thingId: string): Promise<void> {
    await reddit.remove(asThing(thingId), false);
  }

  async setPostFlair(postId: string, flair: FlairSpec): Promise<void> {
    await reddit.setPostFlair({
      subredditName: this.subredditName,
      postId: asT3(postId),
      flairTemplateId: this.#flairTemplateIds[flair.cssClass] || flair.flairTemplateId,
      text: flair.text,
      cssClass: flair.cssClass,
    });
  }

  async sendModmail(to: string, subject: string, body: string): Promise<void> {
    const { conversation } = await reddit.modMail.createConversation({
      subredditName: this.subredditName,
      subject,
      body,
      to,
    });
    if (!conversation.isInternal && conversation.id) {
      await reddit.modMail.archiveConversation(conversation.id);
    }
  }

  async notifyMods(subject: string, body: string): Promise<void> {
    await reddit.modMail.createModNotification({
      subject,
      bodyMarkdown: body,
      subredditId: this.#subredditId,
    });
  }

  async getWikiPage(subredditName: string, page: string): Promise<string> {
    try {
      return (await reddit.getWikiPage(subredditName, page)).content;
    } catch (error) {
      throw new Error(`Cannot read wiki page r/${subredditName}/wiki/${page}: ${String(error)}`);
    }
  }

  async updateWikiPage(
    subredditName: string,
    page: string,
    content: string,
    reason: string
  ): Promise<void> {
    await reddit.updateWikiPage({ subredditName, page, content, reason });
  }

  async submitPost(title: string, text: string): Promise<string> {
    const post = await reddit.submitPost({ subredditName: this.subredditName, title, text });
    return post.id;
  }

  async stickyPost(postId: string): Promise<void> {
    await (await reddit.getPostById(asT3(postId))).sticky(1);
  }

  async unstickyPost(postId: string): Promise<void> {
    await (await reddit.getPostById(asT3(postId))).unsticky();
  }

  async distinguishPost(postId: string): Promise<void> {
    await (await reddit.getPostById(asT3(postId))).distinguish();
  }

  async reply(thingId: string, text: string): Promise<string> {
    const comment = await reddit.submitComment({ id: asThing(thingId), text, runAs: 'APP' });
    return comment.id;
  }

  async distinguishComment(commentId: string, sticky: boolean): Promise<void> {
    await (await reddit.getCommentById(asT1(commentId))).distinguish(sticky);
  }
}

/** Wraps a Reddit port: reads go through, writes are only logged. */
export class DryRunReddit implements Reddit {
  readonly subredditName: string;
  readonly #inner: Reddit;
  readonly #log: Logger;
  #fakeIds = 0;

  constructor(inner: Reddit, log: Logger) {
    this.#inner = inner;
    this.#log = log;
    this.subredditName = inner.subredditName;
  }

  #skip(action: string): void {
    this.#log.info(`[DRY RUN] ${action}`);
  }

  getAppUsername = () => this.#inner.getAppUsername();
  getNewPosts = (limit: number) => this.#inner.getNewPosts(limit);
  getHotPosts = (limit: number) => this.#inner.getHotPosts(limit);
  getCommentTree = (postId: string) => this.#inner.getCommentTree(postId);
  getWikiPage = (subredditName: string, page: string) =>
    this.#inner.getWikiPage(subredditName, page);

  async remove(thingId: string): Promise<void> {
    this.#skip(`remove ${thingId}`);
  }
  async setPostFlair(postId: string, flair: FlairSpec): Promise<void> {
    this.#skip(`flair ${postId}: ${flair.text}`);
  }
  async sendModmail(to: string, subject: string, body: string): Promise<void> {
    this.#skip(`modmail to ${to}: ${subject}\n${body}`);
  }
  async notifyMods(subject: string, body: string): Promise<void> {
    this.#skip(`mod notification: ${subject} - ${body}`);
  }
  async updateWikiPage(subredditName: string, page: string, content: string, reason: string) {
    this.#skip(`wiki r/${subredditName}/${page} (${reason}):\n${content}`);
  }
  async submitPost(title: string, text: string): Promise<string> {
    this.#skip(`submit post "${title}":\n${text}`);
    return `t3_dryrun${++this.#fakeIds}`;
  }
  async stickyPost(postId: string): Promise<void> {
    this.#skip(`sticky ${postId}`);
  }
  async unstickyPost(postId: string): Promise<void> {
    this.#skip(`unsticky ${postId}`);
  }
  async distinguishPost(postId: string): Promise<void> {
    this.#skip(`distinguish ${postId}`);
  }
  async reply(thingId: string, text: string): Promise<string> {
    this.#skip(`reply to ${thingId}: ${text}`);
    return `t1_dryrun${++this.#fakeIds}`;
  }
  async distinguishComment(commentId: string, sticky: boolean): Promise<void> {
    this.#skip(`distinguish ${commentId} (sticky: ${sticky})`);
  }
}

export const redisStore: Store = {
  get: (key) => redis.get(key),
  async set(key, value, options) {
    await redis.set(key, value, options);
  },
  async del(key) {
    await redis.del(key);
  },
};
