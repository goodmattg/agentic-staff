# Staff workflow

Generated from `staff_graph.py` using Pydantic Graph. `AwaitHost` saves a pending action and returns to the current chat. `Resume` continues its saved phase when the matching action result arrives. `Answer` and `Done` complete the invocation. Ordinary messages bypass this graph.

```mermaid
---
title: Staff workflow
---
stateDiagram-v2
  Resume
  state decision <<choice>>
  Classify
  Context
  Execute
  Finalize
  Plan
  Review
  state decision_2 <<choice>>
  state decision_3 <<choice>>
  state decision_4 <<choice>>
  state decision_5 <<choice>>
  state decision_6 <<choice>>
  state decision_8 <<choice>>
  Answer
  AwaitHost
  Done
  Synthesize
  state decision_7 <<choice>>
  Confidence

  [*] --> Resume
  Resume --> decision
  decision --> Classify
  decision --> Context
  decision --> Execute
  decision --> Finalize
  decision --> Plan
  decision --> Review
  Classify --> decision_2
  Context --> decision_3
  Execute --> decision_5
  Finalize --> decision_8
  Plan --> decision_4
  Review --> decision_6
  decision_2 --> Context
  decision_3 --> Plan
  decision_4 --> Execute
  decision_5 --> Review
  decision_2 --> Answer
  decision_3 --> AwaitHost
  decision_4 --> AwaitHost
  decision_5 --> AwaitHost
  decision_6 --> AwaitHost
  decision_6 --> Synthesize
  decision_8 --> AwaitHost
  decision_8 --> Done
  Answer --> [*]
  AwaitHost --> [*]
  Done --> [*]
  Synthesize --> decision_7
  decision_7 --> Plan
  decision_7 --> Confidence
  Confidence --> Finalize
```
