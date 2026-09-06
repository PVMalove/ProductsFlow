import '@testing-library/jest-dom'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import NewTicketPage from '../app/support/tickets/new/page'

jest.mock('@/lib/api/tickets', () => ({
  createTicket: jest.fn().mockResolvedValue({ id: '123e4567-e89b-12d3-a456-426614174000' })
}))

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
      expect(screen.getByText('Ticket submitted successfully.')).toBeInTheDocument()
    })
  })
})
