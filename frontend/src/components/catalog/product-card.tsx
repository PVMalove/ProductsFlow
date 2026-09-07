import Link from 'next/link';

import { Button } from '@/components/ui/button';
import type { ProductView } from '@/lib/api/products';

interface ProductCardProps {
  product: ProductView;
  canEdit: boolean;
}

export function ProductCard({ product, canEdit }: ProductCardProps) {
  return (
    <article className="flex flex-col gap-2 rounded-lg border bg-white p-4 shadow-sm dark:bg-zinc-900">
      <h2 className="text-lg font-semibold">
        <Link href={`/catalog/${product.id}`} className="hover:underline">
          {product.name}
        </Link>
      </h2>
      <p className="line-clamp-2 flex-grow text-sm text-gray-500">
        {product.description}
      </p>
      <div className="mt-2 flex items-center justify-between">
        <span className="font-bold">${product.price.toFixed(2)}</span>
        <span className="rounded-full bg-gray-100 px-2 py-1 text-xs dark:bg-zinc-800">
          {product.category}
        </span>
      </div>
      {canEdit && (
        <div className="mt-2 flex gap-2 border-t border-gray-100 pt-2 dark:border-zinc-800">
          <Button variant="outline" size="sm" className="flex-1">
            Редактировать
          </Button>
          <Button variant="destructive" size="sm" className="flex-1">
            Удалить
          </Button>
        </div>
      )}
    </article>
  );
}
