# API

Product routes remain under `/api/v1/products`.

## BFF response-contract migration

The catalog service is migrating to the platform BFF response contract described
in [the migration guide](../../../docs/architecture/bff_api_contract.md) and
ADR 0031.

In the first rollout, product command endpoints — create, update, activate,
deactivate, and delete — return the success envelope. Product queries and image
endpoints retain their current flat success payload until their dedicated
migration changes. All catalog error responses use the structured BFF error
shape immediately.
