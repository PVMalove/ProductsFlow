'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { authApi, RegisterRequest } from '@/lib/api/auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import Link from 'next/link';

import { useApiError } from '@/hooks/useApiError';

export default function RegisterPage() {
  const router = useRouter();
  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } = useForm<RegisterRequest>();
  const { globalError, handleApiError, clearGlobalError } = useApiError<RegisterRequest>();
  const [success, setSuccess] = useState(false);

  const onSubmit = async (data: RegisterRequest) => {
    clearGlobalError();
    setSuccess(false);
    try {
      await authApi.register(data);
      setSuccess(true);
      setTimeout(() => {
        router.push('/login');
      }, 2000);
    } catch (err: unknown) {
      handleApiError(err, setError, 'Registration failed');
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-5">
      <Card className="w-full max-w-md border border-white/10 shadow-2xl shadow-black/20">
        <CardHeader>
          <CardTitle className="text-2xl text-center">Register</CardTitle>
          <CardDescription className="text-center">Create a new account</CardDescription>
        </CardHeader>
        <CardContent>
          {success ? (
            <div className="rounded-md bg-emerald-400/10 p-4 text-center text-emerald-300">
              Registration successful! Redirecting to login...
            </div>
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              {globalError && (
                <div className="rounded-md bg-red-500/10 p-3 text-sm text-red-300">
                  {globalError}
                </div>
              )}
              
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="name@example.com"
                  {...register('email', { required: 'Email is required' })}
                />
                {errors.email && <p className="text-sm text-red-500">{errors.email.message}</p>}
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  {...register('password', { required: 'Password is required', minLength: { value: 8, message: 'Password must be at least 8 characters' } })}
                />
                {errors.password && <p className="text-sm text-red-500">{errors.password.message}</p>}
              </div>

              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting ? 'Registering...' : 'Register'}
              </Button>
            </form>
          )}
        </CardContent>
        <CardFooter className="flex justify-center">
          <p className="text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link href="/login" className="text-blue-400 hover:underline">
              Log in
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  );
}
