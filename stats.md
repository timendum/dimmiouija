# Statistiche del {{day}}

## Partecipazione

Gli spiriti hanno risposto a {{questions|length}} domande.

Che sono presentate presentate da {{authors|length}} questionanti.

Hanno partecipato {{mediums}} medium.

Le risposte complessivamente sono lunghe {{charlenght}} caratteri.

Sono state risolte {{ruote|length}} Ruote della fortuna.

## Lunghezza delle risposte

Le risposte più lunghe sono state:
{% for longer in questions|top_answer(4) %}
1. [{{longer.answer}}]({{longer.permalink}}) ({{longer.answer|length}})
{%- endfor %}
{%set shorters = questions|bottom_answer %}{% if shorters|length > 1 %}
Le risposte più corte sono state: 
{% for shorter in shorters %}
1. [{{shorter.answer}}]({{shorter.permalink}}) ({{shorter.answer|length}})
{%- endfor %}
{% else %}
La risposta più corta ({{shorters[0].answer|length}} caratteri) è stata:
{% for shorter in shorters %}[{{shorter.answer}}]({{shorter.permalink}}){% endfor %}
{%- endif %}

{% if size %}### Statistiche

La lunghezza media delle risposte è stata: {{size.mean|round(1)}}  
La mediana della lunghezze delle risposte è stata: {{size.median|round(1)}}  
La moda della lunghezze delle risposte è stata: {{size.mode}}
{%- endif %}

## Autori delle domande

Gli utenti che hanno posto più domande sono stati: 
{% for key, value in authors|top_counter(4) %}
1. /u/{{key}} ({{value}})
{%- endfor %}

## Autori delle risposte

Alle risposte hanno partecipato {{solvers|length}} spiriti.

Gli utenti che hanno contribuito di più alle risposte sono stati: 
{% for key, value in solvers|top_counter(9) %}
1. /u/{{key}} ({{value}})
{%- endfor %}

{% if solver %}### Statistiche

Il numero medio di lettere per utente è stato: {{solver.mean|round(1)}}  
La mediana del numero di lettere per utente è stato: {{solver.median|round(1)}}  
La moda del numero di lettere per utente è stato: {{solver.mode}}
{%- endif %}

## Autori dei Goodbye

Gli utenti che hanno inserito più Goodbye: 
{% for key, value in goodbyers|top_counter(3) %}
1. /u/{{key}} ({{value}})
{%- endfor %}

{% if ruote_solvers %}
## Solutori della Ruota della fortuna

Gli utenti che hanno indovinato di più le Ruote della fortuna: 
{% for key, value in ruote_solvers|top_counter(5) %}
1. /u/{{key}} ({{value}})
{%- endfor %}
{% endif %}

## I caratteri

Sono stati utilizzati {{chars|length}} caratteri diversi: 

I caratteri più utilizzati sono stati: 

Char | Freq
---|---
{% for key, value in chars.most_common() %}{{key}} | {{value}}
{% endfor %}

## Tempi delle risposte

La classifica delle tempi di chiusura: 
{% for time, question in open_time[:5] %}
1. [{{question.title}}]({{question.permalink}}) ({{time|time_string}})
{%- endfor %}

...

Ultimo: {% for time, question in open_time[-1:] %}[{{question.title}}]({{question.permalink}}) ({{time|time_string}}){% endfor %}

{% if ruota %}
Le ruote della fortuna più rapide: 
{% for time, ruota in ruote_open_time %}
1. [{{ruota.answer}}]({{ruota.permalink}}) ({{time|time_string}})
{%- endfor %}
{% endif %}



{% if otime %}### Statistiche

Le domande hanno dovuto attendere per una risposta mediamente {{otime.mean|time_string}}  
Il tempo mediano di apertura per le domande è stato: {{otime.median|time_string}}
{%- endif %}

