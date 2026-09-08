'use client';

import { useState } from 'react';
import { isAxiosError } from 'axios';
import { getProduct, ProductView } from '@/lib/api/products';
import { Button } from '@/components/ui/button';
import { ProductEditForm } from '@/components/catalog/product-edit-form';

export default function OwnerDashboard() {
  const [productId, setProductId] = useState('');
  const [product, setProduct] = useState<ProductView | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!productId) return;
    
    setLoading(true);
    setError('');
    setProduct(null);
    
    try {
      const data = await getProduct(productId);
      setProduct(data);
    } catch (err) {
      if (isAxiosError(err)) {
        setError(err.response?.data?.message || 'Product not found or access denied');
      } else {
        setError(err instanceof Error ? err.message : 'Product not found or access denied');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container mx-auto mt-8 max-w-2xl p-4">
      <h1 className="mb-6 text-2xl font-bold">Мои товары</h1>
      
      <div className="rounded-md border border-white/10 bg-[#282f37] p-6 shadow-xl shadow-black/10">
        <h2 className="text-lg font-semibold mb-4">Direct ID Lookup</h2>
        <p className="mb-4 text-sm text-slate-400">
          Lookup a product by its ID. Deactivated products are accessible.
        </p>
        
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            placeholder="Enter Product UUID"
            className="flex-1 rounded-md border border-input bg-input/30 px-3 py-2 text-sm text-foreground outline-none focus:border-ring focus:ring-2 focus:ring-ring/50"
            required
          />
          <Button type="submit" disabled={loading}>
            {loading ? 'Searching...' : 'Search'}
          </Button>
        </form>

        {error && (
          <div className="mt-4 rounded-md bg-red-500/10 p-3 text-red-300">
            {error}
          </div>
        )}

        {product && (
          <ProductEditForm product={product} onUpdate={(updated) => setProduct(updated)} />
        )}
      </div>
    </div>
  );
}

