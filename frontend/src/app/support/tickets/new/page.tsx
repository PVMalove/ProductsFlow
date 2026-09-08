'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { isAxiosError } from 'axios';
import { createTicket } from '@/lib/api/tickets';
import { Button } from '@/components/ui/button';

interface TicketFormValues {
  subject: string;
  first_message: string;
}

export default function NewTicketPage() {
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<TicketFormValues>();

  const onSubmit = async (data: TicketFormValues) => {
    setError('');
    setSuccess(false);
    try {
      await createTicket(data.subject, data.first_message);
      setSuccess(true);
      reset();
    } catch (err) {
      if (isAxiosError(err)) {
        setError(err.response?.data?.message || 'Failed to create ticket');
      } else {
        setError(err instanceof Error ? err.message : 'An error occurred');
      }
    }
  };

  return (
    <div className="container mx-auto mt-8 max-w-2xl p-4">
      <h1 className="text-2xl font-bold mb-6">Create Support Ticket</h1>
      
      <div className="rounded-md border border-white/10 bg-[#282f37] p-6 shadow-xl shadow-black/10">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label htmlFor="subject" className="mb-1 block text-sm font-medium text-slate-200">
              Subject
            </label>
            <input
              id="subject"
              type="text"
              {...register('subject', { 
                required: 'Subject is required',
              })}
              className="w-full rounded-md border border-input bg-input/30 px-3 py-2 text-sm text-foreground outline-none focus:border-ring focus:ring-2 focus:ring-ring/50"
              placeholder="Brief summary of the issue"
            />
            {errors.subject && (
              <p className="mt-1 text-sm text-red-600">{errors.subject.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="first_message" className="mb-1 block text-sm font-medium text-slate-200">
              First Message
            </label>
            <textarea
              id="first_message"
              {...register('first_message', { 
                required: 'Message is required',
              })}
              rows={5}
              className="w-full rounded-md border border-input bg-input/30 px-3 py-2 text-sm text-foreground outline-none focus:border-ring focus:ring-2 focus:ring-ring/50"
              placeholder="Describe your problem in detail"
            />
            {errors.first_message && (
              <p className="mt-1 text-sm text-red-600">{errors.first_message.message}</p>
            )}
          </div>

          {error && (
            <div className="rounded-md bg-red-500/10 p-3 text-red-300">
              {error}
            </div>
          )}

          {success && (
            <div className="rounded-md bg-emerald-400/10 p-3 text-emerald-300">
              Ticket submitted successfully.
            </div>
          )}

          <div className="mt-6 flex justify-end gap-3 border-t border-white/10 pt-4">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Submitting...' : 'Submit Ticket'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
