'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { createConfiguratorInvite, getApiErrorDetail } from '@/lib/api';
import { Copy } from 'lucide-react';
import { toast } from 'sonner';

interface SendConfiguratorLinkDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerId?: number;
  leadId?: number;
  customerName?: string;
}

export default function SendConfiguratorLinkDialog({
  open,
  onOpenChange,
  customerId,
  leadId,
  customerName,
}: SendConfiguratorLinkDialogProps) {
  const [loading, setLoading] = useState(false);
  const [configureUrl, setConfigureUrl] = useState('');

  const handleCreate = async () => {
    try {
      setLoading(true);
      const invite = await createConfiguratorInvite({
        customer_id: customerId,
        lead_id: leadId,
      });
      setConfigureUrl(invite.configure_url);
      toast.success('Layout link ready — copy and send by email or SMS');
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to create layout link');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!configureUrl) return;
    try {
      await navigator.clipboard.writeText(configureUrl);
      toast.success('Link copied');
    } catch {
      toast.error('Could not copy link');
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setConfigureUrl('');
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Send layout builder link</DialogTitle>
          <DialogDescription>
            {customerName
              ? `Create a link for ${customerName} to design their own building layout.`
              : 'Create a link for the customer to design their building layout.'}
            {customerId
              ? ' They can open the builder straight away — no details form needed.'
              : ' They will enter their details on first visit.'}
          </DialogDescription>
        </DialogHeader>
        {!configureUrl ? (
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={() => void handleCreate()} disabled={loading}>
              {loading ? 'Creating…' : 'Create link'}
            </Button>
          </DialogFooter>
        ) : (
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="configure-url">Layout link</Label>
              <div className="flex gap-2">
                <Input id="configure-url" readOnly value={configureUrl} className="font-mono text-xs" />
                <Button type="button" variant="outline" size="icon" onClick={() => void handleCopy()} title="Copy link">
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Paste this into an email or SMS. When they submit their layout, you can apply it to the draft quote from
              the configurator.
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Done
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
