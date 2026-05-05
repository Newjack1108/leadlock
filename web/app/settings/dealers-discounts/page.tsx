'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  getApiErrorDetail,
  getDealersForSettings,
  getDealerDiscountPolicyForAdmin,
  getDiscountTemplates,
  updateDealerDiscountPolicyForAdmin,
} from '@/lib/api';
import type {
  DealerDiscountPolicyAdminPayload,
  DealerSummary,
  DiscountTemplate,
} from '@/lib/types';
import { toast } from 'sonner';
import api from '@/lib/api';

export default function DealerDiscountSettingsPage() {
  const router = useRouter();
  const [userRole, setUserRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [dealers, setDealers] = useState<DealerSummary[]>([]);
  const [discounts, setDiscounts] = useState<DiscountTemplate[]>([]);
  const [selectedDealerId, setSelectedDealerId] = useState<number | null>(null);
  const [policy, setPolicy] = useState<DealerDiscountPolicyAdminPayload>({
    mode: 'TEMPLATE',
    allow_fixed_amount: false,
    allow_percentage: false,
    max_discount_percentage: null,
    max_discount_amount: null,
    allowed_discount_template_ids: [],
  });

  useEffect(() => {
    const loadInitial = async () => {
      try {
        const me = await api.get('/api/auth/me');
        const role = me.data?.role ?? null;
        setUserRole(role);
        if (role !== 'DIRECTOR') {
          setLoading(false);
          return;
        }
        const [dealerList, activeDiscounts] = await Promise.all([
          getDealersForSettings(),
          getDiscountTemplates(true),
        ]);
        setDealers(dealerList);
        setDiscounts(activeDiscounts);
        if (dealerList.length) setSelectedDealerId(dealerList[0].id);
      } catch (err: unknown) {
        toast.error(getApiErrorDetail(err) || 'Failed to load dealer discount settings');
      } finally {
        setLoading(false);
      }
    };
    void loadInitial();
  }, []);

  useEffect(() => {
    if (!selectedDealerId || userRole !== 'DIRECTOR') return;
    let cancelled = false;
    const loadPolicy = async () => {
      try {
        const res = await getDealerDiscountPolicyForAdmin(selectedDealerId);
        if (cancelled) return;
        setPolicy({
          mode: res.mode,
          allow_fixed_amount: !!res.allow_fixed_amount,
          allow_percentage: !!res.allow_percentage,
          max_discount_percentage: res.max_discount_percentage ?? null,
          max_discount_amount: res.max_discount_amount ?? null,
          allowed_discount_template_ids: res.allowed_discount_template_ids ?? [],
        });
      } catch (err: unknown) {
        if (!cancelled) toast.error(getApiErrorDetail(err) || 'Failed to load dealer policy');
      }
    };
    void loadPolicy();
    return () => {
      cancelled = true;
    };
  }, [selectedDealerId, userRole]);

  const selectedDealer = useMemo(
    () => dealers.find((dealer) => dealer.id === selectedDealerId) ?? null,
    [dealers, selectedDealerId]
  );

  const toggleAllowedDiscount = (discountId: number, checked: boolean) => {
    setPolicy((prev) => ({
      ...prev,
      allowed_discount_template_ids: checked
        ? Array.from(new Set([...prev.allowed_discount_template_ids, discountId]))
        : prev.allowed_discount_template_ids.filter((id) => id !== discountId),
    }));
  };

  const savePolicy = async () => {
    if (!selectedDealerId) return;
    try {
      setSaving(true);
      const saved = await updateDealerDiscountPolicyForAdmin(selectedDealerId, policy);
      setPolicy({
        mode: saved.mode,
        allow_fixed_amount: saved.allow_fixed_amount,
        allow_percentage: saved.allow_percentage,
        max_discount_percentage: saved.max_discount_percentage ?? null,
        max_discount_amount: saved.max_discount_amount ?? null,
        allowed_discount_template_ids: saved.allowed_discount_template_ids ?? [],
      });
      toast.success('Dealer discount policy saved');
    } catch (err: unknown) {
      toast.error(getApiErrorDetail(err) || 'Failed to save dealer policy');
    } finally {
      setSaving(false);
    }
  };

  if (userRole !== null && userRole !== 'DIRECTOR') {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">
            Access denied. This page is for directors only.
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 sm:px-6 py-8 space-y-6">
        <div>
          <h1 className="text-3xl font-semibold mb-2">Dealer Discounts</h1>
          <p className="text-muted-foreground">
            Configure which discount templates each dealer can apply in the dealer quote portal.
          </p>
        </div>

        {loading ? (
          <div className="text-muted-foreground">Loading...</div>
        ) : (
          <>
            <Card>
              <CardHeader>
                <CardTitle>Select Dealer</CardTitle>
                <CardDescription>Choose which dealer to configure.</CardDescription>
              </CardHeader>
              <CardContent>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs"
                  value={selectedDealerId ?? ''}
                  onChange={(e) => setSelectedDealerId(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="" disabled>
                    Select a dealer
                  </option>
                  {dealers.map((dealer) => (
                    <option key={dealer.id} value={dealer.id}>
                      {dealer.company_name || dealer.name} (ID: {dealer.id})
                    </option>
                  ))}
                </select>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Discount Policy</CardTitle>
                <CardDescription>
                  {selectedDealer
                    ? `Configure ${selectedDealer.company_name || selectedDealer.name}`
                    : 'Select a dealer first'}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="max-pct">Max discount percentage</Label>
                    <Input
                      id="max-pct"
                      type="number"
                      step="0.01"
                      value={policy.max_discount_percentage ?? ''}
                      onChange={(e) =>
                        setPolicy((prev) => ({
                          ...prev,
                          max_discount_percentage:
                            e.target.value === '' ? null : Number(e.target.value),
                        }))
                      }
                      disabled={!selectedDealerId || saving}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="max-amount">Max discount amount (£)</Label>
                    <Input
                      id="max-amount"
                      type="number"
                      step="0.01"
                      value={policy.max_discount_amount ?? ''}
                      onChange={(e) =>
                        setPolicy((prev) => ({
                          ...prev,
                          max_discount_amount: e.target.value === '' ? null : Number(e.target.value),
                        }))
                      }
                      disabled={!selectedDealerId || saving}
                    />
                  </div>
                </div>

                <div className="flex flex-col gap-2">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={policy.allow_percentage}
                      onChange={(e) =>
                        setPolicy((prev) => ({ ...prev, allow_percentage: e.target.checked }))
                      }
                      disabled={!selectedDealerId || saving}
                    />
                    Allow percentage discounts
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={policy.allow_fixed_amount}
                      onChange={(e) =>
                        setPolicy((prev) => ({ ...prev, allow_fixed_amount: e.target.checked }))
                      }
                      disabled={!selectedDealerId || saving}
                    />
                    Allow fixed amount discounts
                  </label>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Allowed Discount Templates</CardTitle>
                <CardDescription>
                  Dealers can only use templates checked below.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {!discounts.length && (
                  <p className="text-sm text-muted-foreground">
                    No active discount templates available. Create them in Discounts & Giveaways first.
                  </p>
                )}
                {discounts.map((discount) => {
                  const checked = policy.allowed_discount_template_ids.includes(discount.id);
                  return (
                    <label key={discount.id} className="flex items-center justify-between gap-3 text-sm">
                      <span className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => toggleAllowedDiscount(discount.id, e.target.checked)}
                          disabled={!selectedDealerId || saving}
                        />
                        {discount.name}
                      </span>
                      <span className="text-muted-foreground">
                        {discount.discount_type === 'PERCENTAGE'
                          ? `${discount.discount_value}%`
                          : `£${discount.discount_value}`}{' '}
                        · {discount.scope === 'PRODUCT' ? 'Building items' : 'Entire quote'}
                      </span>
                    </label>
                  );
                })}
              </CardContent>
            </Card>

            <div className="flex justify-end">
              <Button onClick={savePolicy} disabled={!selectedDealerId || saving}>
                {saving ? 'Saving...' : 'Save dealer discount policy'}
              </Button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
