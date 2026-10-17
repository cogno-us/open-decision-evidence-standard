# Retained Replay bundle comparison

Status: behaviour note for the exporter; ODES remains draft.

For producer-v2 bundles the exporter re-runs the pinned Replay import over the retained records and requires the retained bundle to equal the fresh reconstruction in `records`, `links`, `commitments`, `producer_profiles`, `status`, `import_reports` and `semantics` (plus the existing metadata comparisons). `import_reports` and `semantics` were previously not compared, so dropped reports or findings, or promoted semantics (independent effect verification, destination observation), were exported unflagged. They are now refused with `retained Replay import_reports|semantics differs from accepted validator reconstruction`. Same pattern as cognous-governance-evidence-pack PR #34.
