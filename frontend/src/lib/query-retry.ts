import { FetchResponseError } from './api/fetch-response-error';

const MAX_QUERY_RETRIES = 3;

export function shouldRetryQuery(failureCount: number, error: Error): boolean {
  if (
    error instanceof FetchResponseError
    && error.status >= 400
    && error.status < 500
  ) {
    return false;
  }

  return failureCount < MAX_QUERY_RETRIES;
}

