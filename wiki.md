Risposte del {{day}}

{% for question in questions %}
### [{{question.title}}]({{question.permalink}})

> {{question.answer}}
{% endfor %}