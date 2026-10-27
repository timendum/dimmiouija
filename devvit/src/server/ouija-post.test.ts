import { describe, expect, test } from 'vitest';
import { ANSWERED, UNANSWERED } from './config';
import { FakeReddit, HOUR, MemoryLogger, NOW, c, chain, post } from './fake.test-utils';
import { OuijaPost, graphemeLength, pyRound } from './ouija-post';
import type { CommentNode, PostInfo } from './port';

async function run(tree: CommentNode[], info: PostInfo = post()) {
  const reddit = new FakeReddit();
  reddit.trees.set(info.id, tree);
  const ouija = new OuijaPost(reddit, info, new MemoryLogger());
  const found = await ouija.process();
  return { reddit, ouija, found };
}

describe('helpers', () => {
  test('pyRound rounds half to even like Python', () => {
    expect([0.5, 1.5, 2.5, -0.5, 2.4, 2.6].map(pyRound)).toEqual([0, 2, 2, 0, 2, 3]);
  });

  test('graphemeLength counts user-perceived characters', () => {
    expect(graphemeLength('👍🏽')).toBe(1);
    expect(graphemeLength('è')).toBe(1);
    expect(graphemeLength('ab')).toBe(2);
  });
});

describe('answers', () => {
  test('a complete chain composes the answer in uppercase', async () => {
    const goodbye = c('Arrivederci', 'b', [], { score: 5 });
    const tree = [c('c', 'a', [c('i', 'b', [c('a', 'a', [c('o', 'c', [goodbye])])])])];
    const { found, ouija, reddit } = await run(tree);
    expect(found).toBe(true);
    expect(ouija.answerText).toBe('CIAO');
    expect(ouija.answerScore).toBe(5);
    expect(ouija.answerPermalink).toBe(goodbye.permalink);
    expect(reddit.removed).toEqual([]);
  });

  test('the best goodbye wins between two branches', async () => {
    const tree = [chain('NO', 4), chain('SI', 10)];
    const { ouija } = await run(tree);
    expect(ouija.answerText).toBe('SI');
    expect(ouija.answerScore).toBe(10);
  });

  test('a chain without goodbye is not an answer', async () => {
    const { found, ouija } = await run([c('s', 'a', [c('i', 'b')])]);
    expect(found).toBe(false);
    expect(ouija.answerText).toBeNull();
  });

  test('escaped and padded letters are accepted', async () => {
    const { ouija, reddit } = await run([c(' \\* ', 'a', [c('Addio', 'b', [], { score: 3 })])]);
    expect(ouija.answerText).toBe('*');
    expect(reddit.removed).toEqual([]);
  });

  test('emoji with modifiers count as one letter', async () => {
    const { ouija } = await run([c('👍🏽', 'a', [c('Goodbye', 'b', [], { score: 3 })])]);
    expect(ouija.answerText).toBe('👍🏽');
  });
});

describe('moderation', () => {
  test('comments longer than one character are removed', async () => {
    const long = c('ciao', 'a');
    const { reddit } = await run([long, c('x', 'b')]);
    expect(reddit.removed).toEqual([long.id]);
  });

  test('empty comments are removed', async () => {
    const empty = c('   ', 'a');
    const { reddit } = await run([empty]);
    expect(reddit.removed).toEqual([empty.id]);
  });

  test('comments by OP are removed with all their replies', async () => {
    const grandchild = c('z', 'b');
    const child = c('y', 'a', [grandchild]);
    const byOp = c('x', 'op', [child]);
    const { reddit } = await run([byOp]);
    expect(reddit.removed).toEqual([grandchild.id, child.id, byOp.id]);
  });

  test('a reply by the author of the parent is removed with its thread', async () => {
    const child = c('c', 'b');
    const selfReply = c('b', 'a', [child]);
    const parent = c('a', 'a', [selfReply]);
    const { reddit } = await run([parent]);
    expect(reddit.removed).toEqual([child.id, selfReply.id]);
  });

  test('a newer duplicate letter without replies is removed', async () => {
    const older = c('a', 'x', [], { age: 60 });
    const newer = c('a', 'y', [], { age: 10 });
    const { reddit } = await run([older, newer]);
    expect(reddit.removed).toEqual([newer.id]);
  });

  test('an older duplicate without replies is removed when the newer one has replies', async () => {
    const older = c('a', 'x', [], { age: 60 });
    const newerReply = c('long reply', 'z');
    const newer = c('a', 'y', [newerReply], { age: 10 });
    const { reddit } = await run([older, newer]);
    // as in bot.py the replacing comment is not browsed in this run
    expect(reddit.removed).toEqual([older.id]);
  });

  test('duplicates with replies on both sides are kept', async () => {
    const first = c('a', 'x', [c('b', 'y')], { age: 60 });
    const second = c('a', 'y', [c('c', 'x')], { age: 10 });
    const { reddit } = await run([first, second]);
    expect(reddit.removed).toEqual([]);
  });

  test('letters are compared case-sensitively, like bot.py', async () => {
    const { reddit } = await run([c('a', 'x', [], { age: 60 }), c('A', 'y', [], { age: 10 })]);
    expect(reddit.removed).toEqual([]);
  });

  test('a duplicate goodbye with lower score is removed', async () => {
    const best = c('Addio', 'b', [], { score: 5, age: 10 });
    const worse = c('Addio', 'c', [], { score: 2, age: 5 });
    const { reddit, ouija } = await run([c('x', 'a', [best, worse])]);
    expect(reddit.removed).toEqual([worse.id]);
    expect(ouija.answerScore).toBe(5);
  });

  test('a newer goodbye is removed even with a higher score', async () => {
    const first = c('Addio', 'b', [], { score: 1, age: 20 });
    const newer = c('Addio', 'c', [], { score: 9, age: 5 });
    const { reddit } = await run([c('x', 'a', [first, newer])]);
    expect(reddit.removed).toEqual([newer.id]);
  });

  test('removed, deleted, stickied and distinguished comments are ignored', async () => {
    const tree = [
      c('ignored removed', 'a', [], { removed: true }),
      c('ignored deleted', undefined),
      c('ignored sticky', 'mod', [], { stickied: true }),
      c('ignored mod', 'mod', [], { distinguished: true }),
    ];
    const { reddit } = await run(tree);
    expect(reddit.removed).toEqual([]);
  });
});

describe('score and flair', () => {
  test('calcScore decreases with the age of the post', () => {
    const reddit = new FakeReddit();
    const log = new MemoryLogger();
    const age = (hours: number) =>
      new OuijaPost(reddit, post({ createdAt: new Date(NOW - hours * HOUR) }), log).calcScore(NOW);
    expect([0, 4, 8, 12, 16].map(age)).toEqual([5, 4, 3, 2, 1]);
  });

  test('without an answer an unflaired post gets "Senza risposta"', async () => {
    const info = post();
    const { reddit, ouija } = await run([], info);
    await ouija.changeFlair();
    expect(reddit.callsTo('setPostFlair')).toEqual([[info.id, UNANSWERED]]);
  });

  test('without an answer an already flaired post is untouched', async () => {
    const info = post({ flairText: UNANSWERED.text, flairCssClass: UNANSWERED.cssClass });
    const { reddit, ouija } = await run([], info);
    await ouija.changeFlair();
    expect(reddit.callsTo('setPostFlair')).toEqual([]);
  });

  test('an answer sets the flair and sends the modmail to OP', async () => {
    const info = post({ title: 'Domanda?' });
    const { reddit, ouija } = await run([chain('SI', 3)], info);
    await ouija.changeFlair();
    expect(reddit.callsTo('setPostFlair')).toEqual([
      [info.id, { ...ANSWERED, text: 'Ouija dice: SI' }],
    ]);
    const modmails = reddit.callsTo('sendModmail');
    expect(modmails).toHaveLength(1);
    const [to, subject, body] = modmails[0]!.map(String);
    expect(to).toBe('op');
    expect(subject).toBe('GLI SPIRITI HANNO PARLATO');
    expect(body).toContain('> Domanda?');
    expect(body).toContain('> SI');
    expect(body).toContain(`(${ouija.answerPermalink}?context=100)`);
  });

  test('long answers are truncated to 64 characters', async () => {
    const { reddit, ouija } = await run([chain('X'.repeat(80), 3)]);
    await ouija.changeFlair();
    const text = `Ouija dice: ${'X'.repeat(49)}...`;
    expect(text).toHaveLength(64);
    expect(reddit.callsTo('setPostFlair')).toEqual([[expect.any(String), { ...ANSWERED, text }]]);
  });

  test('no modmail when OP is deleted, and modmail errors are logged', async () => {
    const deleted = await run([chain('SI', 3)], post({ authorName: undefined }));
    await deleted.ouija.changeFlair();
    expect(deleted.reddit.callsTo('sendModmail')).toEqual([]);

    const reddit = new FakeReddit();
    const info = post();
    reddit.trees.set(info.id, [chain('SI', 3)]);
    reddit.failModmailFor.set('op', new Error('boom'));
    const log = new MemoryLogger();
    const ouija = new OuijaPost(reddit, info, log);
    await ouija.process();
    await expect(ouija.changeFlair()).resolves.toBeUndefined();
    expect(log.lines.some((line) => line.startsWith('ERROR Error sending PM to op'))).toBe(true);
  });
});
