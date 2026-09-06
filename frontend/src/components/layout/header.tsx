'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/lib/store';
import { authApi } from '@/lib/api/auth';

export function Header() {
  const { actor, clearAuth } = useAuthStore();
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch (error) {
      console.error('Logout failed:', error);
    } finally {
      clearAuth();
      router.push('/login');
    }
  };

  return (
    <header className="border-b bg-slate-900 border-slate-800">
      <div className="container mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link href="/" className="text-xl font-bold text-white">
            ProductsFlow
          </Link>

          <nav className="flex items-center gap-4">
            {actor ? (
              <>
                <Link href="/owner" className="text-sm text-slate-300 hover:text-white transition-colors">
                  Мои товары
                </Link>
                <Link href="/" className="text-sm text-slate-300 hover:text-white transition-colors">
                  Поиск
                </Link>
                <Link href="/support" className="text-sm text-slate-300 hover:text-white transition-colors">
                  Поддержка
                </Link>
                {actor.role === 'admin' && (
                  <Link href="/admin" className="text-sm font-semibold text-slate-100 hover:text-white transition-colors">
                    Админка
                  </Link>
                )}
              </>
            ) : null}
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {actor ? (
            <div className="flex items-center gap-4">
              <span className="text-sm text-slate-400">{actor.email}</span>
              <Button variant="destructive" size="sm" onClick={handleLogout}>
                Выйти
              </Button>
            </div>
          ) : (
            <>
              <Link href="/login">
                <Button variant="ghost" className="text-slate-300 hover:text-white">
                  Вход
                </Button>
              </Link>
              <Link href="/register">
                <Button variant="default">Регистрация</Button>
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
