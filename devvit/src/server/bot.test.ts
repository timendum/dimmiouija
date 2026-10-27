import { describe, expect, test } from 'vitest';
import {
  APERTURA_COMMENTO,
  APERTURA_TITOLO,
  ANSWERED,
  MODPOST,
  PROSSIMA_COMMENTO,
  PROSSIMA_TESTO,
  TEXT_WIKI_CAFFE,
  UNANSWERED,
} from './config';
import {
  PMList,
  checkSubmissions,
  closeSubreddit,
  nextOpeningTitle,
  openSubreddit,
  withLock,
} from './bot';
import type { Deps } from './bot';
import { DryRunReddit } from './gateway';
import { FakeReddit, MemoryLogger, MemoryStore, NOW, c, chain, post } from './fake.test-utils';

function deps(reddit = new FakeReddit(), store = new MemoryStore()): Deps & {
  reddit: FakeReddit;
  store: MemoryStore;
} {
  reddit.wiki.set('DimmiOuija/pmlist_todo', '');
  return { reddit, store, log: new MemoryLogger(), botNames: ['dimmiouija', 'OldBot'], now: () => NOW };
}

describe('checkSubmissions', () => {
  test('flairs mod posts, skips bot and answered posts, processes unanswered ones', async () => {
    const d = deps();
    const modPost = post({ distinguished: true });
    const sticky = post({ stickied: true, flairText: 'Annuncio' });
    const botPost = post({ authorName: 'OLDBOT' });
    const answered = post({ flairText: 'Ouija dice: SI', flairCssClass: 'answered' });
    const fresh = post();
    const solved = post({ flairText: UNANSWERED.text, flairCssClass: UNANSWERED.cssClass });
    d.reddit.posts.push(modPost, sticky, botPost, answered, fresh, solved);
    d.reddit.trees.set(solved.id, [chain('NO', 3)]);

    await checkSubmissions(d, Number.POSITIVE_INFINITY);

    expect(d.reddit.callsTo('getCommentTree')).toEqual([[fresh.id], [solved.id]]);
    expect(d.reddit.callsTo('setPostFlair')).toEqual([
      [modPost.id, MODPOST],
      [fresh.id, UNANSWERED],
      [solved.id, { ...ANSWERED, text: 'Ouija dice: NO' }],
    ]);
    expect(d.reddit.callsTo('sendModmail')).toHaveLength(1);
  });

  test('a low-score goodbye on a fresh post is not accepted yet', async () => {
    const d = deps();
    const fresh = post({ createdAt: new Date(NOW - 60 * 60 * 1000) });
    d.reddit.posts.push(fresh);
    d.reddit.trees.set(fresh.id, [chain('SI', 2)]);
    await checkSubmissions(d, Number.POSITIVE_INFINITY);
    expect(d.reddit.callsTo('setPostFlair')).toEqual([[fresh.id, UNANSWERED]]);
  });

  test('a low-score goodbye is accepted once the post is old enough', async () => {
    const d = deps();
    const old = post({ createdAt: new Date(NOW - 16 * 60 * 60 * 1000) });
    d.reddit.posts.push(old);
    d.reddit.trees.set(old.id, [chain('SI', 1)]);
    await checkSubmissions(d, Number.POSITIVE_INFINITY);
    expect(d.reddit.callsTo('setPostFlair')).toEqual([[old.id, { ...ANSWERED, text: 'Ouija dice: SI' }]]);
  });

  test('stops at the deadline and resumes from the cursor on the next run', async () => {
    const d = deps();
    const posts = [post(), post(), post()];
    d.reddit.posts.push(...posts);
    let clock = NOW;
    d.now = () => (clock += 10);

    await checkSubmissions(d, NOW + 25); // time for two posts
    expect(d.reddit.callsTo('getCommentTree')).toEqual([[posts[0]!.id], [posts[1]!.id]]);
    expect(d.store.data.get('check:cursor')).toBe(posts[1]!.id);

    d.reddit.calls.length = 0;
    await checkSubmissions(d, Number.POSITIVE_INFINITY);
    expect(d.reddit.callsTo('getCommentTree')).toEqual([[posts[2]!.id]]);
    expect(d.store.data.has('check:cursor')).toBe(false);
  });

  test('sends one PM from the todo list on every run', async () => {
    const d = deps();
    d.reddit.wiki.set('DimmiOuija/pmlist_todo', 'uno\n\nd\\_ue\n');
    await checkSubmissions(d, Number.POSITIVE_INFINITY);
    expect(d.reddit.callsTo('sendModmail')).toEqual([['uno', APERTURA_TITOLO, APERTURA_COMMENTO]]);
    expect(d.reddit.wiki.get('DimmiOuija/pmlist_todo')).toBe('d_ue');
  });
});

test('a missing pmlist_todo page is logged without failing the check', async () => {
  const log = new MemoryLogger();
  const d = { ...deps(), log };
  d.reddit.wiki.delete('DimmiOuija/pmlist_todo');
  const fresh = post();
  d.reddit.posts.push(fresh);
  await expect(checkSubmissions(d, Number.POSITIVE_INFINITY)).resolves.toBeUndefined();
  expect(d.reddit.callsTo('setPostFlair')).toEqual([[fresh.id, UNANSWERED]]);
  expect(log.lines.some((line) => line.includes('ERROR PM list failed'))).toBe(true);
});

describe('PMList', () => {
  test('start copies the main list into the todo list', async () => {
    const d = deps();
    d.reddit.wiki.set('DimmiOuija/pmlist', 'a\n\nb');
    await new PMList(d.reddit, d.log).start();
    expect(d.reddit.callsTo('updateWikiPage')).toEqual([
      ['DimmiOuija', 'pmlist_todo', 'a\n\nb', 'New opening'],
    ]);
  });

  test('an empty list sends nothing', async () => {
    const d = deps();
    d.reddit.wiki.set('DimmiOuija/pmlist_todo', '\n  \n');
    await new PMList(d.reddit, d.log).sendNext();
    expect(d.reddit.calls).toEqual([]);
  });

  test('a missing user is reported to the mods', async () => {
    const d = deps();
    d.reddit.wiki.set('DimmiOuija/pmlist_todo', 'ghost\n\nnext');
    d.reddit.failModmailFor.set('ghost', new Error('USER_DOESNT_EXIST: no such user'));
    await new PMList(d.reddit, d.log).sendNext();
    expect(d.reddit.callsTo('notifyMods')).toEqual([['ghost', 'User not found']]);
    expect(d.reddit.wiki.get('DimmiOuija/pmlist_todo')).toBe('next');
  });
});

const AUTOMOD_CLOSED = [
  '---',
  '    author:',
  '        ~name: [someone]',
  '        # DummyUtente9510',
  'action: remove',
].join('\n');
const AUTOMOD_OPEN = AUTOMOD_CLOSED.replace('~name:', 'name:');

describe('openSubreddit', () => {
  test('opens automod, notifies the replies, resets the PM list and updates the caffè', async () => {
    const d = deps();
    d.reddit.wiki.set('DimmiOuija/config/automoderator', AUTOMOD_CLOSED);
    d.reddit.wiki.set('DimmiOuija/pmlist', 'utente');
    d.reddit.wiki.set('italy/ambrogio_caffe', 'Oggi\r\n[](/oggi-start)\n* altro');
    const announcement = post({ authorName: 'dimmiouija', distinguished: true });
    d.reddit.hot.push(post(), announcement);
    const wantsPing = [c('io', 'x'), c('anche io', 'y')];
    d.reddit.trees.set(announcement.id, [
      c('commento', 'z'),
      c(PROSSIMA_COMMENTO, 'dimmiouija', wantsPing, { distinguished: true }),
    ]);

    await openSubreddit(d, 'italy');

    expect(d.reddit.wiki.get('DimmiOuija/config/automoderator')).toBe(AUTOMOD_OPEN);
    expect(d.reddit.callsTo('unstickyPost')).toEqual([[announcement.id]]);
    expect(d.reddit.callsTo('reply')).toEqual(wantsPing.map((r) => [r.id, APERTURA_COMMENTO]));
    expect(d.reddit.wiki.get('DimmiOuija/pmlist_todo')).toBe('utente');
    expect(d.reddit.wiki.get('italy/ambrogio_caffe')).toBe(
      `Oggi\n[](/oggi-start)\n\n* ${TEXT_WIKI_CAFFE}* altro`
    );
  });

  test('without the announcement comment every top comment is notified', async () => {
    const d = deps();
    d.reddit.wiki.set('DimmiOuija/config/automoderator', AUTOMOD_CLOSED);
    d.reddit.wiki.set('DimmiOuija/pmlist', '');
    const announcement = post({ authorName: 'oldbot', distinguished: true });
    d.reddit.hot.push(announcement);
    const top = [c('ping', 'x'), c('ping', 'y')];
    d.reddit.trees.set(announcement.id, top);
    await openSubreddit(d, '');
    expect(d.reddit.callsTo('reply')).toEqual(top.map((r) => [r.id, APERTURA_COMMENTO]));
    expect(d.reddit.callsTo('updateWikiPage').map(([sub, page]) => `${sub}/${page}`)).toEqual([
      'DimmiOuija/config/automoderator',
      'DimmiOuija/pmlist_todo',
    ]);
  });

  test('warns the mods when the automod rule is missing', async () => {
    const d = deps();
    d.reddit.wiki.set('DimmiOuija/config/automoderator', 'nothing here');
    d.reddit.wiki.set('DimmiOuija/pmlist', '');
    await openSubreddit(d, '');
    expect(d.reddit.callsTo('notifyMods')).toEqual([['ERRORE Apertura!!!', 'Automod non gestito']]);
  });
});

describe('closeSubreddit', () => {
  test('closes automod and posts the sticky announcement', async () => {
    const d = deps();
    d.reddit.wiki.set('DimmiOuija/config/automoderator', AUTOMOD_OPEN);
    await closeSubreddit(d);
    expect(d.reddit.wiki.get('DimmiOuija/config/automoderator')).toBe(AUTOMOD_CLOSED);
    // NOW is 27 October 2026 12:00 UTC, + 13.5 days
    expect(d.reddit.callsTo('submitPost')).toEqual([['Riapriamo il 10 novembre', PROSSIMA_TESTO]]);
    expect(d.reddit.callsTo('stickyPost')).toEqual([['t3_new']]);
    expect(d.reddit.callsTo('distinguishPost')).toEqual([['t3_new']]);
    expect(d.reddit.callsTo('reply')).toEqual([['t3_new', PROSSIMA_COMMENTO]]);
    expect(d.reddit.callsTo('distinguishComment')).toEqual([['t1_reply_t3_new', true]]);
  });

  test('the date of the next opening uses the Italian time zone', () => {
    // + 13.5 days is 9 November 23:00 UTC, already 10 November in Italy
    expect(nextOpeningTitle(Date.UTC(2026, 9, 27, 11, 0))).toBe('Riapriamo il 10 novembre');
  });
});

describe('infrastructure', () => {
  test('withLock skips a concurrent run', async () => {
    const store = new MemoryStore();
    let inner: boolean | undefined;
    const outer = await withLock(store, 1000, async () => {
      inner = await withLock(store, 1000, async () => {});
    });
    expect([outer, inner]).toEqual([true, false]);
    expect(await withLock(store, 1000, async () => {})).toBe(true);
  });

  test('DryRunReddit reads but never writes', async () => {
    const reddit = new FakeReddit();
    const log = new MemoryLogger();
    const d = deps(reddit);
    const fresh = post();
    reddit.posts.push(fresh);
    reddit.trees.set(fresh.id, [c('troppo lungo', 'a')]);
    reddit.wiki.set('DimmiOuija/config/automoderator', AUTOMOD_OPEN);
    const dry = new DryRunReddit(reddit, log);

    await checkSubmissions({ ...d, reddit: dry }, Number.POSITIVE_INFINITY);
    await closeSubreddit({ ...d, reddit: dry });

    expect(reddit.calls.map((call) => call.method)).toEqual(['getCommentTree']);
    expect(log.lines.filter((line) => line.startsWith('[DRY RUN]')).length).toBeGreaterThan(3);
  });
});
