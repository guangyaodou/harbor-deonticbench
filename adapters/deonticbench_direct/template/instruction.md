The relevant statute is available at `/app/statute.txt`.
{% if text %}

**Case Facts:**
{{ text }}
{% endif %}

**Question:**
{{ question }}

Carefully read the statute and apply it to the facts to determine the answer.

Write your final answer to `/app/output/answer.txt` in exactly this format (one line):

```
Answer: <value>
```

{{ answer_format_instruction }}

The task is complete once `/app/output/answer.txt` exists and contains your `Answer:` line.
