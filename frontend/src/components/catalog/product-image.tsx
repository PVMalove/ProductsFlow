'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';

import { getProductImage } from '@/lib/api/products';

export const PRODUCT_IMAGE_FALLBACK = '/product-placeholder.svg';

export function toGatewayMediaPath(imageUrl: string): string {
  const url = new URL(imageUrl, 'http://gateway.local');
  if (url.pathname.startsWith('/media/')) {
    return `${url.pathname}${url.search}`;
  }
  return `/media${url.pathname}${url.search}`;
}

interface ProductImageProps {
  productId: string;
  alt: string;
  className?: string;
  // Catalog list/search already inline this (attach_image_urls on the
  // backend) — pass it to skip the per-card `GET /products/{id}/image`
  // fetch entirely. Omit the prop (not just `null`) to fall back to that
  // fetch, e.g. on the product detail page where it isn't preloaded.
  imageUrl?: string | null;
}

export function ProductImage({ productId, alt, className, imageUrl }: ProductImageProps) {
  const preloaded = imageUrl !== undefined;
  const [fetchedSrc, setFetchedSrc] = useState(PRODUCT_IMAGE_FALLBACK);
  const [failedImageSrc, setFailedImageSrc] = useState<string | null>(null);

  useEffect(() => {
    if (preloaded) return;

    let isCurrent = true;

    void getProductImage(productId)
      .then((image) => {
        if (isCurrent && image?.image_url) {
          setFetchedSrc(toGatewayMediaPath(image.image_url));
        }
      })
      .catch(() => {
        if (isCurrent) {
          setFetchedSrc(PRODUCT_IMAGE_FALLBACK);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [productId, preloaded]);

  const resolvedImageSrc = preloaded
    ? imageUrl
      ? toGatewayMediaPath(imageUrl)
      : PRODUCT_IMAGE_FALLBACK
    : fetchedSrc;
  const imageSrc =
    failedImageSrc === resolvedImageSrc
      ? PRODUCT_IMAGE_FALLBACK
      : resolvedImageSrc;

  return (
    <Image
      src={imageSrc}
      alt={alt}
      width={640}
      height={480}
      unoptimized
      className={className}
      onError={() => setFailedImageSrc(resolvedImageSrc)}
    />
  );
}
