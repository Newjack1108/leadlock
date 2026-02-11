'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  getDiscountTemplates,
  createDiscountTemplate,
  updateDiscountTemplate,
  deleteDiscountTemplate,
} from '@/lib/api';
import { DiscountTemplate, DiscountType, DiscountScope } from '@/lib/types';
import { toast } from 'sonner';
import { Plus, Edit, Trash2, Tag, Gift } from 'lucide-react';

export default function DiscountsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [discounts, setDiscounts] = useState<DiscountTemplate[]>([]);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingDiscount, setEditingDiscount] = useState<DiscountTemplate | null>(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    discount_type: DiscountType.PERCENTAGE,
    discount_value: '',
    scope: DiscountScope.QUOTE,
    is_giveaway: false,
  });

  useEffect(() => {
    fetchDiscounts();
  }, []);

  const fetchDiscounts = async () => {
    try {
      setLoading(true);
      const data = await getDiscountTemplates();
      setDiscounts(data);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load discounts');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCreateDiscount = async () => {
    if (!formData.name.trim() || !formData.discount_value) {
      toast.error('Name and discount value are required');
      return;
    }

    try {
      setSaving(true);
      await createDiscountTemplate({
        ...formData,
        discount_value: parseFloat(formData.discount_value),
      });
      toast.success('Discount created successfully');
      setCreateDialogOpen(false);
      resetForm();
      fetchDiscounts();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to create discount');
    } finally {
      setSaving(false);
    }
  };

  const handleEditDiscount = (discount: DiscountTemplate) => {
    setEditingDiscount(discount);
    setFormData({
      name: discount.name,
      description: discount.description || '',
      discount_type: discount.discount_type,
      discount_value: discount.discount_value.toString(),
      scope: discount.scope,
      is_giveaway: discount.is_giveaway,
    });
    setEditDialogOpen(true);
  };

  const handleUpdateDiscount = async () => {
    if (!editingDiscount || !formData.name.trim() || !formData.discount_value) {
      toast.error('Name and discount value are required');
      return;
    }

    try {
      setSaving(true);
      await updateDiscountTemplate(editingDiscount.id, {
        ...formData,
        discount_value: parseFloat(formData.discount_value),
      });
      toast.success('Discount updated successfully');
      setEditDialogOpen(false);
      setEditingDiscount(null);
      resetForm();
      fetchDiscounts();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update discount');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteDiscount = async (discountId: number) => {
    if (!confirm('Are you sure you want to deactivate this discount?')) {
      return;
    }

    try {
      await deleteDiscountTemplate(discountId);
      toast.success('Discount deactivated successfully');
      fetchDiscounts();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to deactivate discount');
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      discount_type: DiscountType.PERCENTAGE,
      discount_value: '',
      scope: DiscountScope.QUOTE,
      is_giveaway: false,
    });
  };

  const formatDiscountValue = (discount: DiscountTemplate) => {
    if (discount.discount_type === DiscountType.PERCENTAGE) {
      return `${discount.discount_value}%`;
    } else {
      return `£${Number(discount.discount_value).toFixed(2)}`;
    }
  };

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold mb-2">Discounts & Giveaways</h1>
            <p className="text-muted-foreground">Manage discount templates and giveaways</p>
          </div>
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Create Discount
          </Button>
        </div>

        {loading ? (
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        ) : discounts.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <Tag className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground mb-4">No discounts found</p>
              <Button onClick={() => setCreateDialogOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Create Your First Discount
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {discounts.map((discount) => (
              <Card key={discount.id}>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg flex items-center gap-2">
                        {discount.is_giveaway && <Gift className="h-4 w-4 text-primary" />}
                        {discount.name}
                      </CardTitle>
                      <div className="flex gap-2 mt-2">
                        <Badge variant={discount.is_active ? 'default' : 'secondary'}>
                          {discount.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                        {discount.is_giveaway && (
                          <Badge variant="outline">Giveaway</Badge>
                        )}
                        <Badge variant="outline">
                          {discount.scope === DiscountScope.PRODUCT ? 'Product (Building Only)' : 'Entire Quote'}
                        </Badge>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleEditDiscount(discount)}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteDiscount(discount.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {discount.description && (
                    <p className="text-sm text-muted-foreground mb-3">{discount.description}</p>
                  )}
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Discount:</span>
                      <span className="font-semibold">{formatDiscountValue(discount)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Type:</span>
                      <span>{discount.discount_type === DiscountType.PERCENTAGE ? 'Percentage' : 'Fixed Amount'}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Create Discount Dialog */}
        <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Create New Discount</DialogTitle>
              <DialogDescription>
                Create a discount template that can be applied to quotes
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="name">
                  Name <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., 10% Off, £50 New Customer Discount"
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Optional description..."
                  rows={2}
                  disabled={saving}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="discount_type">
                    Discount Type <span className="text-destructive">*</span>
                  </Label>
                  <Select
                    value={formData.discount_type}
                    onValueChange={(value) =>
                      setFormData({ ...formData, discount_type: value as DiscountType })
                    }
                    disabled={saving}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={DiscountType.PERCENTAGE}>Percentage</SelectItem>
                      <SelectItem value={DiscountType.FIXED_AMOUNT}>Fixed Amount</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="discount_value">
                    Discount Value <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="discount_value"
                    type="number"
                    step="0.01"
                    value={formData.discount_value}
                    onChange={(e) => setFormData({ ...formData, discount_value: e.target.value })}
                    placeholder={formData.discount_type === DiscountType.PERCENTAGE ? "10" : "50.00"}
                    disabled={saving}
                  />
                  <p className="text-xs text-muted-foreground">
                    {formData.discount_type === DiscountType.PERCENTAGE
                      ? 'Enter percentage (e.g., 10 for 10%)'
                      : 'Enter amount in £'}
                  </p>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="scope">
                  Scope <span className="text-destructive">*</span>
                </Label>
                <Select
                  value={formData.scope}
                  onValueChange={(value) =>
                    setFormData({ ...formData, scope: value as DiscountScope })
                  }
                  disabled={saving}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={DiscountScope.PRODUCT}>Product (Building Only)</SelectItem>
                    <SelectItem value={DiscountScope.QUOTE}>Entire Quote</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Product: Applied to building/main items only (not optional extras). Quote: Applied to entire quote total.
                </p>
              </div>
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="is_giveaway"
                  checked={formData.is_giveaway}
                  onChange={(e) =>
                    setFormData({ ...formData, is_giveaway: e.target.checked })
                  }
                  disabled={saving}
                  className="h-4 w-4"
                />
                <Label htmlFor="is_giveaway" className="cursor-pointer">
                  This is a giveaway (free product)
                </Label>
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setCreateDialogOpen(false);
                  resetForm();
                }}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button
                onClick={handleCreateDiscount}
                disabled={saving || !formData.name.trim() || !formData.discount_value}
              >
                {saving ? 'Creating...' : 'Create Discount'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Edit Discount Dialog */}
        <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Edit Discount</DialogTitle>
              <DialogDescription>
                Update discount template information
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="edit-name">
                  Name <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="edit-name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., 10% Off, £50 New Customer Discount"
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-description">Description</Label>
                <Textarea
                  id="edit-description"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Optional description..."
                  rows={2}
                  disabled={saving}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-discount_type">
                    Discount Type <span className="text-destructive">*</span>
                  </Label>
                  <Select
                    value={formData.discount_type}
                    onValueChange={(value) =>
                      setFormData({ ...formData, discount_type: value as DiscountType })
                    }
                    disabled={saving}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={DiscountType.PERCENTAGE}>Percentage</SelectItem>
                      <SelectItem value={DiscountType.FIXED_AMOUNT}>Fixed Amount</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-discount_value">
                    Discount Value <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="edit-discount_value"
                    type="number"
                    step="0.01"
                    value={formData.discount_value}
                    onChange={(e) => setFormData({ ...formData, discount_value: e.target.value })}
                    placeholder={formData.discount_type === DiscountType.PERCENTAGE ? "10" : "50.00"}
                    disabled={saving}
                  />
                  <p className="text-xs text-muted-foreground">
                    {formData.discount_type === DiscountType.PERCENTAGE
                      ? 'Enter percentage (e.g., 10 for 10%)'
                      : 'Enter amount in £'}
                  </p>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-scope">
                  Scope <span className="text-destructive">*</span>
                </Label>
                <Select
                  value={formData.scope}
                  onValueChange={(value) =>
                    setFormData({ ...formData, scope: value as DiscountScope })
                  }
                  disabled={saving}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={DiscountScope.PRODUCT}>Product (Building Only)</SelectItem>
                    <SelectItem value={DiscountScope.QUOTE}>Entire Quote</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Product: Applied to building/main items only (not optional extras). Quote: Applied to entire quote total.
                </p>
              </div>
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="edit-is_giveaway"
                  checked={formData.is_giveaway}
                  onChange={(e) =>
                    setFormData({ ...formData, is_giveaway: e.target.checked })
                  }
                  disabled={saving}
                  className="h-4 w-4"
                />
                <Label htmlFor="edit-is_giveaway" className="cursor-pointer">
                  This is a giveaway (free product)
                </Label>
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setEditDialogOpen(false);
                  setEditingDiscount(null);
                  resetForm();
                }}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button
                onClick={handleUpdateDiscount}
                disabled={saving || !formData.name.trim() || !formData.discount_value}
              >
                {saving ? 'Updating...' : 'Update Discount'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}
