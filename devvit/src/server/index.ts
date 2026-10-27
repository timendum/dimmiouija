import { Hono } from 'hono';
import { serve } from '@hono/node-server';
import { createServer, getServerPort, settings } from '@devvit/web/server';
import type { TaskResponse } from '@devvit/web/server';
import type { UiResponse } from '@devvit/web/shared';
import { checkSubmissions, closeSubreddit, openSubreddit, withLock } from './bot';
import type { Deps } from './bot';
import { ANSWERED, MODPOST, UNANSWERED } from './config';
import { DryRunReddit, RedditGateway, redisStore } from './gateway';
import { consoleLogger } from './port';

// Devvit requests last at most 30s: stop processing posts after 20s
const CHECK_BUDGET_MS = 20_000;

async function readString(name: string): Promise<string> {
  return ((await settings.get<string>(name)) ?? '').trim();
}

async function makeDeps(): Promise<Deps> {
  const gateway = new RedditGateway({
    [UNANSWERED.cssClass]: await readString('flairUnansweredId'),
    [ANSWERED.cssClass]: await readString('flairAnsweredId'),
    [MODPOST.cssClass]: await readString('flairModpostId'),
  });
  const dryRun = (await settings.get<boolean>('dryRun')) ?? true;
  const legacyBot = await readString('legacyBotUsername');
  const botNames = [await gateway.getAppUsername()];
  if (legacyBot) botNames.push(legacyBot.replace(/^u\//, ''));
  return {
    reddit: dryRun ? new DryRunReddit(gateway, consoleLogger) : gateway,
    store: redisStore,
    log: consoleLogger,
    botNames,
    now: Date.now,
  };
}

async function runCheck(): Promise<boolean> {
  const deps = await makeDeps();
  const deadline = Date.now() + CHECK_BUDGET_MS;
  return withLock(deps.store, 60_000, () => checkSubmissions(deps, deadline));
}

function confirmForm(name: string, title: string, description: string): UiResponse {
  return {
    showForm: {
      name,
      form: {
        title,
        description,
        acceptLabel: 'Conferma',
        cancelLabel: 'Annulla',
        fields: [],
      },
    },
  };
}

const app = new Hono();

app.post('/internal/scheduler/check', async (c) => {
  try {
    if (!(await runCheck())) console.info('Check already running, skipped');
    return c.json<TaskResponse>({ status: 'ok' }, 200);
  } catch (error) {
    console.error('Check failed', error);
    return c.json<TaskResponse>({ status: 'error' }, 500);
  }
});

app.post('/internal/menu/check', async (c) => {
  try {
    const ran = await runCheck();
    return c.json<UiResponse>({
      showToast: ran ? 'Controllo completato' : 'Un controllo è già in corso',
    });
  } catch (error) {
    console.error('Check failed', error);
    return c.json<UiResponse>({ showToast: 'Controllo fallito, vedi i log' });
  }
});

app.post('/internal/menu/open', (c) =>
  c.json<UiResponse>(
    confirmForm(
      'openForm',
      'Aprire DimmiOuija?',
      "Riattiva le domande in automoderator, avvisa chi l'ha chiesto e prepara la lista PM."
    )
  )
);

app.post('/internal/menu/close', (c) =>
  c.json<UiResponse>(
    confirmForm(
      'closeForm',
      'Chiudere DimmiOuija?',
      'Blocca le domande in automoderator e pubblica il post con la data di riapertura.'
    )
  )
);

app.post('/internal/form/open', async (c) => {
  try {
    const caffe = await readString('caffeSubreddit');
    await openSubreddit(await makeDeps(), caffe.replace(/^r\//, ''));
    return c.json<UiResponse>({ showToast: { text: 'Subreddit aperto!', appearance: 'success' } });
  } catch (error) {
    console.error('Open failed', error);
    return c.json<UiResponse>({ showToast: 'Apertura fallita, vedi i log' });
  }
});

app.post('/internal/form/close', async (c) => {
  try {
    await closeSubreddit(await makeDeps());
    return c.json<UiResponse>({ showToast: { text: 'Subreddit chiuso', appearance: 'success' } });
  } catch (error) {
    console.error('Close failed', error);
    return c.json<UiResponse>({ showToast: 'Chiusura fallita, vedi i log' });
  }
});

serve({
  fetch: app.fetch,
  createServer,
  port: getServerPort(),
});
