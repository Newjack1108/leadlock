'use client';

import { useState, useEffect, Suspense, useMemo, useCallback, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  createQuote,
  getProducts,
  getProduct,
  getOptionalExtras,
  getCompanySettings,
  getDiscountTemplates,
  estimateDeliveryInstall,
  getQuote,
  getLeadQuotes,
  applyQualifiedToQuotedTransition,
} from '@/lib/api';
import api from '@/lib/api';
import { filterQuoteCatalogProducts } from '@/lib/quoteCatalogProducts';
import {
  buildUpdateDraftPayload,
  quoteItemsToFormItems,
  DRAFT_PLACEHOLDER_LINE_DESCRIPTION,
  isPlaceholderOnlyDraftItems,
} from '@/lib/quoteDraftPayload';
import DraftConfiguratorCallout from '@/components/configurator/DraftConfiguratorCallout';
import DraftConfiguratorLink from '@/components/configurator/DraftConfiguratorLink';
import QuoteDisplayedOptionalExtrasSection from '@/components/quotes/QuoteDisplayedOptionalExtrasSection';
import {
  optionalExtraIdSetFromList,
  isRootQuoteLevelOptionalExtraLine,
  buildQuoteLevelOptionalExtraLine,
  rootBuildingProductNumberAtIndex,
} from '@/lib/quoteFormOptionalExtra';
import { prefetchProductDetailsForQuoteItems } from '@/lib/prefetchQuoteProductDetails';
import {
  allowsNegativeUnitPrice,
  calculateTotalQuoteInstallationHours,
  DELIVERY_INSTALL_LEGACY_DESCRIPTION,
  DELIVERY_ONLY_DESCRIPTION,
  isCustomQuoteLine,
  isDeliveryOrInstallItem,
  isValidQuoteLine,
  lineInstallationHoursPerUnit,
  parseQuoteLineUnitPrice,
  quoteLineTotal,
} from '@/lib/quoteInstallHours';
import { calculateTotalQuoteDeliveryBoxes } from '@/lib/quoteDeliveryBoxes';
import { useDraftAutosave } from '@/hooks/useDraftAutosave';
import {
  Customer,
  Product,
  Quote,
  QuoteItemCreate,
  DiscountTemplate,
  QuoteTemperature,
  QuoteFulfillmentMethod,
  DeliveryInstallEstimateResponse,
  isDiscountTemplateExpired,
  QuoteDiscount,
} from '@/lib/types';
import Link from 'next/link';
import { toast } from 'sonner';
import DeliveryInstallEstimatePanel from '@/components/quotes/DeliveryInstallEstimatePanel';
import FulfillmentMethodField from '@/components/quotes/FulfillmentMethodField';
import DeliveryLocationFields from '@/components/quotes/DeliveryLocationFields';
import { Plus, Trash2, ArrowLeft, X, ChevronDown, ChevronUp, FileSearch } from 'lucide-react';

function hasDeliveryInstallLine(items: QuoteItemCreate[]): boolean {
  return items.some(isDeliveryOrInstallItem);
}

// Default terms and conditions constant (fallback if not set in company settings)
const DEFAULT_TERMS_AND_CONDITIONS = `Key Terms Summary (For Quotations)

Orders & Payment
All orders are subject to our full Terms & Conditions.
A non-refundable deposit is required to secure your order.
Ownership of goods passes only once full payment has been received.

Prices
All prices are Ex VAT @ 20%. VAT will be added at 20% with a breakdown on the quote.
Delivery and installation are not included unless clearly specified.
Drawings and plans are for guidance only.

Delivery
Delivery dates are approximate and not guaranteed.
Delivery is to roadside only unless agreed otherwise.
Goods must be inspected on delivery; damage must be reported within 24 hours.

Installation
Installation (if included) requires a flat, level, suitable base and clear access.
Abortive visits due to poor access or base issues may incur charges.

Cancellations
Standard goods may be cancelled within 14 days of delivery.
Bespoke, made-to-order, or personalised items are non-refundable.
No cancellations once goods are assembled, altered, or used.

Planning & Use
Customers are responsible for planning permission where required.
Natural timber characteristics (knots, cracks, colour variation) are normal.

Warranty & Liability
12-month parts-only warranty.
We are not liable for third-party installation, access damage, weather events, or indirect losses.

Full Terms & Conditions available on request or on our website.
Statutory consumer rights are not affected.`;

function CreateQuoteContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const customerId = searchParams.get('customer_id') ? parseInt(searchParams.get('customer_id')!) : null;
  const leadId = searchParams.get('lead_id') ? parseInt(searchParams.get('lead_id')!) : null;
  const draftIdParsed = searchParams.get('draft_id') ? parseInt(searchParams.get('draft_id')!, 10) : NaN;
  const draftIdFromUrl = Number.isFinite(draftIdParsed) ? draftIdParsed : null;

  const [loading, setLoading] = useState(false);
  const [draftQuoteId, setDraftQuoteId] = useState<number | null>(null);
  /** URL draft_id is authoritative when state resets after router.replace */
  const activeDraftQuoteId = draftQuoteId ?? draftIdFromUrl;
  const syncedDraftBaselineRef = useRef<string | null>(null);
  const [pageLoading, setPageLoading] = useState(true);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [items, setItems] = useState<QuoteItemCreate[]>([
    {
      description: '',
      quantity: 1,
      unit_price: 0,
      is_custom: false,
      sort_order: 0,
    },
  ]);
  const [validUntil, setValidUntil] = useState('');
  const [termsAndConditions, setTermsAndConditions] = useState('');
  const [notes, setNotes] = useState('');
  const [temperature, setTemperature] = useState<QuoteTemperature | ''>(QuoteTemperature.WARM);
  const [includeSpecSheets, setIncludeSpecSheets] = useState(false);
  const [includeAvailableOptionalExtras, setIncludeAvailableOptionalExtras] = useState(false);
  const [includeDeliveryInstallationContactNote, setIncludeDeliveryInstallationContactNote] =
    useState(false);
  const [fulfillmentMethod, setFulfillmentMethod] = useState<QuoteFulfillmentMethod>('DELIVERY');
  const [useAlternateDeliveryAddress, setUseAlternateDeliveryAddress] = useState(false);
  const [deliveryAddressLine1, setDeliveryAddressLine1] = useState('');
  const [deliveryAddressLine2, setDeliveryAddressLine2] = useState('');
  const [deliveryCity, setDeliveryCity] = useState('');
  const [deliveryCounty, setDeliveryCounty] = useState('');
  const [deliveryPostcode, setDeliveryPostcode] = useState('');
  const [deliveryCountry, setDeliveryCountry] = useState('United Kingdom');
  const [deliveryLocationNotes, setDeliveryLocationNotes] = useState('');
  const [depositAmount, setDepositAmount] = useState<number | ''>('');
  const [companySettings, setCompanySettings] = useState<any>(null);
  const [availableDiscounts, setAvailableDiscounts] = useState<DiscountTemplate[]>([]);
  const [selectedDiscountIds, setSelectedDiscountIds] = useState<number[]>([]);
  const [productDetails, setProductDetails] = useState<Record<number, Product>>({});
  const [allOptionalExtras, setAllOptionalExtras] = useState<Product[]>([]);
  const [displayedOptionalExtraIds, setDisplayedOptionalExtraIds] = useState<number[]>([]);
  const [extraPickerOpen, setExtraPickerOpen] = useState(false);
  const [extraPickerFilter, setExtraPickerFilter] = useState('');
  const [termsExpanded, setTermsExpanded] = useState(false);
  const [deliveryEstimate, setDeliveryEstimate] = useState<DeliveryInstallEstimateResponse | null>(null);
  const [deliveryEstimateLoading, setDeliveryEstimateLoading] = useState(false);
  const [deliveryEstimateError, setDeliveryEstimateError] = useState<string | null>(null);
  const [deliveryEstimateMode, setDeliveryEstimateMode] = useState<'full' | 'delivery_only'>('full');

  const optionalExtraIds = useMemo(
    () => optionalExtraIdSetFromList(allOptionalExtras),
    [allOptionalExtras]
  );

  const filteredPickerExtras = useMemo(() => {
    const q = extraPickerFilter.trim().toLowerCase();
    const sorted = [...allOptionalExtras].sort((a, b) => a.name.localeCompare(b.name));
    if (!q) return sorted;
    return sorted.filter((e) => e.name.toLowerCase().includes(q));
  }, [allOptionalExtras, extraPickerFilter]);

  useEffect(() => {
    if (customerId) {
      if (!leadId) {
        toast.error('Please select an enquiry (lead) to create a quote from');
        router.push(`/customers/${customerId}`);
        setPageLoading(false);
        return;
      }
      fetchCustomer();
      fetchProducts();
      fetchOptionalExtras();
      fetchDefaultTerms();
      fetchCompanySettings();
      fetchDiscounts();
      // Set default valid until to 30 days from now
      const date = new Date();
      date.setDate(date.getDate() + 30);
      setValidUntil(date.toISOString().split('T')[0]);
    } else {
      setPageLoading(false);
      toast.error('Customer ID is required');
      router.push('/customers');
    }
  }, [customerId, leadId]);

  const fetchCustomer = async () => {
    if (!customerId) return;
    try {
      const response = await api.get(`/api/customers/${customerId}`);
      setCustomer(response.data);
    } catch (error: any) {
      toast.error('Failed to load customer');
      if (error.response?.status === 401) {
        router.push('/login');
      } else if (error.response?.status === 404) {
        router.push('/customers');
      }
    } finally {
      setPageLoading(false);
    }
  };

  const fetchProducts = async () => {
    try {
      const response = await getProducts();
      // Only main products in dropdown; extras are added via Optional Extras section per product
      setProducts(filterQuoteCatalogProducts(response));
    } catch (error) {
      console.error('Failed to load products');
    }
  };

  const fetchOptionalExtras = async () => {
    try {
      const list = await getOptionalExtras();
      setAllOptionalExtras(list);
    } catch {
      console.error('Failed to load optional extras');
    }
  };

  const fetchDefaultTerms = async () => {
    try {
      const settings = await getCompanySettings();
      if (settings?.default_terms_and_conditions) {
        setTermsAndConditions(settings.default_terms_and_conditions);
      } else {
        setTermsAndConditions(DEFAULT_TERMS_AND_CONDITIONS);
      }
    } catch (error) {
      // If settings don't exist or error, use hardcoded default
      console.error('Failed to load company settings, using default terms');
      setTermsAndConditions(DEFAULT_TERMS_AND_CONDITIONS);
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

  const fetchDiscounts = async () => {
    try {
      const discounts = await getDiscountTemplates(true); // Only active discounts
      setAvailableDiscounts(discounts);
    } catch (error) {
      console.error('Failed to load discounts');
    }
  };

  const addItem = () => {
    setItems([
      ...items,
      {
        description: '',
        quantity: 1,
        unit_price: 0,
        is_custom: false,
        sort_order: items.length,
        parent_index: undefined,
      },
    ]);
  };

  const removeItem = (index: number) => {
    const newItems = items
      .filter((_, i) => i !== index)
      .map((item, i) => {
        let parent_index = item.parent_index;
        if (parent_index !== undefined && parent_index !== null) {
          if (parent_index === index) parent_index = undefined;
          else if (parent_index > index) parent_index = parent_index - 1;
        }
        return { ...item, sort_order: i, parent_index };
      });
    setItems(newItems);
  };

  const updateItem = async (index: number, field: keyof QuoteItemCreate, value: any) => {
    const newItems = [...items];
    if (field === 'product_id') {
      if (value === 'custom' || !value) {
        newItems[index] = {
          ...newItems[index],
          product_id: undefined,
          is_custom: true,
        };
        setItems(newItems);
        return;
      }
      const productId = parseInt(value, 10);
      const product = products.find((p) => p.id === productId);
      if (product) {
        newItems[index] = {
          ...newItems[index],
          product_id: product.id,
          description: product.name,
          unit_price: Math.round(Number(product.base_price) * 100) / 100,
          is_custom: false,
          installation_hours: undefined,
        };
        setItems(newItems);
        try {
          const detailed = await getProduct(productId);
          setProductDetails((prev) => ({ ...prev, [productId]: detailed }));
        } catch {
          setProductDetails((prev) => ({ ...prev, [productId]: product }));
        }
        return;
      }
    }
    newItems[index] = { ...newItems[index], [field]: value };
    setItems(newItems);
  };

  const addOptionalExtra = (parentIndex: number, extra: Product) => {
    const parentItem = items[parentIndex];
    const parentProduct = getSelectedProduct(parentItem);
    const parentQty = Number(parentItem?.quantity) || 1;
    const boxesPerProduct = parentProduct?.boxes_per_product ?? 1;
    const quantity =
      extra.unit === 'Per Box' ? parentQty * boxesPerProduct : parentQty;

    const newItem: QuoteItemCreate = {
      product_id: extra.id,
      description: extra.name,
      quantity,
      unit_price: Math.round(Number(extra.base_price) * 100) / 100,
      is_custom: false,
      sort_order: parentIndex + 1,
      parent_index: parentIndex,
    };
    const newItems = [...items];
    newItems.splice(parentIndex + 1, 0, newItem);
    setItems(newItems.map((it, i) => ({ ...it, sort_order: i })));
  };

  const addQuoteLevelOptionalExtra = (extra: Product) => {
    const newLine = buildQuoteLevelOptionalExtraLine(extra);
    setProductDetails((prev) => ({ ...prev, [extra.id]: extra }));
    setItems((prev) => {
      const next = [...prev, { ...newLine, sort_order: prev.length }];
      return next.map((it, i) => ({ ...it, sort_order: i }));
    });
    setExtraPickerOpen(false);
    setExtraPickerFilter('');
  };

  const getSelectedProduct = (item: QuoteItemCreate) => {
    if (!item.product_id) return null;
    return productDetails[item.product_id] ?? products.find((p) => p.id === item.product_id) ?? null;
  };

  const calculateTotalInstallationHours = (): number =>
    calculateTotalQuoteInstallationHours(items, optionalExtraIds, getSelectedProduct);

  const calculateTotalDeliveryBoxes = (): number =>
    calculateTotalQuoteDeliveryBoxes(items, optionalExtraIds, getSelectedProduct);

  const calculateInstallCostForLine = (item: QuoteItemCreate) => {
    const product = getSelectedProduct(item);
    const perUnit = lineInstallationHoursPerUnit(item, product);
    if (perUnit <= 0 || !companySettings?.hourly_install_rate) return null;
    return perUnit * companySettings.hourly_install_rate;
  };

  useEffect(() => {
    const postcode = useAlternateDeliveryAddress
      ? deliveryPostcode.trim()
      : (customer?.postcode?.trim() ?? '');
    const installHours = calculateTotalInstallationHours();
    const deliveryOnly = deliveryEstimateMode === 'delivery_only';
    const boxCount = deliveryOnly ? calculateTotalDeliveryBoxes() : undefined;
    if (!postcode || (!deliveryOnly && installHours <= 0)) {
      setDeliveryEstimate(null);
      setDeliveryEstimateError(null);
      setDeliveryEstimateLoading(false);
      return;
    }
    let cancelled = false;
    setDeliveryEstimateLoading(true);
    setDeliveryEstimateError(null);
    estimateDeliveryInstall(postcode, deliveryOnly ? 0 : installHours, {
      deliveryOnly,
      numberOfBoxes: boxCount,
    })
      .then((data) => {
        if (!cancelled) {
          setDeliveryEstimate(data);
          setDeliveryEstimateError(null);
        }
      })
      .catch((err: any) => {
        if (!cancelled) {
          setDeliveryEstimate(null);
          const msg = err.response?.data?.detail || 'Failed to load delivery estimate';
          setDeliveryEstimateError(Array.isArray(msg) ? msg[0]?.msg ?? String(msg) : msg);
        }
      })
      .finally(() => {
        if (!cancelled) setDeliveryEstimateLoading(false);
      });
    return () => { cancelled = true; };
  }, [customer?.postcode, useAlternateDeliveryAddress, deliveryPostcode, items, productDetails, products, deliveryEstimateMode]);

  const addDeliveryInstallToQuote = () => {
    if (!deliveryEstimate) return;
    const totalCost = deliveryEstimate.cost_total ?? 0;
    if (totalCost <= 0) {
      toast.error('No delivery or installation costs to add');
      return;
    }
    const deliveryOnly = deliveryEstimateMode === 'delivery_only';
    const trips = deliveryOnly ? (deliveryEstimate.delivery_trips ?? 1) : 1;
    const unitPrice =
      trips > 1
        ? Math.round((totalCost / trips) * 100) / 100
        : Math.round(totalCost * 100) / 100;
    const newItems: QuoteItemCreate[] = [...items];
    newItems.push({
      description: deliveryOnly ? DELIVERY_ONLY_DESCRIPTION : DELIVERY_INSTALL_LEGACY_DESCRIPTION,
      quantity: trips,
      unit_price: unitPrice,
      is_custom: true,
      sort_order: items.length,
      line_type: 'DELIVERY',
    });
    setItems(newItems.map((it, i) => ({ ...it, sort_order: i })));
    toast.success(deliveryOnly ? 'Delivery only added to quote' : 'Delivery & Installation added to quote');
  };

  const removeDeliveryInstallFromQuote = () => {
    const newItems = items
      .filter((item) => !isDeliveryOrInstallItem(item))
      .map((it, i) => ({ ...it, sort_order: i }));
    setItems(newItems);
    toast.success('Delivery line removed from quote');
  };

  const calculateSubtotal = () => {
    return items.reduce((sum, item) => sum + quoteLineTotal(item), 0);
  };

  const calculateTotal = () => {
    // Note: Discounts are calculated on the backend
    // This is just the subtotal for preview
    return calculateSubtotal();
  };

  const calculateTotalIncVat = () => calculateTotal() * 1.2;

  const calculateDefaultDeposit = () => {
    return calculateTotalIncVat() * 0.5;
  };

  const getDepositAmount = () => {
    if (depositAmount === '') {
      return calculateDefaultDeposit();
    }
    return Number(depositAmount);
  };

  const getBalanceAmount = () => {
    const totalIncVat = calculateTotalIncVat();
    const deposit = getDepositAmount();
    return Math.max(0, totalIncVat - deposit);
  };

  const buildDraftPayload = useCallback(
    () =>
      buildUpdateDraftPayload({
        items,
        validUntil,
        termsAndConditions,
        notes,
        temperature,
        includeSpecSheets,
        includeAvailableOptionalExtras,
        displayedOptionalExtraIds,
        includeDeliveryInstallationContactNote,
        fulfillmentMethod,
        useAlternateDeliveryAddress,
        deliveryAddressLine1,
        deliveryAddressLine2,
        deliveryCity,
        deliveryCounty,
        deliveryPostcode,
        deliveryCountry,
        deliveryLocationNotes,
        depositAmount,
        selectedDiscountIds,
      }),
    [
      items,
      validUntil,
      termsAndConditions,
      notes,
      temperature,
      includeSpecSheets,
      includeAvailableOptionalExtras,
      displayedOptionalExtraIds,
      includeDeliveryInstallationContactNote,
      fulfillmentMethod,
      useAlternateDeliveryAddress,
      deliveryAddressLine1,
      deliveryAddressLine2,
      deliveryCity,
      deliveryCounty,
      deliveryPostcode,
      deliveryCountry,
      deliveryLocationNotes,
      depositAmount,
      selectedDiscountIds,
    ]
  );

  const formSignature = useMemo(
    () =>
      JSON.stringify({
        items,
        validUntil,
        termsAndConditions,
        notes,
        temperature,
        includeSpecSheets,
        includeAvailableOptionalExtras,
        displayedOptionalExtraIds,
        includeDeliveryInstallationContactNote,
        fulfillmentMethod,
        useAlternateDeliveryAddress,
        deliveryAddressLine1,
        deliveryAddressLine2,
        deliveryCity,
        deliveryCounty,
        deliveryPostcode,
        deliveryCountry,
        deliveryLocationNotes,
        depositAmount,
        selectedDiscountIds,
      }),
    [
      items,
      validUntil,
      termsAndConditions,
      notes,
      temperature,
      includeSpecSheets,
      includeAvailableOptionalExtras,
      displayedOptionalExtraIds,
      includeDeliveryInstallationContactNote,
      fulfillmentMethod,
      useAlternateDeliveryAddress,
      deliveryAddressLine1,
      deliveryAddressLine2,
      deliveryCity,
      deliveryCounty,
      deliveryPostcode,
      deliveryCountry,
      deliveryLocationNotes,
      depositAmount,
      selectedDiscountIds,
    ]
  );

  const { saveStatus, flushDraft, markClean, isDirty } = useDraftAutosave({
    quoteId: activeDraftQuoteId,
    enabled: !!activeDraftQuoteId && !!customer,
    debounceMs: 1500,
    buildPayload: buildDraftPayload,
    formSignature,
  });

  const draftStorageKey =
    customerId != null && leadId != null ? `ll-quote-create-${customerId}-${leadId}` : null;

  useEffect(() => {
    if (!customer || !leadId || !customerId || !draftStorageKey) return;

    if (draftIdFromUrl != null) {
      try {
        sessionStorage.setItem(draftStorageKey, String(draftIdFromUrl));
      } catch {
        /* ignore */
      }
    }

    if (draftIdFromUrl != null && draftQuoteId === draftIdFromUrl) {
      const syncKey = `${draftIdFromUrl}:${draftQuoteId}`;
      if (syncedDraftBaselineRef.current !== syncKey) {
        syncedDraftBaselineRef.current = syncKey;
        const t = window.setTimeout(() => markClean(), 0);
        return () => window.clearTimeout(t);
      }
      return;
    }

    if (draftIdFromUrl != null && draftQuoteId !== draftIdFromUrl) {
      let cancelled = false;
      (async () => {
        try {
          const q = await getQuote(draftIdFromUrl);
          if (cancelled) return;
          if (q.status !== 'DRAFT' || q.customer_id !== customer.id || q.lead_id !== leadId) {
            toast.error("This draft doesn't match this customer or enquiry.");
            try {
              sessionStorage.removeItem(draftStorageKey);
            } catch {
              /* ignore */
            }
            router.replace(`/quotes/create?customer_id=${customerId}&lead_id=${leadId}`);
            return;
          }
          setDraftQuoteId(q.id);
          const formItems =
            q.items && q.items.length > 0
              ? quoteItemsToFormItems(q.items)
              : [
                  {
                    description: '',
                    quantity: 1,
                    unit_price: 0,
                    is_custom: false,
                    sort_order: 0,
                  },
                ];
          setItems(formItems);
          const details = await prefetchProductDetailsForQuoteItems(formItems);
          if (Object.keys(details).length > 0) {
            setProductDetails((prev) => ({ ...prev, ...details }));
          }
          if (q.valid_until) {
            setValidUntil(new Date(q.valid_until).toISOString().split('T')[0]);
          } else {
            const d = new Date();
            d.setDate(d.getDate() + 30);
            setValidUntil(d.toISOString().split('T')[0]);
          }
          setTermsAndConditions(q.terms_and_conditions ?? '');
          setNotes(q.notes ?? '');
          setTemperature(q.temperature ?? QuoteTemperature.WARM);
          setIncludeSpecSheets(q.include_spec_sheets ?? false);
          setIncludeAvailableOptionalExtras(q.include_available_optional_extras ?? false);
          setDisplayedOptionalExtraIds(q.displayed_optional_extra_ids ?? []);
          setIncludeDeliveryInstallationContactNote(
            q.include_delivery_installation_contact_note ?? false
          );
          setFulfillmentMethod(q.fulfillment_method ?? 'DELIVERY');
          setUseAlternateDeliveryAddress(q.use_alternate_delivery_address ?? false);
          setDeliveryAddressLine1(q.delivery_address_line1 ?? '');
          setDeliveryAddressLine2(q.delivery_address_line2 ?? '');
          setDeliveryCity(q.delivery_city ?? '');
          setDeliveryCounty(q.delivery_county ?? '');
          setDeliveryPostcode(q.delivery_postcode ?? '');
          setDeliveryCountry(q.delivery_country ?? 'United Kingdom');
          setDeliveryLocationNotes(q.delivery_location_notes ?? '');
          setDepositAmount(q.deposit_amount != null ? Number(q.deposit_amount) : '');
          setSelectedDiscountIds(
            (q.discounts ?? [])
              .filter((d: QuoteDiscount) => d.template_id != null)
              .map((d: QuoteDiscount) => d.template_id!)
          );
          window.setTimeout(() => markClean(), 0);
        } catch {
          if (!cancelled) toast.error('Failed to load draft');
        }
      })();
      return () => {
        cancelled = true;
      };
    }

    if (draftQuoteId != null && draftIdFromUrl == null) {
      router.replace(
        `/quotes/create?customer_id=${customerId}&lead_id=${leadId}&draft_id=${draftQuoteId}`
      );
      return;
    }

    if (draftIdFromUrl == null && draftQuoteId == null) {
      try {
        const stored = sessionStorage.getItem(draftStorageKey);
        if (stored && !Number.isNaN(parseInt(stored, 10))) {
          const sid = parseInt(stored, 10);
          router.replace(`/quotes/create?customer_id=${customerId}&lead_id=${leadId}&draft_id=${sid}`);
          return;
        }
      } catch {
        /* ignore */
      }
    }

    if (draftIdFromUrl != null || draftQuoteId != null) {
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const leadQuotes = await getLeadQuotes(leadId);
        if (cancelled) return;
        const drafts = leadQuotes.filter(
          (q: Quote) => q.status === 'DRAFT' && q.customer_id === customer.id
        );
        if (drafts.length > 0) {
          const latestDraft = drafts.reduce((a: Quote, b: Quote) => (a.id > b.id ? a : b));
          try {
            sessionStorage.setItem(draftStorageKey, String(latestDraft.id));
          } catch {
            /* ignore */
          }
          router.replace(
            `/quotes/create?customer_id=${customerId}&lead_id=${leadId}&draft_id=${latestDraft.id}`
          );
          return;
        }

        const d = new Date();
        d.setDate(d.getDate() + 30);
        const vu = d.toISOString().split('T')[0];
        const newQuote = await createQuote({
          customer_id: customer.id,
          lead_id: leadId,
          defer_qualified_to_quoted_transition: true,
          items: [
            {
              description: DRAFT_PLACEHOLDER_LINE_DESCRIPTION,
              quantity: 1,
              unit_price: 0,
              is_custom: true,
              sort_order: 0,
            },
          ],
          valid_until: new Date(vu).toISOString(),
          terms_and_conditions: termsAndConditions.trim() || undefined,
          notes: notes.trim() || undefined,
          deposit_amount: depositAmount !== '' ? Number(depositAmount) : undefined,
          temperature: temperature ? temperature : undefined,
          discount_template_ids: selectedDiscountIds.length > 0 ? selectedDiscountIds : undefined,
          include_spec_sheets: includeSpecSheets,
          include_available_optional_extras: includeAvailableOptionalExtras,
          include_delivery_installation_contact_note: includeDeliveryInstallationContactNote,
          fulfillment_method: fulfillmentMethod,
          use_alternate_delivery_address: useAlternateDeliveryAddress,
          delivery_address_line1: useAlternateDeliveryAddress ? deliveryAddressLine1.trim() || undefined : undefined,
          delivery_address_line2: useAlternateDeliveryAddress ? deliveryAddressLine2.trim() || undefined : undefined,
          delivery_city: useAlternateDeliveryAddress ? deliveryCity.trim() || undefined : undefined,
          delivery_county: useAlternateDeliveryAddress ? deliveryCounty.trim() || undefined : undefined,
          delivery_postcode: useAlternateDeliveryAddress ? deliveryPostcode.trim() || undefined : undefined,
          delivery_country: useAlternateDeliveryAddress ? deliveryCountry.trim() || 'United Kingdom' : undefined,
          delivery_location_notes: useAlternateDeliveryAddress ? deliveryLocationNotes.trim() || undefined : undefined,
        });
        if (cancelled) return;
        try {
          sessionStorage.setItem(draftStorageKey, String(newQuote.id));
        } catch {
          /* ignore */
        }
        setDraftQuoteId(newQuote.id);
        if (newQuote.items?.length) {
          const fi = quoteItemsToFormItems(newQuote.items);
          setItems(fi);
          const det = await prefetchProductDetailsForQuoteItems(fi);
          if (Object.keys(det).length > 0) {
            setProductDetails((prev) => ({ ...prev, ...det }));
          }
        }
        router.replace(
          `/quotes/create?customer_id=${customerId}&lead_id=${leadId}&draft_id=${newQuote.id}`
        );
        window.setTimeout(() => markClean(), 0);
      } catch (error: any) {
        const errorMessage =
          error.response?.data?.detail || error.message || 'Failed to start quote draft';
        toast.error(errorMessage);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Intentionally omit form fields: only bootstrap when URL / ids / customer change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customer, leadId, customerId, draftIdFromUrl, draftQuoteId, draftStorageKey, router, markClean]);

  const navigateAway = async (path: string) => {
    try {
      if (activeDraftQuoteId && isDirty()) {
        await flushDraft();
      }
    } catch {
      toast.error('Could not save draft. Try again.');
      return;
    }
    router.push(path);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!customer) {
      toast.error('Customer information is missing');
      return;
    }

    if (!activeDraftQuoteId) {
      toast.error('Quote draft is still initializing. Please wait.');
      return;
    }

    const validItems = items.filter(isValidQuoteLine);

    if (validItems.length === 0) {
      toast.error('Please add at least one valid quote item');
      return;
    }

    if (isPlaceholderOnlyDraftItems(validItems)) {
      toast.error('Please add real quote lines before finishing');
      return;
    }
    if (fulfillmentMethod === 'COLLECTION' && hasDeliveryInstallLine(items)) {
      toast.error('Remove delivery or installation lines before saving a collection quote.');
      return;
    }

    setLoading(true);
    try {
      await flushDraft();
      await applyQualifiedToQuotedTransition(activeDraftQuoteId);
      if (draftStorageKey) {
        try {
          sessionStorage.removeItem(draftStorageKey);
        } catch {
          /* ignore */
        }
      }
      syncedDraftBaselineRef.current = null;
      toast.success('Quote saved');
      router.push(`/quotes/${activeDraftQuoteId}`);
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to save quote';
      toast.error(errorMessage);
      console.error('Quote save error:', error);
    } finally {
      setLoading(false);
    }
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

  if (!customer) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Customer not found</div>
          <div className="text-center mt-4">
            <Button variant="outline" onClick={() => router.push('/customers')}>
              Back to Customers
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 sm:px-6 py-8">
        <div className="mb-6">
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <Button
              variant="ghost"
              type="button"
              onClick={() => navigateAway(`/customers/${customer.id}`)}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Customer
            </Button>
            {activeDraftQuoteId ? (
              <DraftConfiguratorLink quoteId={activeDraftQuoteId} variant="outline" size="sm" />
            ) : null}
          </div>
          <div>
            <h1 className="text-3xl font-semibold">Create New Quote</h1>
            <p className="text-muted-foreground mt-1 flex items-center gap-2 flex-wrap">
              For {customer.name}
              {saveStatus === 'saving' && (
                <span className="text-xs text-muted-foreground">Saving draft…</span>
              )}
              {saveStatus === 'saved' && (
                <span className="text-xs text-emerald-600">Draft saved</span>
              )}
              {saveStatus === 'error' && (
                <span className="text-xs text-destructive">Could not autosave</span>
              )}
              {leadId && (
                <Button variant="outline" size="sm" asChild className="ml-2">
                  <Link href={`/leads/${leadId}`} target="_blank" rel="noopener noreferrer">
                    <FileSearch className="h-4 w-4 mr-2" />
                    View Enquiry
                  </Link>
                </Button>
              )}
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="space-y-6">
            <DraftConfiguratorCallout quoteId={activeDraftQuoteId} items={items} />

            {/* Quote Items */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-4 flex-wrap">
                  <div>
                    <CardTitle>Quote Items</CardTitle>
                    <p className="text-sm text-muted-foreground mt-1">
                      Add products and priced extras here. Use &quot;Optional extras for customer&quot; below to
                      show extras on the PDF without adding them to the total.
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button type="button" variant="outline" size="sm" onClick={addItem}>
                      <Plus className="h-4 w-4 mr-2" />
                      Add Product
                    </Button>
                    <Button type="button" variant="outline" size="sm" onClick={() => setExtraPickerOpen(true)}>
                      <Plus className="h-4 w-4 mr-2" />
                      Add extra to quote
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {items.map((item, index) => (
                  <div
                    key={index}
                    className={`p-4 border rounded-md space-y-4 ${item.parent_index != null ? 'pl-6 border-l-4 border-l-muted-foreground/30 bg-muted/20' : ''}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">
                        {item.parent_index != null ? (
                          <>
                            Optional extra for Product{' '}
                            {rootBuildingProductNumberAtIndex(
                              items,
                              item.parent_index ?? 0,
                              optionalExtraIds,
                              productDetails
                            )}
                          </>
                        ) : isRootQuoteLevelOptionalExtraLine(item, optionalExtraIds, productDetails) ? (
                          <>Optional extra</>
                        ) : (
                          <>
                            Product{' '}
                            {rootBuildingProductNumberAtIndex(items, index, optionalExtraIds, productDetails)}
                          </>
                        )}
                      </span>
                      {items.length > 1 && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => removeItem(index)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      )}
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label>Product (Optional)</Label>
                        <Select
                          value={item.product_id?.toString() || 'custom'}
                          onValueChange={(value) => updateItem(index, 'product_id', value === 'custom' ? undefined : value)}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select product or enter custom" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="custom">Custom Item</SelectItem>
                            {[...products].sort((a, b) => a.name.localeCompare(b.name)).map((product) => (
                              <SelectItem key={product.id} value={product.id.toString()}>
                                {product.name} - £{Number(product.base_price).toFixed(2)}
                              </SelectItem>
                            ))}
                            {item.product_id &&
                              !products.some((p) => p.id === item.product_id) &&
                              productDetails[item.product_id] && (
                                <SelectItem key={`catalog-line-${item.product_id}`} value={item.product_id.toString()}>
                                  {productDetails[item.product_id].name} - £
                                  {Number(productDetails[item.product_id].base_price).toFixed(2)}
                                </SelectItem>
                              )}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <Label>
                          Description <span className="text-destructive">*</span>
                        </Label>
                        <Input
                          value={item.description}
                          onChange={(e) => updateItem(index, 'description', e.target.value)}
                          placeholder="Item description"
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>
                          Quantity <span className="text-destructive">*</span>
                        </Label>
                        <Input
                          type="number"
                          step="0.01"
                          min="0"
                          value={item.quantity}
                          onChange={(e) => updateItem(index, 'quantity', parseFloat(e.target.value) || 0)}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>
                          Unit Price (£) <span className="text-destructive">*</span>
                        </Label>
                        <Input
                          type="number"
                          step="0.01"
                          {...(!allowsNegativeUnitPrice(item) ? { min: '0' } : {})}
                          value={item.unit_price}
                          onChange={(e) =>
                            updateItem(
                              index,
                              'unit_price',
                              parseQuoteLineUnitPrice(item, e.target.value)
                            )
                          }
                          required
                        />
                        {allowsNegativeUnitPrice(item) && (
                          <p className="text-xs text-muted-foreground">
                            Enter a negative amount for a credit (e.g. -100)
                          </p>
                        )}
                      </div>
                      {isCustomQuoteLine(item) && !isDeliveryOrInstallItem(item) && (
                        <div className="space-y-2 md:col-span-2">
                          <Label>Installation hours (per unit)</Label>
                          <Input
                            type="number"
                            step="0.01"
                            min="0"
                            value={item.installation_hours ?? ''}
                            onChange={(e) => {
                              const raw = e.target.value;
                              updateItem(
                                index,
                                'installation_hours',
                                raw === '' ? undefined : parseFloat(raw) || 0
                              );
                            }}
                            placeholder="Optional — for delivery & installation estimate"
                          />
                        </div>
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      Line Total: £{quoteLineTotal(item).toFixed(2)}
                    </div>
                    {isCustomQuoteLine(item) &&
                      !isDeliveryOrInstallItem(item) &&
                      lineInstallationHoursPerUnit(item, null) > 0 && (
                      <div className="text-sm space-y-1">
                        <div>
                          <span className="text-muted-foreground">Installation Hours: </span>
                          <span className="font-medium">
                            {lineInstallationHoursPerUnit(item, null)} hours
                            {(Number(item.quantity) || 0) > 1
                              ? ` × ${item.quantity} = ${(
                                  lineInstallationHoursPerUnit(item, null) *
                                  (Number(item.quantity) || 0)
                                ).toFixed(2)} total`
                              : ''}
                          </span>
                        </div>
                        {calculateInstallCostForLine(item) != null && (
                          <div>
                            <span className="text-muted-foreground">Installation Cost (per unit): </span>
                            <span className="font-medium">
                              £{calculateInstallCostForLine(item)!.toFixed(2)}
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                    {item.parent_index == null &&
                      !isRootQuoteLevelOptionalExtraLine(item, optionalExtraIds, productDetails) && (
                      <div className="flex items-center gap-2 pt-1">
                        <input
                          type="checkbox"
                          id={`exclude-building-discount-${index}`}
                          className="h-4 w-4 rounded border-muted-foreground"
                          checked={item.include_in_building_discount === false}
                          onChange={(e) =>
                            updateItem(index, 'include_in_building_discount', !e.target.checked)
                          }
                        />
                        <Label
                          htmlFor={`exclude-building-discount-${index}`}
                          className="text-sm font-normal text-muted-foreground cursor-pointer"
                        >
                          Exclude from &apos;building items only&apos; discount
                        </Label>
                      </div>
                    )}
                    {(() => {
                      const selectedProduct = getSelectedProduct(item);
                      if (!selectedProduct) return null;
                      if (selectedProduct.is_extra && item.parent_index == null) return null;
                      
                      const installCost = calculateInstallCostForLine(item);
                      const hasExtras = selectedProduct.optional_extras && selectedProduct.optional_extras.length > 0;
                      const extrasLoaded = productDetails[item.product_id!] != null;
                      
                      return (
                        <div className="mt-4 pt-4 border-t space-y-2">
                          {lineInstallationHoursPerUnit(item, selectedProduct) > 0 && (
                            <div className="text-sm">
                              <span className="text-muted-foreground">Installation Hours: </span>
                              <span className="font-medium">
                                {lineInstallationHoursPerUnit(item, selectedProduct)} hours
                              </span>
                            </div>
                          )}
                          {installCost !== null && (
                            <div className="text-sm">
                              <span className="text-muted-foreground">Installation Cost: </span>
                              <span className="font-medium">£{installCost.toFixed(2)}</span>
                            </div>
                          )}
                          <div className="mt-2">
                            <Label className="text-sm font-medium">Optional Extras</Label>
                            {!extrasLoaded ? (
                              <p className="text-sm text-muted-foreground mt-1">Loading optional extras…</p>
                            ) : hasExtras ? (
                              <div className="mt-2 space-y-2">
                                {[...selectedProduct.optional_extras!].sort((a, b) => a.name.localeCompare(b.name)).map((extra) => (
                                  <div
                                    key={extra.id}
                                    className="flex items-center justify-between p-2 border rounded-md hover:bg-muted/50"
                                  >
                                    <div className="flex-1">
                                      <p className="text-sm font-medium">{extra.name}</p>
                                      <p className="text-xs text-muted-foreground">
                                        £{Number(extra.base_price).toFixed(2)}
                                      </p>
                                    </div>
                                    <Button
                                      type="button"
                                      variant="outline"
                                      size="sm"
                                      onClick={() => addOptionalExtra(index, extra)}
                                    >
                                      <Plus className="h-3 w-3 mr-1" />
                                      Add
                                    </Button>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-sm text-muted-foreground mt-1">No optional extras for this product.</p>
                            )}
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                ))}
                <div className="p-4 bg-muted rounded-md space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold">Subtotal (Ex VAT):</span>
                    <span className="font-semibold">£{calculateSubtotal().toFixed(2)}</span>
                  </div>
                  {selectedDiscountIds.length > 0 && (
                    <div className="flex justify-between items-center text-sm text-muted-foreground">
                      <span>Discounts will be calculated on submission</span>
                    </div>
                  )}
                  <div className="flex justify-between items-center border-t pt-2">
                    <span className="font-semibold">Total (Ex VAT):</span>
                    <span className="font-semibold">£{calculateTotal().toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">VAT @ 20%:</span>
                    <span>£{(calculateTotal() * 0.2).toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between items-center border-t pt-2">
                    <span className="font-semibold text-lg">Total (inc VAT):</span>
                    <span className="font-semibold text-lg">£{(calculateTotal() * 1.2).toFixed(2)}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Customer optional extras</CardTitle>
              </CardHeader>
              <CardContent>
                <QuoteDisplayedOptionalExtrasSection
                  displayedExtraIds={displayedOptionalExtraIds}
                  onChange={setDisplayedOptionalExtraIds}
                  allOptionalExtras={allOptionalExtras}
                  productDetails={productDetails}
                />
              </CardContent>
            </Card>

            <Dialog open={extraPickerOpen} onOpenChange={setExtraPickerOpen}>
              <DialogContent className="max-w-lg max-h-[min(80vh,520px)] flex flex-col">
                <DialogHeader>
                  <DialogTitle>Add extra to quote</DialogTitle>
                  <DialogDescription>
                    Adds a priced line to the quote (included in the total). Not included in &apos;building
                    items only&apos; discounts.
                  </DialogDescription>
                </DialogHeader>
                <Input
                  placeholder="Search…"
                  value={extraPickerFilter}
                  onChange={(e) => setExtraPickerFilter(e.target.value)}
                  className="mb-2"
                />
                <div className="overflow-y-auto flex-1 space-y-2 min-h-0 pr-1">
                  {filteredPickerExtras.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No matching optional extras.</p>
                  ) : (
                    filteredPickerExtras.map((extra) => (
                      <div
                        key={extra.id}
                        className="flex items-center justify-between gap-2 p-2 border rounded-md"
                      >
                        <div>
                          <p className="text-sm font-medium">{extra.name}</p>
                          <p className="text-xs text-muted-foreground">
                            £{Number(extra.base_price).toFixed(2)}
                          </p>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => addQuoteLevelOptionalExtra(extra)}
                        >
                          <Plus className="h-3 w-3 mr-1" />
                          Add
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              </DialogContent>
            </Dialog>

            <Card>
              <CardHeader>
                <CardTitle>Fulfillment</CardTitle>
              </CardHeader>
              <CardContent>
                <FulfillmentMethodField
                  value={fulfillmentMethod}
                  onChange={setFulfillmentMethod}
                  hasDeliveryInstallLines={hasDeliveryInstallLine(items)}
                  onCollectionBlocked={() =>
                    toast.error(
                      'Remove delivery or installation lines before switching to collection.'
                    )
                  }
                />
                <div className="mt-4 border-t pt-4">
                  <DeliveryLocationFields
                    fulfillmentMethod={fulfillmentMethod}
                    useAlternateDeliveryAddress={useAlternateDeliveryAddress}
                    onUseAlternateDeliveryAddressChange={setUseAlternateDeliveryAddress}
                    deliveryAddressLine1={deliveryAddressLine1}
                    onDeliveryAddressLine1Change={setDeliveryAddressLine1}
                    deliveryAddressLine2={deliveryAddressLine2}
                    onDeliveryAddressLine2Change={setDeliveryAddressLine2}
                    deliveryCity={deliveryCity}
                    onDeliveryCityChange={setDeliveryCity}
                    deliveryCounty={deliveryCounty}
                    onDeliveryCountyChange={setDeliveryCounty}
                    deliveryPostcode={deliveryPostcode}
                    onDeliveryPostcodeChange={setDeliveryPostcode}
                    deliveryCountry={deliveryCountry}
                    onDeliveryCountryChange={setDeliveryCountry}
                    deliveryLocationNotes={deliveryLocationNotes}
                    onDeliveryLocationNotesChange={setDeliveryLocationNotes}
                  />
                </div>
              </CardContent>
            </Card>

            {fulfillmentMethod !== 'COLLECTION' &&
              ((useAlternateDeliveryAddress && deliveryPostcode.trim()) ||
                (!useAlternateDeliveryAddress && customer?.postcode?.trim())) && (
              <DeliveryInstallEstimatePanel
                estimate={deliveryEstimate}
                mode={deliveryEstimateMode}
                loading={deliveryEstimateLoading}
                error={deliveryEstimateError}
                customerPostcode={
                  useAlternateDeliveryAddress ? deliveryPostcode : customer?.postcode ?? ''
                }
                companySettings={companySettings}
                installHours={calculateTotalInstallationHours()}
                hasDeliveryLine={hasDeliveryInstallLine(items)}
                onModeChange={setDeliveryEstimateMode}
                onAdd={addDeliveryInstallToQuote}
                onRemove={removeDeliveryInstallFromQuote}
              />
            )}

            {/* Discounts Selection */}
            <Card className="border-violet-200 bg-violet-50 dark:border-violet-800 dark:bg-violet-950/30">
              <CardHeader>
                <CardTitle>Discounts & Giveaways</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Select Discounts</Label>
                  <Select
                    value=""
                    onValueChange={(value) => {
                      if (value && !selectedDiscountIds.includes(parseInt(value))) {
                        setSelectedDiscountIds([...selectedDiscountIds, parseInt(value)]);
                      }
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select a discount to apply..." />
                    </SelectTrigger>
                    <SelectContent>
                      {availableDiscounts
                        .filter((d) => !selectedDiscountIds.includes(d.id) && !isDiscountTemplateExpired(d))
                        .map((discount) => (
                          <SelectItem key={discount.id} value={discount.id.toString()}>
                            {discount.name} - {discount.discount_type === 'PERCENTAGE' ? `${discount.discount_value}%` : `£${discount.discount_value}`} ({discount.scope === 'PRODUCT' ? 'Product (Building Only)' : 'Entire Quote'})
                            {discount.is_giveaway && ' 🎁'}
                            {discount.max_uses != null && discount.remaining_uses != null
                              ? ` · ${discount.remaining_uses} accept${discount.remaining_uses === 1 ? '' : 's'} left`
                              : ''}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>
                {selectedDiscountIds.length > 0 && (
                  <div className="space-y-2">
                    <Label>Selected Discounts</Label>
                    <div className="space-y-2">
                      {selectedDiscountIds.map((discountId) => {
                        const discount = availableDiscounts.find((d) => d.id === discountId);
                        if (!discount) return null;
                        return (
                          <div
                            key={discountId}
                            className="flex items-center justify-between rounded-md border border-violet-200/80 bg-white/80 p-3 dark:border-violet-800/60 dark:bg-background/60"
                          >
                            <div className="flex-1">
                              <p className="font-medium">
                                {discount.name}
                                {discount.is_giveaway && ' 🎁'}
                              </p>
                              <p className="text-sm text-muted-foreground">
                                {discount.discount_type === 'PERCENTAGE'
                                  ? `${discount.discount_value}%`
                                  : `£${discount.discount_value}`}{' '}
                                off {discount.scope === 'PRODUCT' ? 'building items only' : 'entire quote'}
                              </p>
                            </div>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                setSelectedDiscountIds(
                                  selectedDiscountIds.filter((id) => id !== discountId)
                                )
                              }
                            >
                              <X className="h-4 w-4" />
                            </Button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Quote Details */}
            <Card>
              <CardHeader>
                <CardTitle>Quote Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Deposit Amount (£)</Label>
                  <div className="space-y-2">
                    <Input
                      type="number"
                      step="0.01"
                      min="0"
                      value={depositAmount}
                      onChange={(e) => {
                        const value = e.target.value;
                        setDepositAmount(value === '' ? '' : parseFloat(value) || 0);
                      }}
                      placeholder={`Default: £${calculateDefaultDeposit().toFixed(2)} (50%)`}
                    />
                    <div className="text-sm text-muted-foreground">
                      {depositAmount === '' ? (
                        <>Default deposit: £{calculateDefaultDeposit().toFixed(2)} (50% of total inc VAT)</>
                      ) : (
                        <>Balance: £{getBalanceAmount().toFixed(2)}</>
                      )}
                    </div>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>Deal temperature</Label>
                  <Select
                    value={temperature || ''}
                    onValueChange={(v) => setTemperature(v ? (v as QuoteTemperature) : '')}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select temperature" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={QuoteTemperature.HOT}>Hot</SelectItem>
                      <SelectItem value={QuoteTemperature.WARM}>Warm</SelectItem>
                      <SelectItem value={QuoteTemperature.COLD}>Cold</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Valid Until</Label>
                  <Input
                    type="date"
                    value={validUntil}
                    onChange={(e) => setValidUntil(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <button
                    type="button"
                    className="flex items-center justify-between w-full text-left font-medium leading-none hover:opacity-80"
                    onClick={() => setTermsExpanded((prev) => !prev)}
                  >
                    <Label className="cursor-pointer">Terms and Conditions</Label>
                    {termsExpanded ? (
                      <ChevronUp className="h-4 w-4 text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
                    )}
                  </button>
                  {termsExpanded && (
                    <Textarea
                      value={termsAndConditions}
                      onChange={(e) => setTermsAndConditions(e.target.value)}
                      placeholder="Enter terms and conditions..."
                      rows={6}
                    />
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="include_spec_sheets"
                    checked={includeSpecSheets}
                    onChange={(e) => setIncludeSpecSheets(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300"
                  />
                  <Label htmlFor="include_spec_sheets" className="font-normal cursor-pointer">
                    Include product spec sheets with PDF (dimensions, floor plan, specs for products in quote)
                  </Label>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="include_available_optional_extras"
                    checked={includeAvailableOptionalExtras}
                    onChange={(e) => setIncludeAvailableOptionalExtras(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300"
                  />
                  <Label htmlFor="include_available_optional_extras" className="font-normal cursor-pointer">
                    Also show product-linked optional extras not on the quote (in addition to any you add above)
                  </Label>
                </div>
                {fulfillmentMethod !== 'COLLECTION' && (
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="include_delivery_installation_contact_note"
                      checked={includeDeliveryInstallationContactNote}
                      onChange={(e) => setIncludeDeliveryInstallationContactNote(e.target.checked)}
                      className="h-4 w-4 rounded border-gray-300"
                    />
                    <Label
                      htmlFor="include_delivery_installation_contact_note"
                      className="font-normal cursor-pointer"
                    >
                      Show delivery and installation contact message below quote totals (SMS, email, phone)
                    </Label>
                  </div>
                )}
                <div className="space-y-2">
                  <Label>Notes</Label>
                  <Textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Internal notes (not visible to customer)..."
                    rows={4}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Action Buttons */}
            <div className="flex items-center justify-end gap-4 pb-6">
              <Button
                type="button"
                variant="outline"
                onClick={() => navigateAway(`/customers/${customer.id}`)}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={loading || !activeDraftQuoteId}>
                {loading ? 'Saving...' : 'Create Quote'}
              </Button>
            </div>
          </div>
        </form>
      </main>
    </div>
  );
}

export default function CreateQuotePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    }>
      <CreateQuoteContent />
    </Suspense>
  );
}
