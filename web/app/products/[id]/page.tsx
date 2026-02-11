'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { getProduct, getCompanySettings } from '@/lib/api';
import { Product, CompanySettings } from '@/lib/types';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Package } from 'lucide-react';
import Image from 'next/image';

export default function ProductDetailPage() {
  const router = useRouter();
  const params = useParams();
  const productId = parseInt(params.id as string);

  const [loading, setLoading] = useState(true);
  const [product, setProduct] = useState<Product | null>(null);
  const [companySettings, setCompanySettings] = useState<CompanySettings | null>(null);

  useEffect(() => {
    if (productId) {
      fetchProduct();
      fetchCompanySettings();
    }
  }, [productId]);

  const fetchProduct = async () => {
    try {
      setLoading(true);
      const data = await getProduct(productId);
      setProduct(data);
    } catch (error: any) {
      if (error.response?.status === 404) {
        toast.error('Product not found');
        router.push('/products');
      } else {
        toast.error('Failed to load product');
      }
    } finally {
      setLoading(false);
    }
  };

  const fetchCompanySettings = async () => {
    try {
      const settings = await getCompanySettings();
      setCompanySettings(settings);
    } catch (error) {
      console.error('Failed to load company settings');
    }
  };

  const calculateInstallCost = () => {
    if (!product?.installation_hours || !companySettings?.hourly_install_rate) {
      return null;
    }
    return product.installation_hours * companySettings.hourly_install_rate;
  };

  const categoryColors: Record<string, string> = {
    STABLES: 'bg-blue-100 text-blue-700',
    SHEDS: 'bg-green-100 text-green-700',
    CABINS: 'bg-purple-100 text-purple-700',
  };

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Product not found</div>
          <div className="text-center mt-4">
            <Button variant="outline" onClick={() => router.push('/products')}>
              Back to Products
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const installCost = calculateInstallCost();

  return (
    <div className="min-h-screen">
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
              <h1 className="text-3xl font-semibold">{product.name}</h1>
              <div className="flex gap-2 mt-2">
                <Badge className={categoryColors[product.category] || 'bg-gray-100 text-gray-700'}>
                  {product.category}
                </Badge>
                {product.is_extra && (
                  <Badge variant="outline">Extra</Badge>
                )}
                {product.subcategory && (
                  <Badge variant="secondary">{product.subcategory}</Badge>
                )}
              </div>
            </div>
            <Button onClick={() => router.push(`/products/${product.id}/edit`)}>
              <Edit className="h-4 w-4 mr-2" />
              Edit Product
            </Button>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          {/* Product Image */}
          {product.image_url && (
            <Card>
              <CardHeader>
                <CardTitle>Product Image</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="relative w-full h-96 rounded-md overflow-hidden bg-muted">
                  <img
                    src={product.image_url}
                    alt={product.name}
                    className="w-full h-full object-contain"
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {/* Product Details */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Product Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Base Price:</span>
                    <span className="font-semibold">£{Number(product.base_price).toFixed(2)}</span>
                  </div>
                  {product.unit && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Unit:</span>
                      <span>{product.unit}</span>
                    </div>
                  )}
                  {product.sku && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">SKU:</span>
                      <span>{product.sku}</span>
                    </div>
                  )}
                  {product.installation_hours && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Installation Hours:</span>
                      <span>{product.installation_hours} hours</span>
                    </div>
                  )}
                  {product.boxes_per_product != null && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Boxes per product:</span>
                      <span>{product.boxes_per_product}</span>
                    </div>
                  )}
                  {installCost !== null && (
                    <div className="flex justify-between border-t pt-2">
                      <span className="font-semibold">Installation Cost:</span>
                      <span className="font-semibold text-lg">£{installCost.toFixed(2)}</span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {product.description && (
              <Card>
                <CardHeader>
                  <CardTitle>Description</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm whitespace-pre-wrap">{product.description}</p>
                </CardContent>
              </Card>
            )}

            {product.specifications && (
              <Card>
                <CardHeader>
                  <CardTitle>Specifications</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm whitespace-pre-wrap">{product.specifications}</p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>

        {/* Optional Extras */}
        {product.optional_extras && product.optional_extras.length > 0 && (
          <Card className="mt-6">
            <CardHeader>
              <CardTitle>Optional Extras</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {[...product.optional_extras].sort((a, b) => a.name.localeCompare(b.name)).map((extra) => (
                  <div
                    key={extra.id}
                    className="p-4 border rounded-md hover:bg-muted/50 cursor-pointer"
                    onClick={() => router.push(`/products/${extra.id}`)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <p className="font-medium">{extra.name}</p>
                        <p className="text-sm text-muted-foreground mt-1">
                          £{Number(extra.base_price).toFixed(2)}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
