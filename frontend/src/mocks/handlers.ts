import { rest } from 'msw'

export const handlers = [
  rest.get('/api/v1/products/search', (req, res, ctx) => {
    return res(
      ctx.status(200),
      ctx.json({
        data: [
          {
            id: '1',
            name: 'Mocked Product',
            description: 'Mocked description',
            price: 10,
            category: 'Mocked category',
            user_id: 'user-1',
            is_active: true,
          },
        ],
        meta: {
          next_cursor: null,
          prev_cursor: null,
          has_more: false,
          has_prev: false,
        },
      }),
    )
  }),

  rest.post('/api/v1/auth/register', async (req, res, ctx) => {
    try {
      const body = await req.json();
      if (body.email === 'error422@example.com') {
        return res(
          ctx.status(422),
          ctx.json({
            error: {
              code: 'validation_error',
              message: 'Unprocessable Entity',
              details: [
                { field: 'email', issue: 'Email already exists' }
              ]
            }
          })
        );
      }
      return res(
        ctx.status(201),
        ctx.json({
          data: {
            id: 'user-new',
            role: 'user',
            email: body.email
          },
          meta: {}
        })
      );
    } catch {
      return res(ctx.status(400));
    }
  }),

  rest.post('/api/v1/auth/login', async (req, res, ctx) => {
    let email = '';
    let password = '';
    
    try {
      const contentType = req.headers.get('content-type') || '';
      if (contentType.includes('application/x-www-form-urlencoded')) {
        const text = await req.text();
        const params = new URLSearchParams(text);
        email = params.get('username') || '';
        password = params.get('password') || '';
      } else {
        const body = await req.json();
        email = body.email;
        password = body.password;
      }
    } catch {
      // Ignore
    }

    if (email === 'error400@example.com') {
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
    if (email === 'error422@example.com') {
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

    if (email && password) {
      return res(
        ctx.status(200),
        ctx.json({
          access_token: 'mock-access-token',
          token_type: 'bearer',
        }),
      );
    }

    return res(ctx.status(401));
  }),

  rest.get('/api/v1/users/me', (req, res, ctx) => {
    if (req.headers.get('authorization') !== 'Bearer mock-access-token') {
      return res(ctx.status(401));
    }

    return res(
      ctx.status(200),
      ctx.json({
        data: {
          id: 'user-123',
          role: 'user',
          email: 'user@example.com',
        },
        meta: {},
      }),
    );
  })
]
