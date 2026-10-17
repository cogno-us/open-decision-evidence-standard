# Reconstruction Bundle version

Status: behaviour note for the exporter; ODES remains draft.

`export_cognous_stack_package` now checks the retained Reconstruction Bundle's `bundle_version` before any other processing. Only `0.2.0` is supported. A different, empty or missing version raises `ExportError: unsupported Reconstruction Bundle version ...` instead of being exported as if it were `0.2.0`. Previously the field was not compared, so a changed version passed through unflagged.
