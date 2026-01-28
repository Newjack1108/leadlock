'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { getOptionalExtras, getProducts } from '@/lib/api';
import { Product, ProductCategory } from '@/lib/types';
import { toast } from 'sonner';
import { ArrowLeft, Plus, Edit, Package } from 'lucide-react';
import Link from 'next/link';

export default function OptionalExtrasPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [optionalExtras, setOptionalExtras] = useState<Product[]>([]);
  const [productsUsingExtras, setProductsUsingExtras] = useState<Record<number, Product[]>>({});

  useEffect(() => {
    fetchOptionalExtras();
  }, []);

  const fetchOptionalExtras = async () => {
    try {
      setLoading(true);
      const extras = await getOptionalExtras();
      setOptionalExtras(extras);
      
      // Fetch all products to find which ones use each extra
      const allProducts = await getProducts();
      const usageMap: Record<number, Product[]> = {};
      
      extras.forEach((extra) => {
        usageMap[extra.id] = [];
      });
      
      // For each product, check if it has optional extras
      for (const product of allProducts) {
        if (product.optional_extras) {
          product.optional_extras.forEach((extra) => {
            if (usageMap[extra.id]) {
              usageMap[extra.id].push(product);
            }
          });
        }
      }
      
      setProductsUsingExtras(usageMap);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load optional extras');
      }
    } finally {
      setLoading(false);
    }
  };

  const categoryColors: Record<ProductCategory, string> = {
    STABLES: 'bg-blue-100 text-blue-700',
    SHEDS: 'bg-green-100 text-green-700',
    CABINS: 'bg-purple-100 text-purple-700',
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <Button
            variant="ghost"
            onClick={() => router.push('/products')}
            className="mb-4"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Products
          </Button>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-semibold mb-2">Optional Extras</h1>
              <p className="text-muted-foreground">
                Manage optional extras that can be added to products
              </p>
            </div>
            <Button asChild>
              <Link href="/products/create">
                <Plus className="h-4 w-4 mr-2" />
                Create Optional Extra
              </Link>
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        ) : optionalExtras.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <Package className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground mb-4">No optional extras found</p>
              <Button asChild>
                <Link href="/products/create">
                  <Plus className="h-4 w-4 mr-2" />
                  Create Your First Optional Extra
                </Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {optionalExtras.map((extra) => (
              <Card key={extra.id} className="hover:shadow-lg transition-shadow">
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg">{extra.name}</CardTitle>
                      <div className="flex gap-2 mt-2">
                        <Badge className={categoryColors[extra.category]}>
                          {extra.category}
                        </Badge>
                        {extra.subcategory && (
                          <Badge variant="secondary">{extra.subcategory}</Badge>
                        )}
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => router.push(`/products/${extra.id}/edit`)}
                    >
                      <Edit className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {extra.description && (
                    <p className="text-sm text-muted-foreground mb-3">{extra.description}</p>
                  )}
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Price:</span>
                      <span className="font-semibold">£{Number(extra.base_price).toFixed(2)}</span>
                    </div>
                    {extra.unit && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Unit:</span>
                        <span>{extra.unit}</span>
                      </div>
                    )}
                    {extra.sku && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">SKU:</span>
                        <span>{extra.sku}</span>
                      </div>
                    )}
                  </div>
                  {productsUsingExtras[extra.id] && productsUsingExtras[extra.id].length > 0 && (
                    <div className="mt-4 pt-4 border-t">
                      <p className="text-xs text-muted-foreground mb-2">
                        Used by {productsUsingExtras[extra.id].length} product(s):
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {productsUsingExtras[extra.id].slice(0, 3).map((product) => (
                          <Badge
                            key={product.id}
                            variant="outline"
                            className="text-xs cursor-pointer"
                            onClick={() => router.push(`/products/${product.id}`)}
                          >
                            {product.name}
                          </Badge>
                        ))}
                        {productsUsingExtras[extra.id].length > 3 && (
                          <Badge variant="outline" className="text-xs">
                            +{productsUsingExtras[extra.id].length - 3} more
                          </Badge>
                        )}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
