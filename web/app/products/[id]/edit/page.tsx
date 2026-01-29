'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import ImageUpload from '@/components/ImageUpload';
import { getProduct, updateProduct, getOptionalExtras } from '@/lib/api';
import { ProductCategory, Product } from '@/lib/types';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';

export default function EditProductPage() {
  const router = useRouter();
  const params = useParams();
  const productId = parseInt(params.id as string);

  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [optionalExtras, setOptionalExtras] = useState<Product[]>([]);
  const [selectedExtras, setSelectedExtras] = useState<number[]>([]);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    category: ProductCategory.STABLES,
    subcategory: '',
    is_extra: false,
    base_price: '',
    unit: 'unit',
    sku: '',
    image_url: '',
    specifications: '',
    installation_hours: '',
  });

  useEffect(() => {
    if (productId) {
      fetchProduct();
      fetchOptionalExtras();
    }
  }, [productId]);

  const fetchProduct = async () => {
    try {
      setPageLoading(true);
      const product = await getProduct(productId);
      setFormData({
        name: product.name,
        description: product.description || '',
        category: product.category,
        subcategory: product.subcategory || '',
        is_extra: product.is_extra,
        base_price: product.base_price.toString(),
        unit: product.unit,
        sku: product.sku || '',
        image_url: product.image_url || '',
        specifications: product.specifications || '',
        installation_hours: product.installation_hours?.toString() || '',
      });
      if (product.optional_extras) {
        setSelectedExtras(product.optional_extras.map((e: Product) => e.id));
      }
    } catch (error: any) {
      if (error.response?.status === 404) {
        toast.error('Product not found');
        router.push('/products');
      } else {
        toast.error('Failed to load product');
      }
    } finally {
      setPageLoading(false);
    }
  };

  const fetchOptionalExtras = async () => {
    try {
      const extras = await getOptionalExtras();
      setOptionalExtras(extras);
    } catch (error) {
      console.error('Failed to load optional extras');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.name.trim() || !formData.base_price) {
      toast.error('Name and base price are required');
      return;
    }

    setLoading(true);
    try {
      const productData: Parameters<typeof updateProduct>[1] = {
        ...formData,
        base_price: parseFloat(formData.base_price),
        installation_hours: formData.installation_hours
          ? parseFloat(formData.installation_hours)
          : undefined,
        description: formData.description.trim() || undefined,
        subcategory: formData.subcategory.trim() || undefined,
        sku: formData.sku.trim() || undefined,
        specifications: formData.specifications.trim() || undefined,
      };
      if (formData.is_extra) {
        productData.image_url = undefined;
        // Extras cannot link other extras; omit optional_extras
      } else {
        productData.image_url = formData.image_url?.trim() || undefined;
        productData.optional_extras = selectedExtras.length > 0 ? selectedExtras : undefined;
      }

      await updateProduct(productId, productData);
      toast.success('Product updated successfully');
      router.push(`/products/${productId}`);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update product');
    } finally {
      setLoading(false);
    }
  };

  const toggleExtra = (extraId: number) => {
    setSelectedExtras((prev) =>
      prev.includes(extraId)
        ? prev.filter((id) => id !== extraId)
        : [...prev, extraId]
    );
  };

  if (pageLoading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <Button
            variant="ghost"
            onClick={() => router.push(`/products/${productId}`)}
            className="mb-4"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Product
          </Button>
          <div>
            <h1 className="text-3xl font-semibold">Edit Product</h1>
            <p className="text-muted-foreground mt-1">
              Update product information
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="space-y-6">
            {/* Basic Information */}
            <Card>
              <CardHeader>
                <CardTitle>Basic Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">
                      Name <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="name"
                      value={formData.name}
                      onChange={(e) =>
                        setFormData({ ...formData, name: e.target.value })
                      }
                      placeholder="Product Name"
                      required
                      disabled={loading}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="base_price">
                      Base Price (£) <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="base_price"
                      type="number"
                      step="0.01"
                      value={formData.base_price}
                      onChange={(e) =>
                        setFormData({ ...formData, base_price: e.target.value })
                      }
                      placeholder="0.00"
                      required
                      disabled={loading}
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    value={formData.description}
                    onChange={(e) =>
                      setFormData({ ...formData, description: e.target.value })
                    }
                    placeholder="Product description..."
                    rows={3}
                    disabled={loading}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="category">
                      Category <span className="text-destructive">*</span>
                    </Label>
                    <Select
                      value={formData.category}
                      onValueChange={(value) =>
                        setFormData({
                          ...formData,
                          category: value as ProductCategory,
                        })
                      }
                      disabled={loading}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.values(ProductCategory).map((cat) => (
                          <SelectItem key={cat} value={cat}>
                            {cat}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="subcategory">Subcategory</Label>
                    <Input
                      id="subcategory"
                      value={formData.subcategory}
                      onChange={(e) =>
                        setFormData({ ...formData, subcategory: e.target.value })
                      }
                      placeholder="e.g., Extras, Premium"
                      disabled={loading}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="unit">Unit</Label>
                    <Input
                      id="unit"
                      value={formData.unit}
                      onChange={(e) =>
                        setFormData({ ...formData, unit: e.target.value })
                      }
                      placeholder="unit, sqft, etc."
                      disabled={loading}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="sku">SKU</Label>
                    <Input
                      id="sku"
                      value={formData.sku}
                      onChange={(e) =>
                        setFormData({ ...formData, sku: e.target.value })
                      }
                      placeholder="Stock keeping unit"
                      disabled={loading}
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="installation_hours">
                    Installation Hours
                  </Label>
                  <Input
                    id="installation_hours"
                    type="number"
                    step="0.1"
                    value={formData.installation_hours}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        installation_hours: e.target.value,
                      })
                    }
                    placeholder="Hours required for installation"
                    disabled={loading}
                  />
                  <p className="text-xs text-muted-foreground">
                    Used to calculate installation cost
                  </p>
                </div>
              </CardContent>
            </Card>

            {!formData.is_extra && (
              <>
                {/* Image Upload */}
                <Card>
                  <CardHeader>
                    <CardTitle>Product Image</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ImageUpload
                      value={formData.image_url}
                      onChange={(url) =>
                        setFormData({ ...formData, image_url: url })
                      }
                      disabled={loading}
                    />
                  </CardContent>
                </Card>

                {/* Optional Extras */}
                <Card>
                  <CardHeader>
                    <CardTitle>Optional Extras</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm text-muted-foreground">
                      Select optional extras that can be added when this product is sold
                    </p>
                    {optionalExtras.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No optional extras available. Create optional extras first.
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {optionalExtras.map((extra) => (
                          <div
                            key={extra.id}
                            className="flex items-center space-x-2 p-3 border rounded-md hover:bg-muted/50 cursor-pointer"
                            onClick={() => toggleExtra(extra.id)}
                          >
                            <input
                              type="checkbox"
                              checked={selectedExtras.includes(extra.id)}
                              onChange={() => toggleExtra(extra.id)}
                              className="h-4 w-4"
                              disabled={loading}
                            />
                            <div className="flex-1">
                              <p className="font-medium">{extra.name}</p>
                              <p className="text-sm text-muted-foreground">
                                £{Number(extra.base_price).toFixed(2)}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </>
            )}

            {formData.is_extra && (
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-muted-foreground">
                    This is an optional extra. Image is not used.
                  </p>
                </CardContent>
              </Card>
            )}

            {/* Specifications */}
            <Card>
              <CardHeader>
                <CardTitle>Specifications</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <Label htmlFor="specifications">Technical Specifications</Label>
                  <Textarea
                    id="specifications"
                    value={formData.specifications}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        specifications: e.target.value,
                      })
                    }
                    placeholder="Technical specifications..."
                    rows={4}
                    disabled={loading}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Action Buttons */}
            <div className="flex items-center justify-end gap-4 pb-6">
              <Button
                type="button"
                variant="outline"
                onClick={() => router.push(`/products/${productId}`)}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={loading || !formData.name.trim() || !formData.base_price}>
                {loading ? 'Updating...' : 'Update Product'}
              </Button>
            </div>
          </div>
        </form>
      </main>
    </div>
  );
}
