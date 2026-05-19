'use client';

import { useState, useEffect, useCallback } from 'react';
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
import { getApiErrorDetail, getProduct, updateProduct, getOptionalExtras } from '@/lib/api';
import { getAllowedConfiguratorFrontFaces } from '@/lib/configurator/productFrontFace';
import {
  ProductCategory,
  Product,
  PRODUCT_SUBCATEGORIES,
  CONFIGURATOR_CONNECTION_PROFILES,
  CONFIGURATOR_FRONT_FACES,
  type ConfiguratorConnectionProfile,
  type ConfiguratorFrontFace,
} from '@/lib/types';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';

const PRODUCT_UNIT_OPTIONS = ['Per Box', 'Unit', 'Set'] as const;
const SUBCATEGORY_NONE = '__NONE__';
const CONFIGURATOR_FRONT_FACE_NONE = '__NONE__';
const CONFIGURATOR_CONNECTION_PROFILE_NONE = '__NONE__';
const CONFIGURATOR_FRONT_FACE_LABELS: Record<ConfiguratorFrontFace, string> = {
  top: 'Top edge',
  right: 'Right edge',
  bottom: 'Bottom edge',
  left: 'Left edge',
};
const CONFIGURATOR_CONNECTION_PROFILE_LABELS: Record<ConfiguratorConnectionProfile, string> = {
  corner_left: 'Corner box - left hand',
  corner_right: 'Corner box - right hand',
};

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
    allow_trade_dealer_sale: false,
    base_price: '',
    unit: 'Unit',
    sku: '',
    image_url: '',
    specifications: '',
    size: '',
    height: '',
    floor_plan_url: '',
    width: '',
    length: '',
    configurator_width: '',
    configurator_length: '',
    configurator_front_face: '' as ConfiguratorFrontFace | '',
    configurator_connection_profile: '' as ConfiguratorConnectionProfile | '',
    configurator_is_corner_box: false,
    configurator_is_starter_box: false,
    allow_in_configurator: false,
    configurator_per_box: false,
    installation_hours: '',
    boxes_per_product: '',
  });

  const isStandardSubcategory = (value: string) =>
    PRODUCT_SUBCATEGORIES.includes(value as (typeof PRODUCT_SUBCATEGORIES)[number]);

  const subcategorySelectValue =
    !formData.subcategory || formData.subcategory.trim() === ''
      ? SUBCATEGORY_NONE
      : formData.subcategory;
  const isConfiguratorCategory = formData.category === ProductCategory.CONFIGURATOR;
  const isCornerConfiguratorProduct =
    isConfiguratorCategory && !formData.is_extra && formData.configurator_is_corner_box;
  const hasCornerConnectionProfile =
    isCornerConfiguratorProduct && formData.configurator_connection_profile !== '';
  const allowedConfiguratorFrontFaces = getAllowedConfiguratorFrontFaces(
    formData.configurator_width,
    formData.configurator_length
  );
  const requiresConfiguratorFrontFace =
    isConfiguratorCategory &&
    !formData.is_extra &&
    !isCornerConfiguratorProduct &&
    formData.configurator_width !== '' &&
    formData.configurator_length !== '' &&
    Number(formData.configurator_width) !== Number(formData.configurator_length);

  const fetchProduct = useCallback(async () => {
    try {
      setPageLoading(true);
      const product = await getProduct(productId);
      setFormData({
        name: product.name,
        description: product.description || '',
        category: product.category,
        subcategory: product.subcategory || '',
        is_extra: product.is_extra,
        allow_trade_dealer_sale: product.allow_trade_dealer_sale ?? false,
        base_price: product.base_price.toString(),
        unit: PRODUCT_UNIT_OPTIONS.includes(product.unit as (typeof PRODUCT_UNIT_OPTIONS)[number])
          ? product.unit
          : 'Unit',
        sku: product.sku || '',
        image_url: product.image_url || '',
        specifications: product.specifications || '',
        size: product.size || '',
        height: product.height || '',
        floor_plan_url: product.floor_plan_url || '',
        width: product.width?.toString() || '',
        length: product.length?.toString() || '',
        configurator_width: product.configurator_width?.toString() || '',
        configurator_length: product.configurator_length?.toString() || '',
        configurator_front_face: product.configurator_front_face || '',
        configurator_connection_profile: product.configurator_connection_profile || '',
        configurator_is_corner_box:
          product.configurator_is_corner_box ?? Boolean(product.configurator_connection_profile),
        configurator_is_starter_box: product.configurator_is_starter_box ?? false,
        allow_in_configurator: product.allow_in_configurator ?? false,
        configurator_per_box: product.configurator_per_box ?? false,
        installation_hours: product.installation_hours?.toString() || '',
        boxes_per_product: product.boxes_per_product?.toString() || '',
      });
      if (product.optional_extras) {
        setSelectedExtras(product.optional_extras.map((e: Product) => e.id));
      }
    } catch (error: unknown) {
      if ((error as { response?: { status?: number } })?.response?.status === 404) {
        toast.error('Product not found');
        router.push('/products');
      } else {
        toast.error(getApiErrorDetail(error) || 'Failed to load product');
      }
    } finally {
      setPageLoading(false);
    }
  }, [productId, router]);

  const fetchOptionalExtras = useCallback(async () => {
    try {
      const extras = await getOptionalExtras();
      setOptionalExtras(extras);
    } catch {
      console.error('Failed to load optional extras');
    }
  }, []);

  useEffect(() => {
    if (productId) {
      fetchProduct();
      fetchOptionalExtras();
    }
  }, [fetchOptionalExtras, fetchProduct, productId]);

  useEffect(() => {
    if (
      (!isConfiguratorCategory || formData.is_extra) &&
      (formData.configurator_front_face !== '' ||
        formData.configurator_is_corner_box ||
        formData.configurator_is_starter_box)
    ) {
      setFormData((prev) => ({
        ...prev,
        configurator_front_face: '',
        configurator_connection_profile: '',
        configurator_is_corner_box: false,
        configurator_is_starter_box: false,
      }));
      return;
    }
    if (isConfiguratorCategory && !formData.configurator_is_corner_box && formData.configurator_connection_profile !== '') {
      setFormData((prev) => ({
        ...prev,
        configurator_connection_profile: '',
      }));
      return;
    }
    if (hasCornerConnectionProfile && formData.configurator_front_face !== '') {
      setFormData((prev) => ({
        ...prev,
        configurator_front_face: '',
      }));
      return;
    }
    if (
      formData.configurator_front_face &&
      !allowedConfiguratorFrontFaces.includes(formData.configurator_front_face)
    ) {
      setFormData((prev) => ({
        ...prev,
        configurator_front_face: '',
      }));
    }
  }, [
    allowedConfiguratorFrontFaces,
    formData.configurator_front_face,
    hasCornerConnectionProfile,
    formData.is_extra,
    isConfiguratorCategory,
  ]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.name.trim() || !formData.base_price) {
      toast.error('Name and base price are required');
      return;
    }

    if (isConfiguratorCategory && !formData.is_extra && (!formData.configurator_width || !formData.configurator_length)) {
      toast.error('Configurator products require configurator width and length');
      return;
    }

    if (requiresConfiguratorFrontFace && !formData.configurator_front_face) {
      toast.error('Non-square configurator products must choose which edge is the front');
      return;
    }

    if (isCornerConfiguratorProduct && !formData.configurator_connection_profile) {
      toast.error('Corner boxes must choose a left or right corner handedness');
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
        boxes_per_product: formData.boxes_per_product
          ? parseInt(formData.boxes_per_product, 10)
          : undefined,
        description: formData.description.trim() || undefined,
        subcategory: formData.subcategory.trim() || undefined,
        sku: formData.sku.trim() || undefined,
        specifications: formData.specifications.trim() || undefined,
        size: formData.size.trim() || undefined,
        height: formData.height.trim() || undefined,
        floor_plan_url: formData.floor_plan_url.trim() || null,
        width: formData.width ? parseFloat(formData.width) : undefined,
        length: formData.length ? parseFloat(formData.length) : undefined,
        configurator_width: formData.configurator_width ? parseFloat(formData.configurator_width) : null,
        configurator_length: formData.configurator_length ? parseFloat(formData.configurator_length) : null,
        configurator_front_face: formData.configurator_connection_profile
          ? null
          : formData.configurator_front_face || null,
        configurator_connection_profile: formData.configurator_is_corner_box
          ? formData.configurator_connection_profile || null
          : null,
        configurator_is_corner_box:
          isConfiguratorCategory && !formData.is_extra ? formData.configurator_is_corner_box : false,
        configurator_is_starter_box:
          isConfiguratorCategory && !formData.is_extra ? formData.configurator_is_starter_box : false,
        allow_in_configurator: formData.allow_in_configurator,
        configurator_per_box: formData.is_extra && formData.allow_in_configurator ? formData.configurator_per_box : false,
      };
      if (formData.is_extra) {
        productData.image_url = formData.image_url?.trim() || null;
        // Extras cannot link other extras; omit optional_extras
      } else {
        productData.image_url = formData.image_url?.trim() || null;
        productData.optional_extras = selectedExtras.length > 0 ? selectedExtras : undefined;
      }

      await updateProduct(productId, productData);
      toast.success('Product updated successfully');
      router.push(`/products/${productId}`);
    } catch (error: unknown) {
      toast.error(getApiErrorDetail(error) || 'Failed to update product');
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

  /** Normalize form values and refresh state so displayed values and calculations are correct. */
  const handleSaveAndRecalculate = () => {
    setFormData((prev) => ({
      ...prev,
      base_price: prev.base_price === '' ? '' : String(Number(prev.base_price) || 0),
      installation_hours: prev.installation_hours === '' ? '' : String(Number(prev.installation_hours) || ''),
      boxes_per_product: prev.boxes_per_product === '' ? '' : String(parseInt(prev.boxes_per_product, 10) || ''),
    }));
    toast.success('Product details recalculated');
  };

  if (pageLoading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 sm:px-6 py-8">
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
                <div className="flex items-center gap-2">
                  <input
                    id="allow_trade_dealer_sale"
                    type="checkbox"
                    checked={formData.allow_trade_dealer_sale}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        allow_trade_dealer_sale: e.target.checked,
                      })
                    }
                    className="h-4 w-4"
                    disabled={loading}
                  />
                  <Label htmlFor="allow_trade_dealer_sale">
                    Allow trade dealers to sell this product
                  </Label>
                </div>
                {formData.is_extra && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <input
                        id="allow_in_configurator"
                        type="checkbox"
                        checked={formData.allow_in_configurator}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            allow_in_configurator: e.target.checked,
                            configurator_per_box: e.target.checked ? formData.configurator_per_box : false,
                          })
                        }
                        className="h-4 w-4"
                        disabled={loading}
                      />
                      <Label htmlFor="allow_in_configurator">Allow in configurator</Label>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      When checked, this extra appears under Configurator Extras on the quote configurator.
                    </p>
                    {formData.allow_in_configurator && (
                      <>
                        <div className="flex items-center gap-2">
                          <input
                            id="configurator_per_box"
                            type="checkbox"
                            checked={formData.configurator_per_box}
                            onChange={(e) =>
                              setFormData({ ...formData, configurator_per_box: e.target.checked })
                            }
                            className="h-4 w-4"
                            disabled={loading}
                          />
                          <Label htmlFor="configurator_per_box">Quantity per box in configurator</Label>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          In the configurator, quantity equals the number of boxes on the layout. Quote unit is
                          unchanged.
                        </p>
                      </>
                    )}
                  </div>
                )}
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
                    <Select
                      value={subcategorySelectValue}
                      onValueChange={(value) =>
                        setFormData({
                          ...formData,
                          subcategory: value === SUBCATEGORY_NONE ? '' : value,
                        })
                      }
                      disabled={loading}
                    >
                      <SelectTrigger id="subcategory">
                        <SelectValue placeholder="Select subcategory" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={SUBCATEGORY_NONE}>None</SelectItem>
                        {PRODUCT_SUBCATEGORIES.map((sub) => (
                          <SelectItem key={sub} value={sub}>
                            {sub}
                          </SelectItem>
                        ))}
                        {formData.subcategory &&
                          !isStandardSubcategory(formData.subcategory) && (
                            <SelectItem value={formData.subcategory}>
                              {`Legacy: ${formData.subcategory}`}
                            </SelectItem>
                          )}
                      </SelectContent>
                    </Select>
                  </div>
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
                <div className="space-y-2">
                  <Label htmlFor="boxes_per_product">
                    Number of boxes (optional)
                  </Label>
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
                    Used in installation calculation. Leave blank if this product is not boxed.
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
                        {[...optionalExtras].sort((a, b) => a.name.localeCompare(b.name)).map((extra) => (
                          <div
                            key={extra.id}
                            className="flex items-center space-x-2 p-3 border rounded-md hover:bg-muted/50 cursor-pointer"
                            onClick={() => toggleExtra(extra.id)}
                          >
                            <input
                              type="checkbox"
                              checked={selectedExtras.includes(extra.id)}
                              readOnly
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
                <CardHeader>
                  <CardTitle>Configurator icon</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <ImageUpload
                    value={formData.image_url}
                    onChange={(url) => setFormData({ ...formData, image_url: url })}
                    disabled={loading}
                    label="Configurator icon"
                  />
                  <p className="text-xs text-muted-foreground">
                    Small image shown as the toggle button in Configurator Extras when allow in configurator is enabled.
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

            {!formData.is_extra && (
              <>
                {/* Product Spec Sheet */}
                <Card>
                  <CardHeader>
                    <CardTitle>Product Spec Sheet</CardTitle>
                    <p className="text-sm font-normal text-muted-foreground">
                      Dimensions and floor plan for quote spec sheets
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="size">Size</Label>
                        <Input
                          id="size"
                          value={formData.size}
                          onChange={(e) =>
                            setFormData({ ...formData, size: e.target.value })
                          }
                          placeholder="e.g. 3m x 4m, 12ft x 16ft"
                          disabled={loading}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="height">Height</Label>
                        <Input
                          id="height"
                          value={formData.height}
                          onChange={(e) =>
                            setFormData({ ...formData, height: e.target.value })
                          }
                          placeholder="e.g. 2.4m, 8ft to eaves"
                          disabled={loading}
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="width">Width (numeric)</Label>
                        <Input
                          id="width"
                          type="number"
                          step="0.01"
                          value={formData.width}
                          onChange={(e) =>
                            setFormData({ ...formData, width: e.target.value })
                          }
                          placeholder="e.g. 3.0"
                          disabled={loading}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="length">Length (numeric)</Label>
                        <Input
                          id="length"
                          type="number"
                          step="0.01"
                          value={formData.length}
                          onChange={(e) =>
                            setFormData({ ...formData, length: e.target.value })
                          }
                          placeholder="e.g. 4.0"
                          disabled={loading}
                        />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label>Floor Plan Image</Label>
                      <ImageUpload
                        value={formData.floor_plan_url}
                        onChange={(url) =>
                          setFormData({ ...formData, floor_plan_url: url })
                        }
                        disabled={loading}
                      />
                      <p className="text-xs text-muted-foreground">
                        Upload a floor plan diagram to include in product spec sheets
                      </p>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Configurator Footprint</CardTitle>
                    <p className="text-sm font-normal text-muted-foreground">
                      Used by the quote configurator layout grid. Required for configurator items.
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="configurator_width">
                          Configurator Width (numeric)
                          {isConfiguratorCategory && <span className="text-destructive"> *</span>}
                        </Label>
                        <Input
                          id="configurator_width"
                          type="number"
                          step="0.01"
                          value={formData.configurator_width}
                          onChange={(e) =>
                            setFormData({ ...formData, configurator_width: e.target.value })
                          }
                          placeholder="e.g. 3.0"
                          disabled={loading}
                          required={isConfiguratorCategory}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="configurator_length">
                          Configurator Length (numeric)
                          {isConfiguratorCategory && <span className="text-destructive"> *</span>}
                        </Label>
                        <Input
                          id="configurator_length"
                          type="number"
                          step="0.01"
                          value={formData.configurator_length}
                          onChange={(e) =>
                            setFormData({ ...formData, configurator_length: e.target.value })
                          }
                          placeholder="e.g. 4.0"
                          disabled={loading}
                          required={isConfiguratorCategory}
                        />
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      These are separate from the spec sheet dimensions so the configurator uses a dedicated
                      footprint.
                    </p>
                    {isConfiguratorCategory && !formData.is_extra && (
                      <div className="space-y-3">
                        <div className="flex items-center gap-2">
                          <input
                            id="configurator_is_corner_box"
                            type="checkbox"
                            checked={formData.configurator_is_corner_box}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                configurator_is_corner_box: e.target.checked,
                                configurator_connection_profile: e.target.checked
                                  ? formData.configurator_connection_profile
                                  : '',
                                configurator_front_face: e.target.checked ? '' : formData.configurator_front_face,
                              })
                            }
                            className="h-4 w-4"
                            disabled={loading}
                          />
                          <Label htmlFor="configurator_is_corner_box">
                            Corner box (fixed orientation — no rotation on the configurator canvas)
                          </Label>
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            id="configurator_is_starter_box"
                            type="checkbox"
                            checked={formData.configurator_is_starter_box}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                configurator_is_starter_box: e.target.checked,
                              })
                            }
                            className="h-4 w-4"
                            disabled={loading}
                          />
                          <Label htmlFor="configurator_is_starter_box">
                            Starter box (users must place this product before adding other configurator items)
                          </Label>
                        </div>
                      </div>
                    )}
                    {isCornerConfiguratorProduct && (
                      <>
                        <div className="space-y-2">
                          <Label htmlFor="configurator_connection_profile">
                            Corner Handedness
                            <span className="text-destructive"> *</span>
                          </Label>
                          <Select
                            value={formData.configurator_connection_profile || CONFIGURATOR_CONNECTION_PROFILE_NONE}
                            onValueChange={(value) =>
                              setFormData({
                                ...formData,
                                configurator_connection_profile:
                                  value === CONFIGURATOR_CONNECTION_PROFILE_NONE
                                    ? ''
                                    : (value as ConfiguratorConnectionProfile),
                              })
                            }
                            disabled={loading}
                          >
                            <SelectTrigger id="configurator_connection_profile">
                              <SelectValue placeholder="Choose left or right hand" />
                            </SelectTrigger>
                            <SelectContent>
                              {CONFIGURATOR_CONNECTION_PROFILES.map((profile) => (
                                <SelectItem key={profile} value={profile}>
                                  {CONFIGURATOR_CONNECTION_PROFILE_LABELS[profile]}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <p className="text-xs text-muted-foreground">
                            Use separate products for each orientation (e.g. tall 3.6 x 4.9 vs wide 4.9 x 3.6). The
                            shorter edge is the joinable front section; the remainder is the fixed exposed front (e.g.
                            1.3m on a 4.9m side).
                          </p>
                        </div>
                        <div className="space-y-2">
                          <Label>Configurator Front Side</Label>
                          <div className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
                            Derived from the corner handedness and footprint dimensions. Pick the product variant that
                            matches how the box sits on the layout; do not rotate it on the canvas.
                          </div>
                        </div>
                      </>
                    )}
                    {isConfiguratorCategory && !formData.is_extra && !isCornerConfiguratorProduct && (
                      <div className="space-y-2">
                        <Label htmlFor="configurator_front_face">
                          Configurator Front Side
                          {requiresConfiguratorFrontFace && <span className="text-destructive"> *</span>}
                        </Label>
                        <Select
                          value={formData.configurator_front_face || CONFIGURATOR_FRONT_FACE_NONE}
                          onValueChange={(value) =>
                            setFormData({
                              ...formData,
                              configurator_front_face:
                                value === CONFIGURATOR_FRONT_FACE_NONE
                                  ? ''
                                  : (value as ConfiguratorFrontFace),
                            })
                          }
                          disabled={loading}
                        >
                          <SelectTrigger id="configurator_front_face">
                            <SelectValue placeholder="Choose the front side" />
                          </SelectTrigger>
                          <SelectContent>
                            {!requiresConfiguratorFrontFace && (
                              <SelectItem value={CONFIGURATOR_FRONT_FACE_NONE}>
                                Default legacy front
                              </SelectItem>
                            )}
                            {allowedConfiguratorFrontFaces.map((face) => (
                              <SelectItem key={face} value={face}>
                                {CONFIGURATOR_FRONT_FACE_LABELS[face]}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <p className="text-xs text-muted-foreground">
                          Choose which edge is the customer-facing front (top/bottom use width; left/right use length).
                          New boxes will rotate so this front points toward the bottom of the layout by default.
                        </p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </>
            )}

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
              <Button
                type="button"
                variant="secondary"
                onClick={handleSaveAndRecalculate}
                disabled={loading}
              >
                Save & Recalculate
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
