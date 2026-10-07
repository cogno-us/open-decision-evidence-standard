# Merged producer compatibility checkpoint

This change adds `odes-cognous-stack-export-0.2.1` for the exact producer combination below. Historical mappings remain available. It consumes the existing bounded workflow export 2.0.0; it does not export atomic execution claims or refund-intent registry evidence.

| Component | Exact revision |
| --- | --- |
| cognous-action-manifest | `46c950bed37fe3812000895430bc0312d29e37ce` |
| cognous-replay-bundle | `459e4ba62fca49364aebb0050cd5fb2dd5a71bfa` |
| cognous-control-plane | `d3dadee70bd319812b207389ab1e0f6efe511916` |
| cognous-execution-runtime | `c3c3ee7188b9367cf70b08074b9c40a5c70c94ac` |

The actual producer workflow runs 15 lifecycle scenarios. Import/export, validation and rendering or recipient evaluation occur inside assertions that retained Control Plane record bytes and logical SQLite destination contents remain unchanged. Held decisions, uncertain observations, lost acknowledgements and historical effects retain their existing distinctions.

The dedicated workflow runs separate Linux Python 3.11 and 3.12 jobs, with a 120-second generator timeout, a 150-second test process limit, a three-minute test step limit and a ten-minute job limit. Missing configured checkouts fail the dedicated qualification. Existing historical CI remains intact. JUnit and scenario artifacts are retained.

No hub dependency pin is advanced. No external truth, delivery authentication, production enforcement, distributed atomicity or EBL conformance is established. ODES/GAX composition with the new Evidence Pack remains a separate integration gate.

Local dedicated qualification: 54 passed. Repository CI must separately qualify the published commit.
