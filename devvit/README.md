# DimmiOuija su Reddit Developer Platform (Devvit Web)

Port di `bot.py` (PRAW) verso [Devvit Web](https://developers.reddit.com/docs/capabilities/devvit-web/devvit_web_overview).
L'app gira sui server di Reddit, non ha bisogno di token OAuth, `praw.ini` o di un server con cron.

Requisiti: **Node.js 24** (Vite 8 e la CLI Devvit non funzionano con Node 20).

## Struttura

| File | Contenuto |
| --- | --- |
| `devvit.json` | Permessi, job schedulato, voci di menu, form, impostazioni |
| `src/server/index.ts` | Endpoint HTTP (scheduler, menu, form) |
| `src/server/ouija-post.ts` | Port di `OuijaPost`: regole sui commenti e composizione della risposta |
| `src/server/bot.ts` | Port di `PMList` e di `Ouija.check_submission` / `open` / `close` |
| `src/server/gateway.ts` | Adattatore verso l'API Reddit di Devvit, modalità prova, Redis |
| `src/server/config.ts` | Costanti e testi copiati da `bot.py` |
| `src/server/*.test.ts` | Test automatici (Vitest) |

## Cosa è stato migrato

| `bot.py` | Devvit |
| --- | --- |
| `python bot.py check` da cron | Job `check` in `devvit.json`, ogni 2 minuti, più voce di menu "DimmiOuija: controlla ora" |
| `python bot.py open` / `close` | Voci di menu del subreddit (solo mod) "DimmiOuija: apri" / "DimmiOuija: chiudi", con conferma |
| `praw.Reddit(...)` + credenziali | `permissions.reddit` (scope moderatore), nessun segreto |
| `subreddit.new(limit=100)`, `hot()` | `reddit.getNewPosts`, `reddit.getHotPosts` |
| `comments.replace_more(limit=None)` | `reddit.getComments({ sort: 'top' })` + `replies.all()` ricorsivo |
| `comment.mod.remove()` | `reddit.remove(id, false)` |
| `submission.mod.flair(...)` | `reddit.setPostFlair` (stesso template, testo e css class) |
| `subreddit.modmail.create` + `archive` | `reddit.modMail.createConversation` + `archiveConversation` |
| `subreddit.message(...)` (avvisi ai mod) | `reddit.modMail.createModNotification` |
| `subreddit.wiki[...]`, `.edit` | `reddit.getWikiPage`, `reddit.updateWikiPage` (wiki v1, come PRAW) |
| `submit`, `mod.sticky`, `mod.distinguish`, `reply` | `submitPost`, `post.sticky(1)`, `post.distinguish()`, `submitComment`, `comment.distinguish(true)` |
| `time.localtime` per la data di riapertura | `Intl.DateTimeFormat` con fuso `Europe/Rome` |

Regole sui commenti (identiche a `bot.py`):

- nuova domanda senza flair → flair "Senza risposta";
- commento più lungo di un carattere (grafema Unicode) e non un addio → rimosso;
- commento di OP → rimosso con tutte le risposte;
- risposta dello stesso autore del commento padre → rimossa con tutte le risposte;
- due risposte uguali allo stesso commento → si rimuove quella senza risposte (la più nuova se entrambe ne sono prive);
- addii duplicati sotto lo stesso commento → si rimuove quello visto dopo (ordine "top") se ha punteggio più basso o è più recente;
- catena completa con addio di almeno 3 punti (meno se il post è vecchio, `calc_score`) → flair "Ouija dice: ..." e modmail a OP.

La parità con `bot.py` è stata verificata eseguendo l'originale (con oggetti PRAW finti) e il port
sugli stessi 3000 alberi di commenti casuali: stesse rimozioni, stesse risposte, stessi punteggi.

### Differenze volute

- **Limite di 30 secondi** per richiesta: il controllo elabora i post per al massimo 20 secondi; se non finisce,
  salva in Redis l'ultimo post elaborato e riprende da lì al giro successivo. Un lock in Redis evita
  esecuzioni sovrapposte (scheduler + menu).
- Un post il cui autore è `[deleted]` non manda più in errore il controllo dei commenti.
- I commenti già rimossi non vengono rimossi una seconda volta (meno chiamate API, stesso risultato).
- **Modalità prova** (attiva di default): l'app legge tutto ma scrive solo nei log cosa farebbe.
- Gli ID dei template flair si possono cambiare dalle impostazioni (utile nei subreddit di test).

### Cose non migrate o da decidere

1. `ruota.py`, `dump.py` + `summary.py` (pagine riassuntive in wiki da SQLite/Jinja), `random_comment.py`,
   `clear_pmlist.py`: non fanno parte del bot descritto e restano in Python. SQLite non esiste su Devvit:
   andrebbero ridisegnati su Redis.
2. Apertura e chiusura sono **manuali** (menu). Se prima erano lanciate da un cron, si può aggiungere un job
   schedulato: serve sapere con che calendario.
3. In `close()` di `bot.py` la lista delle domande aperte viene calcolata ma non pubblicata
   (`selftext=PROSSIMA_TESTO`). Il port mantiene lo stesso comportamento: va deciso se pubblicarla.
4. La modifica di `r/italy/wiki/ambrogio_caffe` richiede che l'account dell'app possa modificare quella wiki
   (moderatore o contributore approvato di r/italy). È l'unica operazione su un altro subreddit: da verificare.
5. Post, commenti e modmail ora partono dall'account dell'app (`u/<nome app>`), non più dal vecchio account bot,
   salvo trasferimento dello username tramite il programma di migrazione di Reddit.
6. L'errore "utente inesistente" nella lista PM viene riconosciuto cercando `USER_DOESNT_EXIST` nel messaggio
   d'errore: da verificare in playtest con un utente inesistente.

## Impostazioni (per installazione)

| Impostazione | Default | Note |
| --- | --- | --- |
| Modalità prova | attiva | Disattivala per far agire davvero il bot |
| Subreddit con la wiki ambrogio_caffe | `italy` | Vuoto = non toccare nessuna wiki esterna |
| Username del vecchio bot | vuoto | Per riconoscere il post "Riapriamo il..." creato dal bot PRAW |
| ID template flair (3 voci) | vuoto | Vuoto = template di r/DimmiOuija |

Si modificano da `https://developers.reddit.com/r/<subreddit>/apps/<nome app>` (o dal pannello di installazione).

## Come testare

### 1. Test automatici

```sh
npm install && npm run type-check && npm test && npm run build
```

Attesi: nessun errore TypeScript, 39 test passati, `dist/server/index.cjs` generato.
I test usano un Reddit finto in memoria (`fake.test-utils.ts`) perché `@devvit/test` non simula
ancora flair, listing, moderazione, modmail e wiki.

### 2. Preparare un subreddit di test

1. Crea un subreddit privato (es. `r/DimmiOuijaTest`) di cui sei moderatore e mettilo in `dev.subreddit`
   di `devvit.json` (oppure `set DEVVIT_SUBREDDIT=DimmiOuijaTest`).
2. Crea tre template di flair per i post (Mod tools → Post flair), con **"modificabile dagli utenti/mod"**
   attivo per quello delle risposte, e css class `unanswered`, `answered`, `DimmiOuija`. Copia i tre ID.
3. Crea le pagine wiki `pmlist` (con 1-2 username di prova, uno per riga, es. il tuo secondo account)
   e `pmlist_todo` (vuota o con un carattere qualsiasi).
4. In `config/automoderator` aggiungi una regola con la riga da commutare subito prima del marcatore:

   ```yaml
   type: submission
   author:
       name: [qualcuno]
       # DummyUtente9510
   action: remove
   ```

5. Ti servono **tre account**: uno che fa la domanda (OP) e due (A e B) che si alternano nelle lettere,
   perché il bot rimuove i commenti di OP e le risposte date a se stessi.

### 3. Playtest

```sh
npm run login
npm run dev
```

Apri il link stampato dalla CLI. Nelle impostazioni dell'app nel subreddit di test inserisci i tre ID dei flair
e svuota "Subreddit con la wiki ambrogio_caffe" (a meno che tu non voglia testare una wiki di prova:
in quel caso metti il nome del tuo subreddit di test e crea la pagina `ambrogio_caffe` con la riga `[](/oggi-start)`).
Lascia **attiva** la modalità prova per il primo giro. I log si leggono nel terminale di `npm run dev`
o con `npx devvit logs <subreddit>`.

| # | Azione | Risultato atteso |
| --- | --- | --- |
| 1 | Modalità prova attiva: crea una domanda e un commento "ciao", poi menu del subreddit → "DimmiOuija: controlla ora" | Toast "Controllo completato"; nei log `[DRY RUN] flair ... Senza risposta` e `[DRY RUN] remove t1_...`; nulla cambia sul subreddit |
| 2 | Disattiva la modalità prova e ripeti "controlla ora" | La domanda prende il flair "Senza risposta", il commento "ciao" sparisce |
| 3 | Con l'account A commenta `S`, con B rispondi `I`, con A rispondi `Addio`; dai 3 upvote all'addio (o aspetta 8 ore per post vecchi) | Al controllo successivo (≤ 2 min) flair "Ouija dice: SI" e modmail "GLI SPIRITI HANNO PARLATO" all'autore della domanda (nella modmail del subreddit è archiviata) |
| 4 | Su una nuova domanda: l'autore della domanda commenta `X` | Il commento (e le sue risposte) viene rimosso |
| 5 | A commenta `A` e A stesso risponde `B` | La risposta `B` viene rimossa |
| 6 | A e B rispondono entrambi `C` allo stesso commento, senza risposte sotto | Viene rimosso il più recente |
| 7 | Un mod pubblica un post e lo "distingue" (o lo fissa) | Riceve il flair dei post dei mod |
| 8 | Menu → "DimmiOuija: chiudi" → Conferma | Nella regola automod `name:` diventa `~name:`; nuovo post "Riapriamo il <data fra 13 giorni e mezzo>" fissato in alto e distinto, con commento distinto e fissato |
| 9 | Con un altro account rispondi al commento fissato del post di chiusura | – |
| 10 | Menu → "DimmiOuija: apri" → Conferma | Automod torna a `name:`; il post di chiusura non è più fissato; la tua risposta del punto 9 riceve "Ciao, gli spiriti sono arrivati..."; `pmlist_todo` contiene la lista di `pmlist` |
| 11 | Aspetta 1-2 giri del job | A ogni giro il primo utente di `pmlist_todo` riceve la modmail "Sei stato convocato su DimmiOuija" e viene tolto dalla lista |
| 12 | Metti in `pmlist_todo` un utente inesistente | Arriva ai mod una notifica modmail con oggetto = username e testo "User not found" (se invece compare solo un errore nei log, segnalamelo: va adattato il riconoscimento dell'errore) |
| 13 | Togli la riga `# DummyUtente9510` da automod e premi "chiudi" | Notifica ai mod "ERRORE Chiusura!!!" / "Automod non gestito" |

### 4. Passaggio in produzione

1. `npm run deploy` e installa l'app in r/DimmiOuija: la modalità prova è attiva di default, quindi può
   convivere con il bot Python. In "Username del vecchio bot" inserisci l'account del bot PRAW.
2. Lascia girare qualche ciclo e confronta i log (`npx devvit logs DimmiOuija`) con quello che fa il bot Python.
3. Ferma il cron del bot Python (non devono agire entrambi), poi disattiva la modalità prova.

## Comandi

```sh
npm install
npm run type-check   # TypeScript
npm test             # test automatici (Vitest)
npm run build        # bundle in dist/server
npm run login        # login alla CLI Devvit
npm run dev          # playtest nel subreddit indicato da dev.subreddit / DEVVIT_SUBREDDIT
npm run deploy       # type-check + test + devvit upload
npm run launch       # deploy + devvit publish (revisione di Reddit)
```
