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
    <div className="container mx-auto p-4 max-w-2xl mt-8">
      <h1 className="text-2xl font-bold mb-6">Owner Dashboard</h1>
      
      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <h2 className="text-lg font-semibold mb-4">Direct ID Lookup</h2>
        <p className="text-sm text-gray-500 mb-4">
          Lookup a product by its ID. Deactivated products are accessible.
        </p>
        
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            placeholder="Enter Product UUID"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
          <Button type="submit" disabled={loading}>
            {loading ? 'Searching...' : 'Search'}
          </Button>
        </form>

        {error && (
          <div className="mt-4 p-3 bg-red-50 text-red-700 rounded-md">
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

