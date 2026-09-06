'use client';

import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import Image from 'next/image';
import { ProductView, patchProduct, uploadProductImage, getProductImage } from '@/lib/api/products';
import { Button } from '@/components/ui/button';

interface ProductEditFormProps {
  product: ProductView;
  onUpdate: (updatedProduct: ProductView) => void;
}

export function ProductEditForm({ product, onUpdate }: ProductEditFormProps) {
  const { register, handleSubmit, formState: { dirtyFields, isSubmitting }, reset } = useForm<ProductView>({
    defaultValues: product
  });
  
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [imageError, setImageError] = useState('');
  
  // Reset form when product changes
  useEffect(() => {
    reset(product);
  }, [product, reset]);

  useEffect(() => {
    // Try to load existing image
    const fetchImage = async () => {
      try {
        const res = await getProductImage(product.id);
        if (res?.image_url) {
          setImageUrl(res.image_url);
        }
      } catch (err) {
        // Image might not exist, which is fine
        console.log('No image found or failed to load image', err);
      }
    };
    fetchImage();
  }, [product.id]);

  const onSubmit = async (data: ProductView) => {
    try {
      setError('');
      setSuccess('');
      
      const patchPayload: Partial<ProductView> = {};
      let hasChanges = false;
      
      (Object.keys(dirtyFields) as (keyof ProductView)[]).forEach((key) => {
        // @ts-expect-error dynamic key assignment
        patchPayload[key] = data[key];
        hasChanges = true;
      });
      
      if (!hasChanges) {
        setSuccess('No changes to save.');
        return;
      }
      
      const updated = await patchProduct(product.id, patchPayload);
      onUpdate(updated);
      setSuccess('Product updated successfully!');
      reset(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update product');
    }
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    try {
      setUploadingImage(true);
      setImageError('');
      const res = await uploadProductImage(product.id, file);
      setImageUrl(res.image_url);
    } catch (err) {
      setImageError(err instanceof Error ? err.message : 'Failed to upload image');
    } finally {
      setUploadingImage(false);
    }
  };

  return (
    <div className="mt-6 border-t pt-4">
      <h3 className="font-semibold text-lg mb-4">Edit Product</h3>
      
      {/* Image Upload Section */}
      <div className="mb-6 border rounded-md p-4 bg-gray-50">
        <h4 className="font-medium mb-2">Product Image</h4>
        
        {uploadingImage ? (
          <div className="w-48 h-48 bg-gray-200 animate-pulse rounded-md flex items-center justify-center mb-4">
            <span className="text-gray-400">Uploading...</span>
          </div>
        ) : imageUrl ? (
          <div className="relative w-48 h-48 mb-4 border rounded-md overflow-hidden">
            <Image src={imageUrl} alt={product.name} fill className="object-cover" unoptimized />
          </div>
        ) : (
          <div className="w-48 h-48 bg-gray-100 rounded-md flex items-center justify-center mb-4 border border-dashed border-gray-300">
            <span className="text-gray-400">No image</span>
          </div>
        )}
        
        <input 
          type="file" 
          accept="image/jpeg, image/png, image/webp"
          onChange={handleImageUpload}
          className="block w-full text-sm text-gray-500
            file:mr-4 file:py-2 file:px-4
            file:rounded-md file:border-0
            file:text-sm file:font-semibold
            file:bg-blue-50 file:text-blue-700
            hover:file:bg-blue-100"
          disabled={uploadingImage}
        />
        {imageError && <p className="text-red-500 text-sm mt-2">{imageError}</p>}
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
          <input 
            {...register('name')} 
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" 
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
          <textarea 
            {...register('description')} 
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            rows={3}
          />
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Price</label>
            <input 
              type="number" 
              step="0.01" 
              {...register('price', { valueAsNumber: true })} 
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" 
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
            <input 
              {...register('category')} 
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" 
            />
          </div>
        </div>

        <div className="flex items-center">
          <input 
            type="checkbox" 
            id="is_active"
            {...register('is_active')} 
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded" 
          />
          <label htmlFor="is_active" className="ml-2 block text-sm text-gray-900">
            Active Status
          </label>
        </div>

        {error && <div className="p-3 bg-red-50 text-red-700 rounded-md">{error}</div>}
        {success && <div className="p-3 bg-green-50 text-green-700 rounded-md">{success}</div>}
        
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Saving...' : 'Save Changes'}
        </Button>
      </form>
    </div>
  );
}
