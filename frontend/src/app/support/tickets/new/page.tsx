'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { isAxiosError } from 'axios';
import { createTicket } from '@/lib/api/tickets';
import { Button } from '@/components/ui/button';

interface TicketFormValues {
  subject: string;
  first_message: string;
}

export default function NewTicketPage() {
  const router = useRouter();
  const [error, setError] = useState('');
  
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<TicketFormValues>();

  const onSubmit = async (data: TicketFormValues) => {
    setError('');
    try {
      const ticket = await createTicket(data.subject, data.first_message);
      // Wait, what should happen after creation?
      // Redirect to the ticket details or dashboard.
      // For now, maybe just redirect to a success state or ticket list.
      router.push(`/support/tickets/${ticket.id}`);
    } catch (err) {
      if (isAxiosError(err)) {
        setError(err.response?.data?.message || 'Failed to create ticket');
      } else {
        setError(err instanceof Error ? err.message : 'An error occurred');
      }
    }
  };

  return (
    <div className="container mx-auto p-4 max-w-2xl mt-8">
      <h1 className="text-2xl font-bold mb-6">Create Support Ticket</h1>
      
      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label htmlFor="subject" className="block text-sm font-medium text-gray-700 mb-1">
              Subject
            </label>
            <input
              id="subject"
              type="text"
              {...register('subject', { 
                required: 'Subject is required',
                minLength: { value: 1, message: 'Subject must not be empty' },
                maxLength: { value: 200, message: 'Subject cannot exceed 200 characters' }
              })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Brief summary of the issue"
            />
            {errors.subject && (
              <p className="mt-1 text-sm text-red-600">{errors.subject.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="first_message" className="block text-sm font-medium text-gray-700 mb-1">
              First Message
            </label>
            <textarea
              id="first_message"
              {...register('first_message', { 
                required: 'Message is required',
                minLength: { value: 1, message: 'Message must not be empty' },
                maxLength: { value: 10000, message: 'Message is too long' }
              })}
              rows={5}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Describe your problem in detail"
            />
            {errors.first_message && (
              <p className="mt-1 text-sm text-red-600">{errors.first_message.message}</p>
            )}
          </div>

          {error && (
            <div className="p-3 bg-red-50 text-red-700 rounded-md">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100 mt-6">
            <Button 
              type="button" 
              variant="outline" 
              onClick={() => router.back()}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Submitting...' : 'Submit Ticket'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
