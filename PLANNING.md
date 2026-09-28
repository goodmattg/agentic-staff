# Mindset

We approach problems with curiosity and optimism.

# Operating Loop

An explicitly invoked staff `[[QUERY]]` comes in via the user interface. Ordinary
requests and followups use the base model. `staff_graph.py` is the executable
workflow; the skill only bridges its requested actions to native harness tools.

Branch if the `[[QUERY]]` is `[TYPE-QUERY-KQ]` or`[TYPE-QUERY-CCR]` using `[[JEV]]`

## Knowledge Question (`[TYPE-QUERY-KQ]`)

### STEP: Answer `[[QUERY]]`

Answer immediately with the root model. Exit the operating loop.

## Codebase Change Request (`[TYPE-QUERY-CCR]`)

### STEP: Build our context for the Query. (`[STEP-BUILD-CONTEXT]`)

Execute `[STEP-PREVIOUS-CONVERSATION-CONTEXT]` and `[STEP-BUILD-CONTEXT]` in parallel. Then move to `[STEP-DECIDE-TICKET-TYPE]`.

#### STEP: Previous Conversation Context Lookup (`[STEP-PREVIOUS-CONVERSATION-CONTEXT]`)

For each conversation in every harness / tool we identify in Appendix, apply `[[JEV]]` to determine if it is relevant to the current `[[QUERY]]` with high numerical threshold for relevance.

If above relevance threshold, pull the files in codebase from that conversation and the conversation itself into context.

#### STEP: Query Specific Context Lookup (`[STEP-QUERY-SPECIFIC-CONTEXT]`)

Root model pulls tree of relevant files into context based on `[[QUERY]]`.

### STEP: Decide the ticket type (`[STEP-DECIDE-TICKET-TYPE]`)

Apply `[[JEV]]` to determine the type of ticket (`[TICKET-TYPE-*]`). Then move to `[STEP-DECIDE-TICKET-SCOPE]`.

#### Chore (`[TICKET-TYPE-CHORE]`)

Chore refers to minor cleanups in backend code or changing the visual appearance of frontend views, package upgrades, anything deemed a ~nice-to-have~ (e.g. syntactic sugar), variable renaming, code refactoring that is stylistic only, responding to linting and variable naming feedback.

#### Bug (`[TICKET-TYPE-BUG]`)

Bug refers to an error that has been experienced by the software user in its intended use or that the platform has registered during user use.

#### New Feature (`[TICKET-TYPE-NEW-FEATURE]`)

The development of a new feature in the platform that is intended for immediate use by users.

#### Experiment (`[TICKET-TYPE-EXPERIMENTAL-FEATURE]`)

The development of an experimental feature in the platform that is not intended for immediate use by users.

### STEP: Decide the ticket scopes (`[STEP-DECIDE-TICKET-SCOPE]`)

Apply `[[JEV]]` to determine the scopes of ticket. We apply a separate filter to each in `[[JEV]]` with a moderately high confidence threshold. Ticket can take on one or more scopes. Then move to `[STEP-DECIDE-SEVERITY]`.

Ask where the user encounters the problem, not which code we expect to edit. A named page counts as frontend even when the sentence does not say the layout will change.

#### Frontend (`[TICKET-SCOPE-FRONTEND]`)

The user encounters this on a screen: a page, button, or other thing they can see.

#### CI/CD (`[TICKET-SCOPE-CI-CD]`)

The user encounters this in the build or deploy pipeline.

#### Cloud Infrastructure (`[TICKET-SCOPE-CLOUD-INFRA]`)

The user encounters this in cloud infrastructure, such as AWS, Terraform, or Vercel.

#### Backend (`[TICKET-SCOPE-BACKEND]`)

The user encounters this through server or service behavior, such as an API or stored data.

### STEP: Decide the severity of the change (`[STEP-DECIDE-SEVERITY]`)

We run `[[JEV]]` with high confidence threshold to inspect `[[QUERY]]` to see if it provides explicit language dictating the severity of the ticket, if yes, use that value of `[TICKET-SEVERITY-*]` and move to `[STEP-DECIDE-MODEL-INTELLIGENCE]`. Otherwise, given `[TICKET-TYPE-*]` and one or more `[TICKET-SCOPE-*]` we use `[[JEV]]` to decide ticket severity. We follow standard escalation pattern to decide `[TICKET-SEVERITY-*]` capping at `[TICKET-SEVERITY-CRITICAL]`. Bubble up values of`[DECISION-*]` in ticket escalation, do not repeat decision.

#### Low `[TICKET-SEVERITY-LOW]`

- Chore: always
- Bug: must be judged via `[[JEV]]` with high threshold to be both latent and unlikely to be hit in the course of normal use (`[DECIDE-BUG-LATENT-UNLIKELY]`).
- New-Feature: must have exactly 1 `[TICKET-SCOPE-*]` and be judged via `[[JEV]]` with high threshold to not impact existing functionality; existing functionality working is not contigent on success of the new feature (`[DECIDE-NEW-FEATURE-UNCOUPLED]`).
- Experiment: always

#### Medium `[TICKET-SEVERITY-MEDIUM]`

- Chore: never
- Bug: must be judged via `[[JEV]]` with high threshold to be latent (`[DECIDE-BUG-LATENT]`).
- New-Feature: must have <=2 `[TICKET-SCOPE-*]` and be and be judged via `[[JEV]]` with high threshold to not impact existing functionality; existing functionality working is not contigent on success of the new feature (`[DECIDE-NEW-FEATURE-UNCOUPLED]`).
- Experiment: never

Applies to bugs that are not latent and impacting user features that are not critical to day-to-day operation.

#### High `[TICKET-SEVERITY-HIGH]`

- Chore: never
- Bug: user encountered live bug that is unlikely to be hit again in the course of normal use (`[DECIDE-BUG-LIVE-UNLIKELY]`).
- New-Feature: must be judged via `[[JEV]]` with high threshold to not impact existing functionality; existing functionality working is not contigent on success of the new feature (`[DECIDE-NEW-FEATURE-UNCOUPLED]`).
- Experiment: never

#### Critical `[TICKET-SEVERITY-CRITICAL]`

Final escalation severity point for all tickets.

### STEP: Decide Model Intelligence (`[STEP-DECIDE-MODEL-INTELLIGENCE]`)

The value of `[TICKET-SEVERITY-*]` determines the model intelligence to use for planning (`[PLANNING-MODEL-INTELLIGENCE]`) and then for execution (`[EXECUTION-MODEL-INTELLIGENCE]`).

Map for `[PLANNING-MODEL-INTELLIGENCE]`:

`[TICKET-SEVERITY-LOW]`: GPT 6.0 Astra, effort medium
`[TICKET-SEVERITY-MEDIUM]`: GPT 6.0 Astra, effort high
`[TICKET-SEVERITY-HIGH]`: GPT 6.0 Astra, effort xhigh
`[TICKET-SEVERITY-CRITICAL]`: GPT 6.0 Astra, effort xhigh

Map for `[EXECUTION-MODEL-INTELLIGENCE]`:

`[TICKET-SEVERITY-LOW]`: GPT 6.0 Sol, effort medium
`[TICKET-SEVERITY-MEDIUM]`: GPT 6.0 Sol, effort high
`[TICKET-SEVERITY-HIGH]`: GPT 6.0 Sol, effort high
`[TICKET-SEVERITY-CRITICAL]`: GPT 6.0 Sol, effort xhigh

Then move to `[STEP-DECIDE-TESTING-STANDARDS]`.

### STEP: Decide Testing Standards (`[STEP-DECIDE-TESTING-STANDARDS]`)

The type and extent of testing in our execution plan is determined by the type of ticket and the scopes that cleared the threshold. If no scope cleared it, do not pick a testing row yet. Read the code the change touches, then apply the row for the layers that code is in. An empty scope list is not a reason to skip tests. Unless specified do not add unit tests. Unit tests can be used by the agent during development but should not be retained unless the category below calls for it.

- UX change: no testing
- infra gap causing bug: Dry-run of infra change if available, no unit tests. Post-execution end-to-end testing.
- infra change: Dry-run of infra change if available, no unit tests. Post-execution end-to-end testing.
- backend bug: modify existing unit tests if any coverage, else add new unit test. End-to-end test frontend feature(s) that backend component touches if any, or if purely backend apply an end-to-end test of the backend functionality in the most heavily trafficked usage pattern.
- frontend bug: End-to-end test frontend feature
- full-stack bug: modify existing unit tests if any coverage, else add new unit test. End-to-end test full-stack feature(s) in the most heavily trafficked usage pattern.
- new feature combining UX + backend: unit-tests for the backend, end-to-end test the full-stack feature in the expected primary usage pattern for operators.
- new feature combining UX + backend + infra change: unit-tests for the backend, end-to-end test the full-stack feature in the expected primary usage pattern for operators.

Then move to `[STEP-DECIDE-EXECUTE]`.

### STEP: Decide Execute (`[STEP-DECIDE-EXECUTE]`)

We keep a count (`[COUNT-EXECUTION-LOOP]`) of the number of repeats of the execution loop, initial value 0, maximum value num repeats `[MAX-EXECUTION-LOOP]`.

The value of `[TICKET-SEVERITY-*]` determines `[MAX-EXECUTION-LOOP]`.

`[TICKET-SEVERITY-LOW]`: 1
`[TICKET-SEVERITY-MEDIUM]`: 2
`[TICKET-SEVERITY-HIGH]`: 3
`[TICKET-SEVERITY-CRITICAL]`: 3

If count value is 0, move to `[STEP-EXECUTE-OR-REVISE]`. If the count value is >= `[MAX-EXECUTION-LOOP]` move to `STEP-POST-EXECUTE-RESPONSE`.

### STEP: Execute or Revise (`[STEP-EXECUTE-OR-REVISE]`)

This step creates a plan with `[PLANNING-MODEL-INTELLIGENCE]` and executes it with `[EXECUTION-MODEL-INTELLIGENCE]` using the `isolated-pr-workflow` skill. Context for the planning and execution is:

- existing PR if `[COUNT-EXECUTION-LOOP]` > 1; the first pass creates the PR
- synthesized feedback from `[STEP-REVIEW-SYNTHESIS]` if `[COUNT-EXECUTION-LOOP]` > 1

### STEP: Review Panel (`[STEP-REVIEW-PANEL]`)

We have a panel of multiple reviewers each with a different viewpoint on how we do software engineering. Each operates in parallel as an isolated sub-agent. When all are complete we pass through all feedback to `[STEP-REVIEW-SYNTHESIS]`.

#### STEP: Reviewer: Jeff Dean (`[STEP-REVIEW-BORING-STANDARD-EFFECTIVE]`)

Jeff's mantra is "Boring, Standard, Effective". He demands that there be nothing ~weird~ and nothing that isn't standard in our work that can't be defended out of necessity. We choose coding patterns, data structures, design patterns, that are battle tested at scale or have demonstrated effectiviness in the specific domain of the task we are working on.

#### STEP: Reviewer: Elon Musk (`[STEP-REVIEW-NO-EXTRA-REQUIREMENTS]`)

Elon applies SpaceX engineering standards to our software. We are always trying to cut requirements that are unneeded or leading to worse performance. No cruft, no overcomplication, no perfomative code; no code that exists becaues it looks good or ~should~ be there as the part of some imagined ideal situation, but doesn't offer our software a tangible benefit in the situations and usage patterns we are actually expecting. Elon is hypervigilant about the tradeoff of complexity to effectiveness. He only accepts added complexity when it passes a high bar of being required to acheive a level of effectiveness we are seeking.

#### STEP: Reviewer: Jeff Bezos (`[STEP-REVIEW-OPERATOR-OBSESSION]`)

Jeff driving telos is perator obsession: we care deeply about normal non-technical people using this, buttons must work, must look right for normal operating paths and usage, prioritizing hot operating paths of core functionality, we cannot crash without action to take or explanation for the user, graceful behavior. Prefer degraded isolated functionality that can come back online instead of hard crashes that will confuse and infuriate the user. Jeff accepts that normal users to not share our level of technical sophisticiation and we have a limited opportunity to present them with software that ~just works~, language that is plain and not confusing, and an overall user experience that is exceptional.

#### STEP: Reviewer: Mark (`[STEP-REVIEW-FORWARD-LOOKING]`)

Mark is a forward thinking staff engineer. He understands that shortcuts may lead to less copmlexity in the short-term but can conflict with our stated long-term technical direction. While we like to keep our code changes lean and minimal, we should not take shortcuts if the way we execute a change is in contradiction to a future strategic direction we have documented we are taking or it is clear we are taking the immediate decision is not long-term effective. We are often fine documenting the known limitations we are introducing inline with the explicit intention to improve and extend later, but these are documented and escalated, not silent.

#### STEP: Reviewer: Steve (`[STEP-DEVELOPER-OBSESSED]`)

Steve offers feedbacks and low level refactors based on our code guidelines. Steve believes new code we intrdouce must match our developer guidelines because we respsect our developers. Steve is also obsessed with keeping our documentation up-to-date. Steve confirms that documentation is holisically valid after new changes, and if not proposes narrow changes to the documentation that will update it.

### STEP: Review Synthesis (`[STEP-REVIEW-SYNTHESIS]`)

First we use `[[JEV]]` to filter out any identified bugs in our execution that are judged to be inconsequential - inconsequential can mean outside of normal operating path and procedures of regular usage - i.e. if a path would technically cause a bug, but that path will never be explored because the UX does not allow it, can be filtered out of the feedback report.

We then concatenate the feedback our independent review panel provided.

### STEP: Post-Execute Response (`STEP-POST-EXECUTE-RESPONSE`)

Cntext input is existing PR, review feedback from agents with reasoning (most recent round), whether we terminated early

BRANCH ON POST-COMPLETION CONFIDENCE [JEV] to estimate if our work accomplished the task with a high quality bar.

If low confidence, escalate to the user with a tersely summarized evidence of LOW CONFIDENCE, for high evidence, terse answer of "good to ship" with concise bullets (limited to three) of why we are confident. Confidence evidence can include small blast radius, testing quality, comprehensiveness, diversity, and exhaustiveness of e2e testing, synthesis of new testing + previous testing covered, holistic judgement. Also make sure the Github PR is marked as Draft.

If high confidence, make sure the Github PR is marked as Ready for Review and remove the worktree on the machine.

# Appendix

- Seeing `[[JEV]]` in these docs is a stand-in for an LLM classifier to structure output decision. We are currently going to use Jev from TypeSafe AI because of its cost structure, but will switch back to OpenAI / OSS if comparable solution becomes available.
