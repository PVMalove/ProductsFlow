import { rest } from 'msw'

export const handlers = [
  rest.get('/api/v1/products', (req, res, ctx) => {
    return res(
      ctx.status(200),
      ctx.json([
        { id: '1', name: 'Mocked Product' }
      ])
    )
  }),

  rest.post('/api/v1/auth/login', async (req, res, ctx) => {
    const body = await req.json();
    if (body.email === 'error400@example.com') {
      return res(
        ctx.status(400),
        ctx.json({
          error: {
            code: 'general_multiple_validation_errors',
            message: 'Multiple validation errors occurred',
            details: [
              { field: 'email', issue: 'Email must be from a supported domain' }
            ]
          }
        })
      );
    }
    if (body.email === 'error422@example.com') {
      return res(
        ctx.status(422),
        ctx.json({
          error: {
            code: 'validation_error',
            message: 'Unprocessable Entity',
            details: [
              { field: 'password', issue: 'Password is too short' }
            ]
          }
        })
      );
    }

    if (body.email && body.password) {
      return res(
        ctx.status(200),
        ctx.cookie('accessToken', 'mock-access-token', { httpOnly: true }),
        ctx.cookie('refreshToken', 'mock-refresh-token', { httpOnly: true }),
        ctx.json({
          message: 'Success'
        })
      );
    }

    return res(ctx.status(401));
  }),

  rest.get('/api/v1/users/me', (req, res, ctx) => {
    // If the request doesn't have the mock access token, return 401
    // (MSW mock tokens are sent in requests just like real cookies in browser)
    const token = req.cookies.accessToken;
    if (token !== 'mock-access-token') {
      return res(ctx.status(401));
    }

    return res(
      ctx.status(200),
      ctx.json({
        id: 'user-123',
        role: 'USER',
        email: 'user@example.com'
      })
    );
  }),

  rest.post('/api/v1/auth/logout', (req, res, ctx) => {
    return res(
      ctx.status(200),
      ctx.cookie('accessToken', '', { httpOnly: true, expires: new Date(0) }),
      ctx.cookie('refreshToken', '', { httpOnly: true, expires: new Date(0) }),
      ctx.json({
        message: 'Logged out successfully'
      })
    );
  })
]
