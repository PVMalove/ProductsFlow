# Architecture

`presentation` owns HTTP and worker entrypoints, `application` owns use cases,
`domain` owns identity business concepts, `infrastructure` owns persistence,
and `core` owns service-local security and configuration policy.
