'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Plus, Edit, Trash2, Package } from 'lucide-react';
import Link from 'next/link';
import api from '@/lib/api';
import { Product, ProductCategory } from '@/lib/types';
import { toast } from 'sonner';

export default function ProductsPage() {
  const router = useRouter();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [categoryFilter, setCategoryFilter] = useState<ProductCategory | 'ALL'>('ALL');
  const [extrasFilter, setExtrasFilter] = useState<'ALL' | true | false>('ALL');
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [saving, setSaving] = useState(false);
  const [newProduct, setNewProduct] = useState({
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
  });

  useEffect(() => {
    fetchProducts();
  }, [categoryFilter, extrasFilter]);

  const fetchProducts = async () => {
    try {
      setLoading(true);
      const params: any = { is_active: true };
      if (categoryFilter !== 'ALL') {
        params.category = categoryFilter;
      }
      if (extrasFilter !== 'ALL') {
        params.is_extra = extrasFilter;
      }

      const response = await api.get('/api/products', { params });
      setProducts(response.data);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load products');
      }
    } finally {
      setLoading(false);
    }
  };


  const handleEditProduct = (product: Product) => {
    router.push(`/products/${product.id}/edit`);
  };

  const handleUpdateProduct = async () => {
    if (!editingProduct || !newProduct.name.trim() || !newProduct.base_price) {
      toast.error('Name and base price are required');
      return;
    }

    try {
      setSaving(true);
      await api.patch(`/api/products/${editingProduct.id}`, {
        ...newProduct,
        base_price: parseFloat(newProduct.base_price),
        description: newProduct.description.trim() || undefined,
        subcategory: newProduct.subcategory.trim() || undefined,
        sku: newProduct.sku.trim() || undefined,
        image_url: newProduct.image_url.trim() || undefined,
        specifications: newProduct.specifications.trim() || undefined,
      });
      
      toast.success('Product updated successfully');
      setEditDialogOpen(false);
      setEditingProduct(null);
      fetchProducts();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update product');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteProduct = async (productId: number) => {
    if (!confirm('Are you sure you want to deactivate this product?')) {
      return;
    }

    try {
      await api.delete(`/api/products/${productId}`);
      toast.success('Product deactivated successfully');
      fetchProducts();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to deactivate product');
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
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold mb-2">Products</h1>
            <p className="text-muted-foreground">Manage your product catalog</p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" asChild>
              <Link href="/products/optional-extras">
                Optional Extras
              </Link>
            </Button>
            <Button asChild>
              <Link href="/products/create">
                <Plus className="h-4 w-4 mr-2" />
                Create Product
              </Link>
            </Button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-col md:flex-row gap-4 mb-6">
          <Select value={categoryFilter} onValueChange={(value) => setCategoryFilter(value as ProductCategory | 'ALL')}>
            <SelectTrigger className="w-full md:w-[200px]">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All Categories</SelectItem>
              {Object.values(ProductCategory).map((cat) => (
                <SelectItem key={cat} value={cat}>
                  {cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={extrasFilter.toString()} onValueChange={(value) => setExtrasFilter(value === 'ALL' ? 'ALL' : value === 'true')}>
            <SelectTrigger className="w-full md:w-[200px]">
              <SelectValue placeholder="Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All Types</SelectItem>
              <SelectItem value="false">Regular Products</SelectItem>
              <SelectItem value="true">Extras Only</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Products List */}
        {loading ? (
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        ) : products.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">No products found</div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[...products].sort((a, b) => a.name.localeCompare(b.name)).map((product) => (
              <Card key={product.id} className="cursor-pointer hover:shadow-lg transition-shadow" onClick={() => router.push(`/products/${product.id}`)}>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg">{product.name}</CardTitle>
                      <div className="flex gap-2 mt-2">
                        <Badge className={categoryColors[product.category]}>
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
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleEditProduct(product)}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteProduct(product.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {product.description && (
                    <p className="text-sm text-muted-foreground mb-3">{product.description}</p>
                  )}
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Price:</span>
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
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Edit Product Dialog */}
        <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Edit Product</DialogTitle>
              <DialogDescription>
                Update product information
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-name">
                    Name <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="edit-name"
                    value={newProduct.name}
                    onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })}
                    placeholder="Product Name"
                    disabled={saving}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-base_price">
                    Base Price (£) <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="edit-base_price"
                    type="number"
                    step="0.01"
                    value={newProduct.base_price}
                    onChange={(e) => setNewProduct({ ...newProduct, base_price: e.target.value })}
                    placeholder="0.00"
                    disabled={saving}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-description">Description</Label>
                <Textarea
                  id="edit-description"
                  value={newProduct.description}
                  onChange={(e) => setNewProduct({ ...newProduct, description: e.target.value })}
                  placeholder="Product description..."
                  rows={3}
                  disabled={saving}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-category">Category <span className="text-destructive">*</span></Label>
                  <Select
                    value={newProduct.category}
                    onValueChange={(value) => setNewProduct({ ...newProduct, category: value as ProductCategory })}
                    disabled={saving}
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
                  <Label htmlFor="edit-subcategory">Subcategory</Label>
                  <Input
                    id="edit-subcategory"
                    value={newProduct.subcategory}
                    onChange={(e) => setNewProduct({ ...newProduct, subcategory: e.target.value })}
                    placeholder="e.g., Extras, Premium"
                    disabled={saving}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-unit">Unit</Label>
                  <Input
                    id="edit-unit"
                    value={newProduct.unit}
                    onChange={(e) => setNewProduct({ ...newProduct, unit: e.target.value })}
                    placeholder="unit, sqft, etc."
                    disabled={saving}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-sku">SKU</Label>
                  <Input
                    id="edit-sku"
                    value={newProduct.sku}
                    onChange={(e) => setNewProduct({ ...newProduct, sku: e.target.value })}
                    placeholder="Stock keeping unit"
                    disabled={saving}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-image_url">Image URL</Label>
                <Input
                  id="edit-image_url"
                  value={newProduct.image_url}
                  onChange={(e) => setNewProduct({ ...newProduct, image_url: e.target.value })}
                  placeholder="https://..."
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-specifications">Specifications</Label>
                <Textarea
                  id="edit-specifications"
                  value={newProduct.specifications}
                  onChange={(e) => setNewProduct({ ...newProduct, specifications: e.target.value })}
                  placeholder="Technical specifications..."
                  rows={3}
                  disabled={saving}
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setEditDialogOpen(false);
                  setEditingProduct(null);
                }}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button onClick={handleUpdateProduct} disabled={saving || !newProduct.name.trim() || !newProduct.base_price}>
                {saving ? 'Updating...' : 'Update Product'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}
