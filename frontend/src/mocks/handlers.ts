import { rest } from 'msw'

export const handlers = [
  rest.get('/api/v1/products', (req, res, ctx) => {
    return res(
      ctx.status(200),
      ctx.json([
        { id: '1', name: 'Mocked Product' }
      ])
    )
  })
]
