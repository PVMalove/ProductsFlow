'use client';

import { useAuthStore } from '@/lib/store';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { actor } = useAuthStore();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted && actor?.role !== 'admin') {
      router.replace('/');
    }
  }, [actor, mounted, router]);

  if (!mounted || actor?.role !== 'admin') {
    return null; // or a loading spinner
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="font-bold text-lg text-gray-800">Admin Portal</div>
          <div className="text-sm text-gray-500">{actor.email}</div>
        </div>
      </nav>
      <main>
        {children}
      </main>
    </div>
  );
}
