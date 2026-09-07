'use client';

import { useState } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { useForm } from 'react-hook-form';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useApiError } from '@/hooks/useApiError';
import { authApi, type RegisterRequest } from '@/lib/api/auth';
import { useAuthStore } from '@/lib/store';

export function AuthDialog() {
  const [open, setOpen] = useState(false);
  const setActor = useAuthStore((state) => state.setActor);
  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } =
    useForm<RegisterRequest>();
  const { globalError, clearGlobalError, handleApiError } = useApiError<RegisterRequest>();

  const onSubmit = async (data: RegisterRequest) => {
    clearGlobalError();

    try {
      await authApi.login(data);
      setActor(await authApi.getMe());
      setOpen(false);
    } catch (error: unknown) {
      handleApiError(error, setError, 'Не удалось войти');
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger
        render={
          <Button variant="ghost" className="text-slate-300 hover:text-white">
            Вход
          </Button>
        }
      />
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Popup className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl bg-card p-6 text-card-foreground shadow-xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-xl font-semibold">Вход</Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                Введите данные учётной записи.
              </Dialog.Description>
            </div>
            <Dialog.Close
              aria-label="Закрыть"
              render={<Button variant="ghost" size="sm">Закрыть</Button>}
            />
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4">
            {globalError ? (
              <div className="rounded-md bg-red-50 p-3 text-sm text-red-500">
                {globalError}
              </div>
            ) : null}

            <div className="space-y-2">
              <Label htmlFor="auth-dialog-email">Email</Label>
              <Input
                id="auth-dialog-email"
                type="email"
                autoComplete="email"
                placeholder="name@example.com"
                {...register('email', { required: 'Email is required' })}
              />
              {errors.email ? <p className="text-sm text-red-500">{errors.email.message}</p> : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="auth-dialog-password">Пароль</Label>
              <Input
                id="auth-dialog-password"
                type="password"
                autoComplete="current-password"
                {...register('password', { required: 'Password is required' })}
              />
              {errors.password ? <p className="text-sm text-red-500">{errors.password.message}</p> : null}
            </div>

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? 'Входим...' : 'Войти'}
            </Button>
          </form>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
