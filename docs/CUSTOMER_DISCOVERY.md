# Customer Discovery

The purpose of discovery is to falsify or support the paid-pilot hypothesis in
`docs/PAID_PILOT.md`. It is not a product pitch and should not be used to manufacture positive
feedback.

## Recruitment

Interview people responsible for an agent already used in customer support, finance operations,
security operations, or another workflow with consequential tool calls. Prioritize the
engineering owner, the operator who handles exceptions, and the person accountable for risk or
budget. Avoid counting people who are only exploring agents and have no deployed workflow.

Do not put customer names, personal data, credentials, incident details, or confidential logs in
this public repository. Store interview notes in an approved private system and use anonymous
identifiers in aggregate results.

## Thirty-minute interview

Spend the first 20 minutes on past behavior before showing the demo.

1. What agent workflow is running today, and who owns it when something goes wrong?
2. Tell me about the last incorrect or risky action. What happened next?
3. Which actions require a person to review them today? Walk through the actual process.
4. How often are actions delayed, repeated, silently dropped, or approved without enough context?
5. How do you determine which agent, prompt, tool call, and person caused an outcome?
6. When did you last pause or roll back an agent? How long did diagnosis and recovery take?
7. What does the current process cost in engineering time, operator time, refunds, or risk?
8. Which controls are mandatory before this workflow can handle more volume?
9. Who owns the budget for fixing this, and what has already been purchased or built?
10. Is there a time-bound project where a three-week staging pilot could be evaluated?

Then show the refund-approval scenario. Ask what would have to change for it to fit their actual
workflow, which evidence is missing, who else must approve a pilot, and what decision date is
realistic. Do not ask whether they "like" the product or whether they "would use" it someday.

## Evidence record

Record one row per interview outside the public repository:

| Field | Evidence to capture |
| --- | --- |
| Segment | Industry, team function, and deployed-agent maturity |
| Last incident | Date range, failure type, impact, and current recovery path |
| Frequency | Consequential actions and manual reviews per week |
| Current spend | Tools plus engineering and operator effort |
| Required control | Approval, audit, pause, replay, evaluation, or another named need |
| Buying process | Budget owner, security owner, procurement steps, and deadline |
| Commitment | Introduction, data sample, technical session, trial, or paid pilot |
| Disconfirming evidence | Reason the problem is unimportant or already solved |

Separate direct quotes and observed behavior from interpretation. A verbal compliment is not a
commitment; access to a technical owner, sanitized cases, scheduled integration time, or payment
is progressively stronger evidence.

## Decision thresholds

Run 20 qualified interviews before broadening the product. Continue toward the refund pilot if
at least eight teams report the problem from recent experience, five provide a technical follow-
up or representative cases, two commit engineering time to an evaluation, and one signs a paid
pilot within eight weeks.

Stop or change the segment if fewer than five teams report a recent consequential failure, the
problem has no named budget owner, or existing observability and workflow tools already solve it
without meaningful friction. Build Mem0, DSPy, Temporal, or another major adapter only when
repeated interview and pilot evidence identifies that capability as the blocker.
