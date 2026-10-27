// The subset of Reddit operations used by the bot.
// Production: RedditGateway (gateway.ts). Tests: FakeReddit (fake.test-utils.ts).

import type { FlairSpec } from './config';

export type PostInfo = {
  id: string; // t3_...
  title: string;
  authorName: string | undefined; // undefined when the author is [deleted]
  createdAt: Date;
  permalink: string; // /r/.../comments/...
  flairText: string | undefined;
  flairCssClass: string | undefined;
  distinguished: boolean;
  stickied: boolean;
};

export type CommentNode = {
  id: string; // t1_...
  authorName: string | undefined; // undefined when the author is [deleted]
  body: string;
  score: number;
  createdAt: Date;
  permalink: string;
  removed: boolean;
  stickied: boolean;
  distinguished: boolean;
  replies: CommentNode[];
};

export type Reddit = {
  subredditName: string;
  getAppUsername(): Promise<string>;
  getNewPosts(limit: number): Promise<PostInfo[]>;
  getHotPosts(limit: number): Promise<PostInfo[]>;
  /** The full comment tree of a post, sorted by top, with every "load more" expanded. */
  getCommentTree(postId: string): Promise<CommentNode[]>;
  remove(thingId: string): Promise<void>;
  setPostFlair(postId: string, flair: FlairSpec): Promise<void>;
  /** Send a modmail from the subreddit to a user, archiving it when it is not internal. */
  sendModmail(to: string, subject: string, body: string): Promise<void>;
  /** Send a message to the subreddit moderators. */
  notifyMods(subject: string, body: string): Promise<void>;
  getWikiPage(subredditName: string, page: string): Promise<string>;
  updateWikiPage(subredditName: string, page: string, content: string, reason: string): Promise<void>;
  submitPost(title: string, text: string): Promise<string>;
  stickyPost(postId: string): Promise<void>;
  unstickyPost(postId: string): Promise<void>;
  distinguishPost(postId: string): Promise<void>;
  reply(thingId: string, text: string): Promise<string>;
  distinguishComment(commentId: string, sticky: boolean): Promise<void>;
};

/** Small key-value store, backed by Redis in production. */
export type Store = {
  get(key: string): Promise<string | undefined>;
  set(key: string, value: string, options?: { nx?: boolean; expiration?: Date }): Promise<void>;
  del(key: string): Promise<void>;
};

export type Logger = {
  info(message: string): void;
  error(message: string, error?: unknown): void;
};

export const consoleLogger: Logger = {
  info: (message) => console.info(message),
  error: (message, error) => console.error(message, error),
};
