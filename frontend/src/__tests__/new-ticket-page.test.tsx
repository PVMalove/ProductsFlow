import '@testing-library/jest-dom'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import NewTicketPage from '../app/support/tickets/new/page'
import { rest } from 'msw'
import { setupServer } from 'msw/node'

const server = setupServer(
  rest.post('*/v1/tickets', (req, res, ctx) => {
    return res(
      ctx.status(201),
      ctx.json({
        data: {
          id: '123e4567-e89b-12d3-a456-426614174000',
          subject: 'Test Subject',
          status: 'open',
          created_at: '2026-09-06T12:00:00Z',
          messages: [
            {
              id: 'msg-1',
              body: 'Test Message',
              created_at: '2026-09-06T12:00:00Z',
              is_system: false,
              is_deleted: false,
              author_id: 'user-1'
            }
          ]
        },
        meta: {
          next_cursor: null,
          prev_cursor: null,
          has_more: false,
          has_prev: false
        }
      })
    )
  })
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

jest.mock('next/navigation', () => ({
  useRouter() {
    return {
      push: jest.fn(),
      back: jest.fn(),
    };
  },
}));

describe('NewTicketPage', () => {
  it('renders form and submits ticket', async () => {
    render(<NewTicketPage />)
    
    expect(screen.getByText('Create Support Ticket')).toBeInTheDocument()

    const subjectInput = screen.getByLabelText(/Subject/i)
    const messageInput = screen.getByLabelText(/First Message/i)
    const submitBtn = screen.getByRole('button', { name: /Submit Ticket/i })

    fireEvent.change(subjectInput, { target: { value: 'Test Subject' } })
    fireEvent.change(messageInput, { target: { value: 'Test Message' } })
    
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(submitBtn).toBeDisabled()
    })
    
    // Test successfully passes if it completes
    expect(true).toBe(true)
  })
})
