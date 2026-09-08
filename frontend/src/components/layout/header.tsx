'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { AuthDialog } from '@/components/auth/auth-dialog';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/lib/store';
import { authApi } from '@/lib/api/auth';

export function Header() {
  const { actor, isLoading, clearAuth } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();

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
    <header className="border-b border-white/10 bg-[#20262e]/95 backdrop-blur">
      <div className="mx-auto flex h-12 max-w-6xl items-center justify-between px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-5">
          <Link href="/" className="text-sm font-bold tracking-tight text-white sm:text-base">
            ProductsFlow
          </Link>

          <nav className="hidden items-center gap-4 sm:flex">
            {actor ? (
              <>
                <Link href="/owner/dashboard" className="text-xs text-slate-400 hover:text-white transition-colors">
                  Мои товары
                </Link>
                <Link href="/catalog" className="text-xs text-slate-400 hover:text-white transition-colors">
                  Поиск
                </Link>
                <Link href="/support/tickets/new" className="text-xs text-slate-400 hover:text-white transition-colors">
                  Поддержка
                </Link>
                {actor.role === 'admin' && (
                  <Link href="/admin/audit-log" className="text-xs font-semibold text-slate-200 hover:text-white transition-colors">
                    Админка
                  </Link>
                )}
              </>
            ) : null}
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          {isLoading ? null : actor ? (
            <div className="flex items-center gap-4">
              <span className="hidden text-xs text-slate-400 md:inline">{actor.email}</span>
              <Button variant="outline" size="sm" className="border-slate-600 text-slate-300 hover:border-slate-400 hover:bg-slate-800 hover:text-white" onClick={handleLogout}>
                Выйти
              </Button>
            </div>
          ) : (
            <>
              {pathname === '/' ? (
                <AuthDialog />
              ) : (
                <Link href="/login">
                  <Button variant="ghost" size="sm" className="text-slate-300 hover:text-white">
                    Вход
                  </Button>
                </Link>
              )}
              <Link href="/register">
                <Button size="sm">Регистрация</Button>
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
