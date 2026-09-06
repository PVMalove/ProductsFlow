const { TextDecoder, TextEncoder } = require('node:util')
const { ReadableStream, TransformStream } = require('node:stream/web')
const { MessageChannel, MessagePort } = require('node:worker_threads')

Object.defineProperties(global, {
  TextDecoder: { value: TextDecoder },
  TextEncoder: { value: TextEncoder },
  ReadableStream: { value: ReadableStream },
  TransformStream: { value: TransformStream },
  MessageChannel: { value: MessageChannel },
  MessagePort: { value: MessagePort },
})

const { Blob, File } = require('node:buffer')
const { fetch, Headers, Request, Response, FormData } = require('undici')

Object.defineProperties(global, {
  fetch: { value: fetch, writable: true },
  Blob: { value: Blob },
  File: { value: File },
  Headers: { value: Headers },
  Request: { value: Request },
  Response: { value: Response },
  FormData: { value: FormData },
})
