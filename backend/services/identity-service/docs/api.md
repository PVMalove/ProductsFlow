# API

The service exposes RS256 JWKS at `/.well-known/jwks.json` and the identity
contract under `/api/v1`.

## Authentication

- `POST /auth/register` accepts `{email, password}` and returns the created
  user with `201`.
- `POST /auth/login` accepts OAuth2 form fields `username` (the email) and
  `password`, returning a bearer access token with a UUID aggregate id in
  `sub`.

## Users

`GET /users/me` and `PATCH /users/me/password` are available to the current
active user. Every bearer request reloads the account from Postgres, so
deactivation takes effect immediately for already-issued tokens.

Administrators can use:

- `GET /users/` for cursor pagination (`limit`, `after`, `before`);
- `PATCH /users/{user_id}/activate` and `/deactivate`;
- `GET /users/audit?page_index=&page_size=` for the global offset-paginated
  audit feed;
- `GET /users/{user_id}/audit` for a user's audit history.

The current user can read their own history at `GET /users/me/audit`. User
audit entries are immutable and are written by ORM listeners in the same
transaction as the user mutation.
