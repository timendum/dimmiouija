// In-memory Reddit used by the tests: @devvit/test does not mock flair,
// listings, moderation, modmail and wiki yet.

import type { FlairSpec } from './config';
import type { CommentNode, Logger, PostInfo, Reddit, Store } from './port';

export const HOUR = 60 * 60 * 1000;
export const NOW = Date.UTC(2026, 9, 27, 12, 0, 0);

export type Call = { method: string; args: unknown[] };

let ids = 0;

export function post(overrides: Partial<PostInfo> = {}): PostInfo {
  const id = overrides.id ?? `t3_p${++ids}`;
  return {
    id,
    title: 'Chi vincerà?',
    authorName: 'op',
    createdAt: new Date(NOW - HOUR),
    permalink: `/r/DimmiOuija/comments/${id.slice(3)}/q/`,
    flairText: undefined,
    flairCssClass: undefined,
    distinguished: false,
    stickied: false,
    ...overrides,
  };
}

/** A comment; `age` is in minutes before NOW. */
export function c(
  body: string,
  authorName: string | undefined,
  replies: CommentNode[] = [],
  overrides: Partial<CommentNode> & { age?: number } = {}
): CommentNode {
  const id = overrides.id ?? `t1_c${++ids}`;
  const { age = 30, ...rest } = overrides;
  return {
    id,
    authorName,
    body,
    score: 1,
    createdAt: new Date(NOW - age * 60 * 1000),
    permalink: `/r/DimmiOuija/comments/x/q/${id.slice(3)}/`,
    removed: false,
    stickied: false,
    distinguished: false,
    replies,
    ...rest,
  };
}

/** A chain of letters, each reply by an alternating author, ending with a goodbye. */
export function chain(letters: string, goodbyeScore: number, authors = ['a', 'b']): CommentNode {
  let node = c('Addio', authors[letters.length % authors.length], [], { score: goodbyeScore });
  for (let i = letters.length - 1; i >= 0; i--) {
    node = c(letters[i]!, authors[i % authors.length], [node]);
  }
  return node;
}

export class FakeReddit implements Reddit {
  readonly subredditName = 'DimmiOuija';
  readonly calls: Call[] = [];
  readonly posts: PostInfo[] = [];
  readonly hot: PostInfo[] = [];
  readonly trees = new Map<string, CommentNode[]>();
  readonly wiki = new Map<string, string>();
  failModmailFor = new Map<string, Error>();

  #record(method: string, ...args: unknown[]): void {
    this.calls.push({ method, args });
  }

  callsTo(method: string): unknown[][] {
    return this.calls.filter((call) => call.method === method).map((call) => call.args);
  }

  get removed(): string[] {
    return this.callsTo('remove').map(([id]) => String(id));
  }

  async getAppUsername(): Promise<string> {
    return 'dimmiouija';
  }
  async getNewPosts(limit: number): Promise<PostInfo[]> {
    return this.posts.slice(0, limit);
  }
  async getHotPosts(limit: number): Promise<PostInfo[]> {
    return this.hot.slice(0, limit);
  }
  async getCommentTree(postId: string): Promise<CommentNode[]> {
    this.#record('getCommentTree', postId);
    return this.trees.get(postId) ?? [];
  }
  async remove(thingId: string): Promise<void> {
    this.#record('remove', thingId);
  }
  async setPostFlair(postId: string, flair: FlairSpec): Promise<void> {
    this.#record('setPostFlair', postId, flair);
  }
  async sendModmail(to: string, subject: string, body: string): Promise<void> {
    this.#record('sendModmail', to, subject, body);
    const error = this.failModmailFor.get(to);
    if (error) throw error;
  }
  async notifyMods(subject: string, body: string): Promise<void> {
    this.#record('notifyMods', subject, body);
  }
  async getWikiPage(subredditName: string, page: string): Promise<string> {
    const content = this.wiki.get(`${subredditName}/${page}`);
    if (content === undefined) throw new Error(`No wiki page ${subredditName}/${page}`);
    return content;
  }
  async updateWikiPage(subredditName: string, page: string, content: string, reason: string) {
    this.#record('updateWikiPage', subredditName, page, content, reason);
    this.wiki.set(`${subredditName}/${page}`, content);
  }
  async submitPost(title: string, text: string): Promise<string> {
    this.#record('submitPost', title, text);
    return 't3_new';
  }
  async stickyPost(postId: string): Promise<void> {
    this.#record('stickyPost', postId);
  }
  async unstickyPost(postId: string): Promise<void> {
    this.#record('unstickyPost', postId);
  }
  async distinguishPost(postId: string): Promise<void> {
    this.#record('distinguishPost', postId);
  }
  async reply(thingId: string, text: string): Promise<string> {
    this.#record('reply', thingId, text);
    return `t1_reply_${thingId}`;
  }
  async distinguishComment(commentId: string, sticky: boolean): Promise<void> {
    this.#record('distinguishComment', commentId, sticky);
  }
}

export class MemoryStore implements Store {
  readonly data = new Map<string, string>();
  async get(key: string): Promise<string | undefined> {
    return this.data.get(key);
  }
  async set(key: string, value: string, options?: { nx?: boolean }): Promise<void> {
    if (options?.nx && this.data.has(key)) return;
    this.data.set(key, value);
  }
  async del(key: string): Promise<void> {
    this.data.delete(key);
  }
}

export class MemoryLogger implements Logger {
  readonly lines: string[] = [];
  info(message: string): void {
    this.lines.push(message);
  }
  error(message: string, error?: unknown): void {
    this.lines.push(`ERROR ${message} ${String(error)}`);
  }
}
