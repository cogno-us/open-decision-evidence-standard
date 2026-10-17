# Export from a shared journal

Status: behaviour note for the exporter; ODES remains draft.

A Control Plane journal can retain decisions for unrelated proposals, for example a held, unauthorized request that shares the journal with a valid flow. Previously the exporter refused with `export supports exactly one retained runtime_decision` whenever more than one `runtime_decision` was retained, so one unauthorized hold blocked export of the valid flow's evidence.

The exporter now selects the flow's decision when, and only when, retained execution evidence (`execution_envelope`, `execution_result`, `destination_attempt` or `control_plane_attempt_transition` records) names exactly one of the retained decisions by `decision_id`. All existing decision/execution/proposal consistency checks then run on that decision.

The exporter still fails closed, with the same error, when the situation is ambiguous: several decisions and no execution evidence, several decisions each referenced by execution evidence, or evidence that references none of them.

The package's `evidence_hash` still covers the whole supplied bundle, so unrelated retained decisions remain bound to the exported record even though they are not the exported decision.
