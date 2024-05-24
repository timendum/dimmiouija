Risposte del {{day}}

{% for question in questions %}
### [{{question.title}}]({{question.permalink}})

> {{question.answer}}
{% endfor %}

{% if ruota %}
## Ruota della fortuna:

{% for ruota in ruote %}
### [{{ruota.answer}}]({{ruota.permalink}})

{% endfor %}
{% endif %}