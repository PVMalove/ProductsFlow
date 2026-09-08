import Link from 'next/link';

import { Button } from '@/components/ui/button';
import type { ProductView } from '@/lib/api/products';
import { ProductImage } from '@/components/catalog/product-image';

interface ProductCardProps {
  product: ProductView;
  canEdit: boolean;
}

export function ProductCard({ product, canEdit }: ProductCardProps) {
  return (
    <article className="group flex flex-col overflow-hidden rounded-md border border-white/10 bg-[#282f37] transition hover:-translate-y-0.5 hover:border-blue-400/50 hover:shadow-xl hover:shadow-black/15">
      <Link href={`/catalog/${product.id}`} className="block w-full">
        <div className="aspect-[16/9] overflow-hidden bg-slate-800">
          <ProductImage
            productId={product.id}
            alt={product.name}
            imageUrl={product.image_url}
            className="size-full object-cover transition duration-500 group-hover:scale-[1.03]"
          />
        </div>
      </Link>
      <div className="flex min-w-0 flex-1 flex-col p-3">
        <div className="flex items-start justify-between gap-2">
          <h2 className="line-clamp-2 text-sm font-semibold leading-5 text-slate-100">
            <Link href={`/catalog/${product.id}`} className="transition hover:text-blue-300">
              {product.name}
            </Link>
          </h2>
          <span className="shrink-0 rounded-sm bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold text-slate-700">
            {product.category}
          </span>
        </div>
        <p className="mt-1.5 line-clamp-2 flex-grow text-xs leading-4 text-slate-400">
          {product.description}
        </p>
        <span className="mt-3 text-sm font-bold text-slate-100">${product.price.toFixed(2)}</span>
        {canEdit && (
          <div className="mt-3 flex gap-2 border-t border-white/10 pt-2">
            <Button variant="outline" size="sm" className="flex-1 text-xs">
              Редактировать
            </Button>
            <Button variant="destructive" size="sm" className="flex-1 text-xs">
              Удалить
            </Button>
          </div>
        )}
      </div>
    </article>
  );
}
