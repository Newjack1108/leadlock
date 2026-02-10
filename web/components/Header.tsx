'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import Logo from './Logo';
import { Button } from '@/components/ui/button';
import { LogOut, Users, Settings, Package, User, Mail, Bell, FileText, ShoppingCart, ChevronDown, Gift, Send, MessageSquare } from 'lucide-react';
import api from '@/lib/api';
import { getStaleSummary, getDiscountRequests, getUnreadSms, getUnreadMessenger } from '@/lib/api';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

export default function Header() {
  const router = useRouter();
  const pathname = usePathname();
  const [userRole, setUserRole] = useState<string | null>(null);
  const [reminderCount, setReminderCount] = useState<number>(0);
  const [newLeadsCount, setNewLeadsCount] = useState<number>(0);
  const [unreadMessagesCount, setUnreadMessagesCount] = useState<number>(0);
  const [pendingDiscountCount, setPendingDiscountCount] = useState<number>(0);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const response = await api.get('/api/auth/me');
        setUserRole(response.data.role);
      } catch (error) {
        // User not authenticated or error fetching user
        setUserRole(null);
      }
    };
    fetchUser();
  }, []);

  const fetchReminderCount = async () => {
    try {
      const summary = await getStaleSummary();
      setReminderCount(summary.total_reminders || 0);
    } catch (error) {
      // Silently fail to avoid disrupting navigation
      setReminderCount(0);
    }
  };

  const fetchNewLeadsCount = async () => {
    try {
      const response = await api.get('/api/dashboard/stats');
      setNewLeadsCount(response.data.new_count || 0);
    } catch (error) {
      // Silently fail to avoid disrupting navigation
      setNewLeadsCount(0);
    }
  };

  const fetchPendingDiscountCount = async () => {
    try {
      const list = await getDiscountRequests({ status: 'PENDING' });
      setPendingDiscountCount(Array.isArray(list) ? list.length : 0);
    } catch {
      setPendingDiscountCount(0);
    }
  };

  const fetchUnreadMessagesCount = async () => {
    try {
      const [smsRes, messengerRes] = await Promise.all([
        getUnreadSms().catch(() => ({ count: 0 })),
        getUnreadMessenger().catch(() => ({ count: 0 })),
      ]);
      setUnreadMessagesCount((smsRes?.count ?? 0) + (messengerRes?.count ?? 0));
    } catch {
      setUnreadMessagesCount(0);
    }
  };

  useEffect(() => {
    fetchReminderCount();
    fetchNewLeadsCount();
    fetchUnreadMessagesCount();
    if (userRole === 'DIRECTOR' || userRole === 'SALES_MANAGER') {
      fetchPendingDiscountCount();
    }
  }, [pathname, userRole]);

  const handleLogout = () => {
    // Clear token from localStorage
    localStorage.removeItem('token');
    // Clear token cookie
    document.cookie = 'token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    // Redirect to login
    router.push('/login');
    // Force a hard reload to clear any cached state
    window.location.href = '/login';
  };

  const isDirector = userRole === 'DIRECTOR';
  const canApproveDiscounts = userRole === 'DIRECTOR' || userRole === 'SALES_MANAGER';

  return (
    <header className="border-b border-border bg-card shadow-sm">
      <div className="container mx-auto px-6 py-0 flex items-center justify-between">
        <Logo />
        <nav className="flex items-center gap-4">
          {/* Main Navigation */}
          <Link href="/leads" className="relative">
            <Button
              variant={pathname?.startsWith('/leads') ? 'default' : 'ghost'}
              size="sm"
              className={pathname?.startsWith('/leads') ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}
            >
              <Users className="h-4 w-4 mr-2" />
              Leads
            </Button>
            {newLeadsCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold flex items-center justify-center">
                {newLeadsCount > 99 ? '99+' : newLeadsCount}
              </span>
            )}
          </Link>
          <Link href="/customers" className="relative">
            <Button
              variant={pathname?.startsWith('/customers') ? 'default' : 'ghost'}
              size="sm"
              className={pathname?.startsWith('/customers') ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}
            >
              <Users className="h-4 w-4 mr-2" />
              Customers
            </Button>
            {unreadMessagesCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold flex items-center justify-center">
                {unreadMessagesCount > 99 ? '99+' : unreadMessagesCount}
              </span>
            )}
          </Link>
          <Link href="/quotes">
            <Button
              variant={pathname?.startsWith('/quotes') ? 'default' : 'ghost'}
              size="sm"
              className={pathname?.startsWith('/quotes') ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}
            >
              <FileText className="h-4 w-4 mr-2" />
              Quotes
            </Button>
          </Link>
          <Link href="/orders">
            <Button
              variant={pathname?.startsWith('/orders') ? 'default' : 'ghost'}
              size="sm"
              className={pathname?.startsWith('/orders') ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}
            >
              <ShoppingCart className="h-4 w-4 mr-2" />
              Orders
            </Button>
          </Link>
          {isDirector && (
            <Link href="/products">
              <Button
                variant={pathname?.startsWith('/products') ? 'default' : 'ghost'}
                size="sm"
                className={pathname?.startsWith('/products') ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}
              >
                <Package className="h-4 w-4 mr-2" />
                Products
              </Button>
            </Link>
          )}
          <Link href="/reminders" className="relative">
            <Button
              variant={pathname?.startsWith('/reminders') ? 'default' : 'ghost'}
              size="sm"
              className={pathname?.startsWith('/reminders') ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}
            >
              <Bell className="h-4 w-4 mr-2" />
              Reminders
            </Button>
            {reminderCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold flex items-center justify-center">
                {reminderCount > 99 ? '99+' : reminderCount}
              </span>
            )}
          </Link>
          <Link href="/discount-requests" className="relative">
            <Button
              variant={pathname?.startsWith('/discount-requests') ? 'default' : 'ghost'}
              size="sm"
              className={pathname?.startsWith('/discount-requests') ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}
            >
              <Send className="h-4 w-4 mr-2" />
              Discount requests
            </Button>
            {canApproveDiscounts && pendingDiscountCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold flex items-center justify-center">
                {pendingDiscountCount > 99 ? '99+' : pendingDiscountCount}
              </span>
            )}
          </Link>

          {/* Profile Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-foreground"
              >
                <User className="h-4 w-4 mr-2" />
                <ChevronDown className="h-3 w-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <Link href="/settings/user">
                <DropdownMenuItem className="cursor-pointer">
                  <User className="h-4 w-4 mr-2" />
                  My Settings
                </DropdownMenuItem>
              </Link>
              {isDirector && (
                <>
                  <Link href="/settings/company">
                    <DropdownMenuItem className="cursor-pointer">
                      <Settings className="h-4 w-4 mr-2" />
                      Company Settings
                    </DropdownMenuItem>
                  </Link>
                  <Link href="/settings/email-templates">
                    <DropdownMenuItem className="cursor-pointer">
                      <Mail className="h-4 w-4 mr-2" />
                      Email Templates
                    </DropdownMenuItem>
                  </Link>
                  <Link href="/settings/sms-templates">
                    <DropdownMenuItem className="cursor-pointer">
                      <MessageSquare className="h-4 w-4 mr-2" />
                      SMS Templates
                    </DropdownMenuItem>
                  </Link>
                  <Link href="/discounts">
                    <DropdownMenuItem className="cursor-pointer">
                      <Gift className="h-4 w-4 mr-2" />
                      Discounts & Giveaways
                    </DropdownMenuItem>
                  </Link>
                </>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={handleLogout}
                className="cursor-pointer text-destructive focus:text-destructive"
              >
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </nav>
      </div>
    </header>
  );
}
