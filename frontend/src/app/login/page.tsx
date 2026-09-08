'use client';

import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { authApi, RegisterRequest } from '@/lib/api/auth';
import { useAuthStore } from '@/lib/store';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import Link from 'next/link';

import { useApiError } from '@/hooks/useApiError';

export default function LoginPage() {
  const router = useRouter();
  const setActor = useAuthStore((state) => state.setActor);
  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } = useForm<RegisterRequest>();
  const { globalError, handleApiError, clearGlobalError } = useApiError<RegisterRequest>();

  const onSubmit = async (data: RegisterRequest) => {
    clearGlobalError();
    try {
      await authApi.login(data);
      // Fetch user profile on success
      const user = await authApi.getMe();
      setActor(user);
      router.push('/');
    } catch (err: unknown) {
      handleApiError(err, setError, 'Login failed');
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-5">
      <Card className="w-full max-w-md border border-white/10 shadow-2xl shadow-black/20">
        <CardHeader>
          <CardTitle className="text-2xl text-center">Login</CardTitle>
          <CardDescription className="text-center">Enter your credentials to access your account</CardDescription>
        </CardHeader>
        <CardContent>
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
                {...register('password', { required: 'Password is required' })}
              />
              {errors.password && <p className="text-sm text-red-500">{errors.password.message}</p>}
            </div>

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? 'Logging in...' : 'Log in'}
            </Button>
          </form>
        </CardContent>
        <CardFooter className="flex justify-center">
          <p className="text-sm text-muted-foreground">
            Don&apos;t have an account?{' '}
            <Link href="/register" className="text-blue-400 hover:underline">
              Register
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  );
}
