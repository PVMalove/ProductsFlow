# API

Product routes remain under `/api/v1/products`.

## BFF response-contract migration

The catalog service is migrating to the platform BFF response contract described
in [the migration guide](../../../docs/architecture/bff_api_contract.md) and
ADR 0031.

Product command endpoints — create, update, activate, deactivate, and delete —
and product GET-queries — read, list, and audit — return the success envelope.
Product-image endpoints retain their current flat success payload until their
dedicated migration. All catalog error responses use the structured BFF error
shape immediately.
