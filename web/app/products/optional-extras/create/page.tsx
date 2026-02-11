'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
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
import { createProduct } from '@/lib/api';
import { ProductCategory } from '@/lib/types';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';

const PRODUCT_UNIT_OPTIONS = ['Per Box', 'Unit', 'Set'] as const;

export default function CreateOptionalExtraPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    base_price: '',
    unit: 'Unit',
    sku: '',
    specifications: '',
    installation_hours: '',
    boxes_per_product: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.name.trim() || !formData.base_price) {
      toast.error('Name and base price are required');
      return;
    }

    setLoading(true);
    try {
      await createProduct({
        name: formData.name.trim(),
        description: formData.description.trim() || undefined,
        category: ProductCategory.STABLES,
        is_extra: true,
        base_price: parseFloat(formData.base_price),
        unit: formData.unit.trim() || 'Unit',
        sku: formData.sku.trim() || undefined,
        specifications: formData.specifications.trim() || undefined,
        installation_hours: formData.installation_hours
          ? parseFloat(formData.installation_hours)
          : undefined,
        boxes_per_product: formData.boxes_per_product
          ? parseInt(formData.boxes_per_product, 10)
          : undefined,
      });
      toast.success('Optional extra created successfully');
      router.push('/products/optional-extras');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to create optional extra');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <Button
            variant="ghost"
            onClick={() => router.push('/products/optional-extras')}
            className="mb-4"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Optional Extras
          </Button>
          <div>
            <h1 className="text-3xl font-semibold">Create Optional Extra</h1>
            <p className="text-muted-foreground mt-1">
              Add an optional extra that can be linked to products
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Details</CardTitle>
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
                      placeholder="Optional extra name"
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
                    placeholder="Description..."
                    rows={3}
                    disabled={loading}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="unit">Unit</Label>
                    <Select
                      value={formData.unit}
                      onValueChange={(value) =>
                        setFormData({ ...formData, unit: value })
                      }
                      disabled={loading}
                    >
                      <SelectTrigger id="unit">
                        <SelectValue placeholder="Select unit" />
                      </SelectTrigger>
                      <SelectContent>
                        {PRODUCT_UNIT_OPTIONS.map((opt) => (
                          <SelectItem key={opt} value={opt}>
                            {opt}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
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
                  <Label htmlFor="installation_hours">Installation Hours</Label>
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
                <div className="space-y-2">
                  <Label htmlFor="boxes_per_product">Number of boxes (optional)</Label>
                  <Input
                    id="boxes_per_product"
                    type="number"
                    min={1}
                    value={formData.boxes_per_product}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        boxes_per_product: e.target.value,
                      })
                    }
                    placeholder="e.g. 4"
                    disabled={loading}
                  />
                  <p className="text-xs text-muted-foreground">
                    Used in installation calculation. Leave blank if not boxed.
                  </p>
                </div>
              </CardContent>
            </Card>

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

            <div className="flex items-center justify-end gap-4 pb-6">
              <Button
                type="button"
                variant="outline"
                onClick={() => router.push('/products/optional-extras')}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={loading || !formData.name.trim() || !formData.base_price}>
                {loading ? 'Creating...' : 'Create Optional Extra'}
              </Button>
            </div>
          </div>
        </form>
      </main>
    </div>
  );
}
