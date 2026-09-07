'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { ProductImage } from '@/components/catalog/product-image';
import { getProduct } from '@/lib/api/products';
import type { ProductView } from '@/lib/api/products';

function isNotFoundResponse(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'response' in error &&
    typeof error.response === 'object' &&
    error.response !== null &&
    'status' in error.response &&
    error.response.status === 404
  );
}

function ProductUnavailable() {
  return (
    <section className="mx-auto max-w-2xl p-8 text-center">
      <h1 className="text-2xl font-semibold">
        Товар не существует или снят с публикации
      </h1>
      <Link
        href="/catalog"
        className="mt-6 inline-block text-sm text-blue-600 underline underline-offset-4 hover:text-blue-800 dark:text-blue-400"
      >
        Вернуться в каталог
      </Link>
    </section>
  );
}

interface ProductLoadResult {
  id: string;
  product: ProductView | null;
}

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [result, setResult] = useState<ProductLoadResult | null>(null);

  useEffect(() => {
    let isCurrent = true;

    void getProduct(id)
      .then((product) => {
        if (isCurrent) {
          setResult({ id, product });
        }
      })
      .catch((error: unknown) => {
        if (isCurrent && isNotFoundResponse(error)) {
          setResult({ id, product: null });
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [id]);

  if (result?.id !== id) {
    return (
      <div role="status" className="p-8 text-center text-muted-foreground">
        Загрузка товара...
      </div>
    );
  }

  if (result.product === null) {
    return <ProductUnavailable />;
  }

  const product = result.product;
  return (
    <article className="mx-auto grid max-w-4xl gap-8 p-4 md:grid-cols-2 md:p-8">
      <ProductImage
        key={product.id}
        productId={product.id}
        alt={product.name}
        className="aspect-square w-full rounded-lg border bg-muted object-cover"
      />
      <div className="flex flex-col gap-4">
        <Link
          href="/catalog"
          className="text-sm text-blue-600 underline underline-offset-4 hover:text-blue-800 dark:text-blue-400"
        >
          Вернуться в каталог
        </Link>
        <p className="text-sm text-muted-foreground">{product.category}</p>
        <h1 className="text-3xl font-bold tracking-tight">{product.name}</h1>
        <p className="text-lg text-muted-foreground">{product.description}</p>
        <p className="text-2xl font-semibold">${product.price.toFixed(2)}</p>
      </div>
    </article>
  );
}
