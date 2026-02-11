'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ArrowLeft, Save, AlertCircle, CheckCircle, XCircle } from 'lucide-react';
import api from '@/lib/api';
import { Quote, OpportunityStage, LossCategory, Customer, QuoteTemperature } from '@/lib/types';
import CallNotesDialog from '@/components/CallNotesDialog';
import { toast } from 'sonner';

const stageColors: Record<OpportunityStage, string> = {
  [OpportunityStage.DISCOVERY]: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300',
  [OpportunityStage.CONCEPT]: 'bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-300',
  [OpportunityStage.QUOTE_SENT]: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/20 dark:text-yellow-300',
  [OpportunityStage.FOLLOW_UP]: 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-300',
  [OpportunityStage.DECISION_PENDING]: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300',
  [OpportunityStage.WON]: 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-300',
  [OpportunityStage.LOST]: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300',
};

export default function OpportunityDetailPage() {
  const router = useRouter();
  const params = useParams();
  const quoteId = parseInt(params.id as string);

  const [opportunity, setOpportunity] = useState<Quote | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [wonDialogOpen, setWonDialogOpen] = useState(false);
  const [lostDialogOpen, setLostDialogOpen] = useState(false);
  const [callNotesOpen, setCallNotesOpen] = useState(false);
  const [formData, setFormData] = useState({
    opportunity_stage: undefined as OpportunityStage | undefined,
    close_probability: undefined as number | undefined,
    expected_close_date: '',
    next_action: '',
    next_action_due_date: '',
    loss_reason: '',
    loss_category: undefined as LossCategory | undefined,
    temperature: undefined as QuoteTemperature | undefined,
  });

  useEffect(() => {
    if (quoteId) {
      fetchOpportunity();
    }
  }, [quoteId]);

  useEffect(() => {
    if (opportunity) {
      setFormData({
        opportunity_stage: opportunity.opportunity_stage,
        close_probability: opportunity.close_probability,
        expected_close_date: opportunity.expected_close_date ? opportunity.expected_close_date.split('T')[0] : '',
        next_action: opportunity.next_action || '',
        next_action_due_date: opportunity.next_action_due_date ? opportunity.next_action_due_date.split('T')[0] : '',
        loss_reason: opportunity.loss_reason || '',
        loss_category: opportunity.loss_category,
        temperature: opportunity.temperature,
      });
    }
  }, [opportunity]);

  const fetchOpportunity = async () => {
    try {
      setLoading(true);
      const response = await api.get(`/api/quotes/opportunities/${quoteId}`);
      setOpportunity(response.data);
      
      if (response.data.customer_id) {
        try {
          const customerResponse = await api.get(`/api/customers/${response.data.customer_id}`);
          setCustomer(customerResponse.data);
        } catch (error) {
          console.error('Failed to load customer');
        }
      }
    } catch (error: any) {
      toast.error('Failed to load opportunity');
      if (error.response?.status === 401) {
        router.push('/login');
      } else if (error.response?.status === 404) {
        router.push('/opportunities');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!opportunity) return;

    // Validate next action for open opportunities
    if (formData.opportunity_stage && 
        formData.opportunity_stage !== OpportunityStage.WON && 
        formData.opportunity_stage !== OpportunityStage.LOST) {
      if (!formData.next_action || !formData.next_action_due_date) {
        toast.error('Next action and due date are required for open opportunities');
        return;
      }
    }

    try {
      setSaving(true);
      const updateData: any = {
        opportunity_stage: formData.opportunity_stage,
        close_probability: formData.close_probability ? formData.close_probability : undefined,
        expected_close_date: formData.expected_close_date || undefined,
        next_action: formData.next_action || undefined,
        next_action_due_date: formData.next_action_due_date || undefined,
        temperature: formData.temperature,
      };

      await api.patch(`/api/quotes/${quoteId}`, updateData);
      toast.success('Opportunity updated successfully');
      fetchOpportunity();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update opportunity');
    } finally {
      setSaving(false);
    }
  };

  const handleMarkWon = async () => {
    if (!opportunity) return;

    try {
      setSaving(true);
      await api.post(`/api/quotes/opportunities/${quoteId}/won`, {
        confirmed_value: opportunity.total_amount > 0 ? opportunity.total_amount : undefined,
      });
      toast.success('Opportunity marked as WON');
      setWonDialogOpen(false);
      fetchOpportunity();
      router.push('/opportunities');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to mark opportunity as won');
    } finally {
      setSaving(false);
    }
  };

  const handleMarkLost = async () => {
    if (!opportunity) return;

    if (!formData.loss_reason || !formData.loss_category) {
      toast.error('Loss reason and category are required');
      return;
    }

    try {
      setSaving(true);
      await api.post(`/api/quotes/opportunities/${quoteId}/lost`, {
        loss_reason: formData.loss_reason,
        loss_category: formData.loss_category,
      });
      toast.success('Opportunity marked as LOST');
      setLostDialogOpen(false);
      fetchOpportunity();
      router.push('/opportunities');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to mark opportunity as lost');
    } finally {
      setSaving(false);
    }
  };

  const getDaysOverdue = (): number | null => {
    if (!opportunity?.next_action_due_date) return null;
    const due = new Date(opportunity.next_action_due_date);
    const now = new Date();
    const diffMs = now.getTime() - due.getTime();
    const diffDays = Math.floor(diffMs / 86400000);
    return diffDays > 0 ? diffDays : null;
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

  if (!opportunity) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Opportunity not found</div>
        </div>
      </div>
    );
  }

  const daysOverdue = getDaysOverdue();
  const isOverdue = daysOverdue !== null && daysOverdue > 0;
  const isOpen = opportunity.opportunity_stage && 
                 opportunity.opportunity_stage !== OpportunityStage.WON && 
                 opportunity.opportunity_stage !== OpportunityStage.LOST;

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <Button variant="ghost" onClick={() => router.push('/opportunities')} className="mb-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Opportunities
          </Button>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-semibold">{opportunity.quote_number}</h1>
              {customer && (
                <p className="text-muted-foreground mt-1">
                  For {customer.name}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              {opportunity.opportunity_stage && (
                <Badge className={stageColors[opportunity.opportunity_stage]}>
                  {opportunity.opportunity_stage.replace('_', ' ')}
                </Badge>
              )}
              {opportunity.temperature && (
                <Badge variant="outline">{opportunity.temperature}</Badge>
              )}
            </div>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Opportunity Details */}
            <Card>
              <CardHeader>
                <CardTitle>Opportunity Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Stage</Label>
                    <Select
                      value={formData.opportunity_stage || ''}
                      onValueChange={(value) => setFormData({ ...formData, opportunity_stage: value as OpportunityStage })}
                      disabled={saving}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select stage" />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.values(OpportunityStage).map((stage) => (
                          <SelectItem key={stage} value={stage}>
                            {stage.replace('_', ' ')}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Close Probability (%)</Label>
                    <Input
                      type="number"
                      min="0"
                      max="100"
                      value={formData.close_probability || ''}
                      onChange={(e) => setFormData({ ...formData, close_probability: e.target.value ? parseFloat(e.target.value) : undefined })}
                      disabled={saving}
                    />
                  </div>
                  <div>
                    <Label>Expected Close Date</Label>
                    <Input
                      type="date"
                      value={formData.expected_close_date}
                      onChange={(e) => setFormData({ ...formData, expected_close_date: e.target.value })}
                      disabled={saving}
                    />
                  </div>
                  <div>
                    <Label>Value (£)</Label>
                    <Input
                      type="number"
                      value={opportunity.total_amount || 0}
                      disabled
                      className="bg-muted"
                    />
                  </div>
                  <div>
                    <Label>Temperature</Label>
                    <Select
                      value={formData.temperature || ''}
                      onValueChange={(value) => setFormData({ ...formData, temperature: value ? (value as QuoteTemperature) : undefined })}
                      disabled={saving}
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
                </div>

                {/* Next Action Section - Highlighted if missing or overdue */}
                <div className={`p-4 rounded-lg border-2 ${!formData.next_action || isOverdue ? 'border-red-500 bg-red-50 dark:bg-red-500/10' : 'border-border'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Label className="text-base font-semibold">Next Action</Label>
                    {isOverdue && (
                      <Badge variant="destructive">
                        <AlertCircle className="h-3 w-3 mr-1" />
                        {daysOverdue}d overdue
                      </Badge>
                    )}
                    {!formData.next_action && isOpen && (
                      <Badge variant="destructive">Required</Badge>
                    )}
                  </div>
                  <Textarea
                    value={formData.next_action}
                    onChange={(e) => setFormData({ ...formData, next_action: e.target.value })}
                    placeholder="What needs to happen next?"
                    disabled={saving || !isOpen}
                    rows={3}
                    className="mb-2"
                  />
                  <div>
                    <Label>Due Date</Label>
                    <Input
                      type="datetime-local"
                      value={formData.next_action_due_date}
                      onChange={(e) => setFormData({ ...formData, next_action_due_date: e.target.value })}
                      disabled={saving || !isOpen}
                    />
                  </div>
                </div>

                {opportunity.loss_reason && (
                  <div className="p-4 rounded-lg border border-red-200 bg-red-50 dark:bg-red-500/10">
                    <Label className="text-base font-semibold text-red-700">Loss Reason</Label>
                    <p className="text-sm text-muted-foreground mt-1">{opportunity.loss_reason}</p>
                    {opportunity.loss_category && (
                      <Badge variant="outline" className="mt-2">
                        {opportunity.loss_category}
                      </Badge>
                    )}
                  </div>
                )}

                <div className="flex justify-end pt-4">
                  <Button onClick={handleSave} disabled={saving}>
                    <Save className="h-4 w-4 mr-2" />
                    {saving ? 'Saving...' : 'Save Changes'}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Quote Items (if any) */}
            {opportunity.items && opportunity.items.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Quote Items</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {opportunity.items.map((item) => (
                      <div key={item.id} className="flex justify-between p-2 border rounded">
                        <span>{item.description}</span>
                        <span className="font-semibold">£{item.final_line_total.toLocaleString()}</span>
                      </div>
                    ))}
                    <div className="flex justify-between p-2 border-t-2 font-bold mt-2">
                      <span>Total</span>
                      <span>£{opportunity.total_amount.toLocaleString()}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Actions */}
            {isOpen && (
              <Card>
                <CardHeader>
                  <CardTitle>Actions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Button
                    onClick={() => setWonDialogOpen(true)}
                    className="w-full bg-green-600 hover:bg-green-700"
                  >
                    <CheckCircle className="h-4 w-4 mr-2" />
                    Mark as Won
                  </Button>
                  <Button
                    onClick={() => setLostDialogOpen(true)}
                    variant="destructive"
                    className="w-full"
                  >
                    <XCircle className="h-4 w-4 mr-2" />
                    Mark as Lost
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* Customer Info */}
            {customer && (
              <Card>
                <CardHeader>
                  <CardTitle>Customer</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="font-semibold">{customer.name}</p>
                  {customer.email && <p className="text-sm text-muted-foreground">{customer.email}</p>}
                  {customer.phone && (
                    <p className="text-sm text-muted-foreground">
                      <button
                        type="button"
                        className="text-primary hover:underline text-left"
                        onClick={() => setCallNotesOpen(true)}
                      >
                        {customer.phone}
                      </button>
                    </p>
                  )}
                  <Button
                    variant="outline"
                    className="w-full mt-4"
                    onClick={() => router.push(`/customers/${customer.id}`)}
                  >
                    View Customer Profile
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>
        </div>

        {/* Won Dialog */}
        <Dialog open={wonDialogOpen} onOpenChange={setWonDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Mark Opportunity as Won</DialogTitle>
              <DialogDescription>
                This will mark the opportunity as won and transition associated leads to WON status.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setWonDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleMarkWon} disabled={saving} className="bg-green-600 hover:bg-green-700">
                {saving ? 'Marking...' : 'Mark as Won'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Lost Dialog */}
        <Dialog open={lostDialogOpen} onOpenChange={setLostDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Mark Opportunity as Lost</DialogTitle>
              <DialogDescription>
                Please provide a reason for the loss. This will transition associated leads to LOST status.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div>
                <Label>Loss Category *</Label>
                <Select
                  value={formData.loss_category || ''}
                  onValueChange={(value) => setFormData({ ...formData, loss_category: value as LossCategory })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select category" />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.values(LossCategory).map((category) => (
                      <SelectItem key={category} value={category}>
                        {category}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Loss Reason *</Label>
                <Textarea
                  value={formData.loss_reason}
                  onChange={(e) => setFormData({ ...formData, loss_reason: e.target.value })}
                  placeholder="Explain why this opportunity was lost..."
                  rows={4}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setLostDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleMarkLost}
                disabled={saving || !formData.loss_reason || !formData.loss_category}
                variant="destructive"
              >
                {saving ? 'Marking...' : 'Mark as Lost'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {customer && customer.phone && (
          <CallNotesDialog
            open={callNotesOpen}
            onOpenChange={setCallNotesOpen}
            customerId={customer.id}
            customerName={customer.name}
            phone={customer.phone}
          />
        )}
      </main>
    </div>
  );
}
