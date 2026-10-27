// Constants ported from bot.py

export type FlairSpec = {
  text: string;
  cssClass: string;
  flairTemplateId: string;
};

export const SCORE_LIMIT = 3; // comment score must be >=
export const GOODBYE = /^(?:Goodbye|Arrivederci|Addio)/i;
export const WAIT_NEXT = 1000 * 60 * 60 * (24 * 13 + 12); // 13 days + 12 hours, for daylight saving
export const TIME_ZONE = 'Europe/Rome';

export const UNANSWERED: FlairSpec = {
  text: 'Senza risposta',
  cssClass: 'unanswered',
  flairTemplateId: 'c08164be-2cf7-11e8-82fd-0e9dcb216a98',
};
export const ANSWERED: FlairSpec = {
  text: 'Ouija dice: ',
  cssClass: 'answered',
  flairTemplateId: '456a526e-8c01-11e7-bb65-0ed09cec4484',
};
export const MODPOST: FlairSpec = {
  text: 'DimmiOuija',
  cssClass: 'DimmiOuija',
  flairTemplateId: '4341ba2c-8c01-11e7-93f7-0e091235c204',
};

export const MESI = [
  'None',
  'gennaio',
  'febbraio',
  'marzo',
  'aprile',
  'maggio',
  'giugno',
  'luglio',
  'agosto',
  'settembre',
  'ottobre',
  'novembre',
  'dicembre',
];

export const PROSSIMA_TITOLO = 'Riapriamo il ';
export const PROSSIMA_TESTO = `Qui potete commentare i risultati di questo giro.

Nel frattempo non sarà possibile porre nuove domande, solo concludere quelle già aperte.`;
export const PROSSIMA_APERTE = '\n\nLe domande aperte ad ora sono:\n\n';
export const APERTURA_TITOLO = 'Sei stato convocato su DimmiOuija';
export const PROSSIMA_COMMENTO = `Vuoi essere contattato ad OGNI apertura?
[Scrivici in modmail](https://www.reddit.com/message/compose?to=%2Fr%2FDimmiOuija&subject=Aggiungimi)
e sarai aggiunto alla lista.

Vuoi essere avvertito solo della prossima apertura?
Rispondi a QUESTO commento.`;
export const APERTURA_COMMENTO = 'Ciao,  \ngli spiriti sono arrivati r/DimmiOuija.\n\nUn saluto.';
export const PM_ANSWER_TITLE = 'GLI SPIRITI HANNO PARLATO';
export const PM_ANSWER_BODY = `Hai chiesto:
> {question}

Gli spiriti dicono:
> {answer}

[Commenta qui]({permalink}?context=100)`;
export const TEXT_WIKI_CAFFE =
  'Oggi è aperto /r/DimmiOuija, dove si possono fare domande ' +
  'e ricevere risposte, una lettera alla volta. Partecipazione aperta a tutti.';

// The automoderator rule toggled by open/close is the line before this marker
export const AUTOMOD_MARKER = 'DummyUtente9510';
