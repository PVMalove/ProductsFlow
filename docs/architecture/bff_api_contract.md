# BFF API response contract

This document defines the response contract adopted incrementally by
ProductsFlow services. It is a breaking change for migrated endpoints; clients
must read the payload from `data` rather than from the response root.

## Successful responses

Every migrated endpoint returns an object with both keys:

```json
{
  "data": {},
  "meta": {}
}
```

`data` is the endpoint payload and may be `null` for a successful delete.
`meta` is always an object; it is `{}` when no metadata is available. Future
query migrations use it for pagination and other auxiliary response data.

## Error responses

All service errors use this shape:

```json
{
  "error": {
    "code": "STRING_CODE",
    "message": "Human-readable message"
  }
}
```

`code` is stable, machine-readable control data. `message` is only a
human-readable explanation and must not contain technical details. Business
failures use specific codes such as `PRODUCT_NOT_FOUND`,
`PRODUCT_ACCESS_DENIED`, and `IDENTITY_UNAVAILABLE`. Framework failures use
canonical codes such as `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`,
`VALIDATION_ERROR`, and `INTERNAL_ERROR`.

Unknown failures are logged server-side and return HTTP 500 with
`INTERNAL_ERROR`; no stack trace or implementation detail reaches clients.

## Rollout

The first rollout applies the success envelope to catalog product commands only.
Catalog query and image success responses remain flat until their own migrations,
while error responses use the structured shape across the service from the first
rollout. New service migrations should follow the same staged approach and cite
ADR 0031.
