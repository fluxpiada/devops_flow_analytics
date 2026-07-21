# Consistent, confident, and wrong: what building a test-automation business case taught me about measurement in an AI-native organisation

*Draft for LinkedIn. See the disclosure note at the bottom before publishing.*

---

We wanted to answer a simple question: should we automate our regression testing?

The finance template was waiting. Hours per regression run, runs per year, hourly
rate, multiply, compare against build cost, done. Two numbers and a calculator.

We couldn't fill in the first field.

Not because nobody knew, but because nobody had ever written it down. Zero worklogs
in Jira. Zero estimates. In the test management tool, the "elapsed time" field was
filled in on exactly one of 108 test results. Four people had spent five weeks on the
last regression round and the organisation held no record of how long it took them.

This is not unusual. Most organisations I work with cannot answer "how long does this
take us" about their own core processes. What made this one interesting is what
happened when we stopped asking people and started reading the exhaust.

## The data was there. It just wasn't a measurement.

Every test result carries two things nobody put there on purpose: who submitted it,
and when. Sort one tester's submissions by timestamp and look at the gaps between
them. A gap of four minutes is someone working. A gap of six hours is lunch, a
meeting, or tomorrow.

Cap the gaps at an hour, sum what's left, and you have hands-on time. Not because
anyone measured it — because the system timestamped a byproduct of the work.

For that five-week round: **seven hours** of hands-on execution across four people.

That number is wrong, and knowing exactly *how* it's wrong is the point. It's a lower
bound. It cannot see setup. It cannot see a tester staring at a failure trying to
work out whether it's a real defect. It cannot see an isolated result with no
neighbouring timestamp to measure against. The true figure is higher — but not
unboundedly higher, and now the conversation has a floor instead of a shrug.

The same round consumed **26 person-days** of calendar presence. Seven hours of
keyboard time inside 26 days of "I'm on the test round this week."

That gap is the finding. It isn't slack. It's coordination, waiting for an
environment, waiting for a fix, waiting for someone else to finish the step before
yours.

## What LEAN says about that gap

Map it as a value stream and the shape is familiar to anyone who has done this work.

From start of build to delivery: **83 working days**. Of those, 55 active and 28
waiting — a flow efficiency of **66%**, which is genuinely good by the standards of
most value streams I've mapped. Software teams commonly land between 5% and 15%.

But zoom into the test window and it inverts. A 25-working-day window with **8 days
of complete stillness** — days on which not a single test result was submitted by
anyone. Waiting for bug fixes, mostly. The median wait between a test failing and its
retest passing was **eight days**.

The instinctive management response to "testing takes five weeks" is to ask testers
to work faster. The data says the testers were barely the constraint. You could
double their speed and recover a fraction of the seven hours, while the eight idle
days sit untouched.

This is the oldest lesson in LEAN and it keeps needing to be relearned: optimise for
flow, not utilisation. The waste was in the handoffs.

## Then the question changed

The business case was supposed to be about efficiency. Automate the regression suite,
save the manual hours, count the savings.

So we counted how often regression actually ran. Over four years: **4, 4, 17 and 37**
executions per year. Against **300 to 1,100** tests per year for individual changes.

There were no hours to save. The organisation had not been doing the thing we
proposed to make cheaper.

You cannot automate your way to a capability you never built. If you automate a
practice that runs four times a year, you have bought an expensive way to keep not
doing it.

But that reframes rather than kills the case. The team's goal was never to keep the
current cadence — it was to refactor and simplify the process, and to do that safely
they need to regress the whole thing weekly. Weekly manual regression is arithmetically
impossible: one round takes five weeks. The case isn't *this saves money*. It's *this
is the only way to get the capability at all*.

Efficiency case versus enabler case. Different number, different conversation,
different decision-maker. The data didn't answer the original question — it revealed
that the original question was the wrong one.

That reframing was worth more than the ROI calculation, and no amount of refining the
spreadsheet would have produced it.

## Where the AI helped, and where it confidently lied

I built the whole analysis pipeline with an AI agent — API archaeology, changelog
parsing, the value-stream model, the management deck. Days of work compressed into
hours. That part worked.

Two failures are the more useful story.

**The deck remembered numbers it shouldn't have.** The generated slides looked
polished and the figures were right. Then I pointed the generator at a *second* test
round to compare. It produced a deck reporting the new round's 14 test cases and 2
person-days — alongside the old round's five-week duration, eight idle days and
four-tester work split. Half the slides were hardcoded prose from the first analysis.

A human writing slides knows to update the narrative when the numbers change. A
generator that was asked for "a deck about this analysis" happily welded one round's
data to another round's story. It never looked uncertain. Nothing failed. It rendered
beautifully.

**The pipeline would splice unrelated work together.** The analysis joins one Jira
story's lifecycle to one test run's execution data. Nothing checked that they
described the same piece of work. Pass a mismatched pair and you get a complete,
internally consistent, entirely fictional value stream. I had been pairing them by
reading the run title with my own eyes.

The fix was small: test runs already declare which issue they belong to. Read that
field, verify the pair, refuse to run when they don't match. Ten lines.

The lesson isn't small. **Plausible output is now nearly free. Verified output costs
exactly what it always did.** These systems fail by producing something coherent, and
coherence is precisely what we use as a heuristic for correctness. Every reviewer in
the chain — including me — was primed to accept a confident, well-formatted answer.

For anyone leading an AI-native transformation: your bottleneck moves. It stops being
*can we produce the analysis* and becomes *can we trust it*. Budget accordingly. The
guardrail work is the work now.

## The discipline that made it usable

One artefact did more for the credibility of this business case than anything else: a
table marking every quantity as **measured**, **derived**, **lower bound**, or
**assumed**.

Measured: status transitions, execution counts, first-pass rate, defect resolution
times, how often regression actually ran.

Lower bound: hands-on effort, with the reason it's a floor stated in the same
sentence.

Assumed: minutes per test execution, hours to automate a test case, annual maintenance
percentage, how much freed capacity converts into real output.

The assumptions are not a weakness in the case — they *are* the case. Every business
case is an argument built partly on judgement. The failure mode is not having
judgement in it; the failure mode is being unable to tell which parts are judgement
when someone challenges you in the steering committee.

We also removed two headline numbers from the summary because we could not
reconstruct where they came from. They had been quietly propagating through drafts
and had started to look like findings. Deleting them made the document weaker and
more honest, which is the right trade.

## Four things I'd carry into the next one

**Read the exhaust before commissioning a measurement.** Ticket systems, CI logs,
version control and test tools timestamp everything. You often already have six months
of history for a question you were about to spend six months instrumenting.

**Measure the waiting, not the working.** Effort data tells you what people did. Flow
data tells you why it took so long. They are rarely the same story, and only one of
them changes the decision.

**Let the data challenge the question.** We set out to price an efficiency gain and
discovered a missing capability. If your analysis only ever answers the question you
started with, it isn't telling you much.

**Separate what you know from what you assume, in writing.** Then defend the
assumptions openly rather than hiding them inside a formula. It survives scrutiny far
better, and it tells you exactly what your pilot should measure next.

---

We ran that comparison against a second round to validate our headline number. It
turned out not to be comparable — one tester, two days, no rework — which meant we
could not validate the number at all.

The honest conclusion was that the organisation has run a full end-to-end regression
exactly once.

Which, it turns out, was the strongest argument in the entire business case.

---

## Disclosure note — read before publishing

I wrote this without naming the organisation, the process, the systems or any
individual. The testers were already anonymised in the source analysis. But some
figures below are specific enough to identify the employer to anyone who knows where
you work, and they are internal operational metrics:

- `4, 4, 17, 37` regression executions per year and `300–1,100` change tests
- `1 of 2,868` test cases automated *(cut from this draft — flagging it in case you
  add it back, it is the single most identifying number)*
- `83 working days` lead time and `66%` flow efficiency
- `7 hours` hands-on across `26 person-days`

None of it is commercially sensitive in the usual sense — no customer data, no
financials, no security detail. But it is a candid account of a maturity gap, and
that is the employer's story to tell as much as yours.

Three options, in descending order of exposure: publish as-is; replace the specific
counts with ratios ("regression ran roughly twice a quarter against several hundred
change tests"); or clear it with whoever owns the transformation narrative first.

I would ask first. The post loses very little if the numbers become ratios, and the
argument does not depend on any single figure.
