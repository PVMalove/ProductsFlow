# Architecture

`presentation` owns HTTP entrypoints and schemas, `application` is reserved
for use cases and ports, `domain` owns product rules, `infrastructure` owns
persistence and external adapters, and `core` owns service-local policy.
