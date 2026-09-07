'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';

import { getProductImage } from '@/lib/api/products';

export const PRODUCT_IMAGE_FALLBACK = '/product-placeholder.svg';

function toGatewayMediaPath(imageUrl: string): string {
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
}

export function ProductImage({ productId, alt, className }: ProductImageProps) {
  const [imageSrc, setImageSrc] = useState(PRODUCT_IMAGE_FALLBACK);

  useEffect(() => {
    let isCurrent = true;

    void getProductImage(productId)
      .then((image) => {
        if (isCurrent && image?.image_url) {
          setImageSrc(toGatewayMediaPath(image.image_url));
        }
      })
      .catch(() => {
        if (isCurrent) {
          setImageSrc(PRODUCT_IMAGE_FALLBACK);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [productId]);

  return (
    <Image
      src={imageSrc}
      alt={alt}
      width={640}
      height={480}
      unoptimized
      className={className}
      onError={() => setImageSrc(PRODUCT_IMAGE_FALLBACK)}
    />
  );
}
