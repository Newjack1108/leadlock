'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import Logo from './Logo';
import { Button } from '@/components/ui/button';
import {
  LogOut,
  Users,
  Settings,
  Package,
  User,
  Mail,
  Bell,
  FileText,
  ShoppingCart,
  ChevronDown,
  Gift,
  Send,
  MessageSquare,
  FolderOpen,
  LayoutDashboard,
  Menu,
} from 'lucide-react';
import api from '@/lib/api';
import {
  getStaleSummary,
  getDiscountRequests,
  getUnreadSms,
  getUnreadMessenger,
  getUnreadEmails,
  getQualifiedForQuoting,
} from '@/lib/api';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { cn } from '@/lib/utils';

function BadgePill({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="min-w-[22px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold flex items-center justify-center shrink-0">
      {count > 99 ? '99+' : count}
    </span>
  );
}

export default function Header() {
  const router = useRouter();
  const pathname = usePathname();
  const [userRole, setUserRole] = useState<string | null>(null);
  const [reminderCount, setReminderCount] = useState<number>(0);
  const [newLeadsCount, setNewLeadsCount] = useState<number>(0);
  const [unreadMessagesCount, setUnreadMessagesCount] = useState<number>(0);
  const [pendingDiscountCount, setPendingDiscountCount] = useState<number>(0);
  const [newQualifiedDashboardCount, setNewQualifiedDashboardCount] = useState<number>(0);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const response = await api.get('/api/auth/me');
        setUserRole(response.data.role);
      } catch {
        setUserRole(null);
      }
    };
    fetchUser();
  }, []);

  const fetchReminderCount = async () => {
    try {
      const summary = await getStaleSummary();
      setReminderCount(summary.total_reminders || 0);
    } catch {
      setReminderCount(0);
    }
  };

  const fetchNewLeadsCount = async () => {
    try {
      const response = await api.get('/api/dashboard/stats');
      setNewLeadsCount(response.data.new_count || 0);
    } catch {
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
      const [smsRes, messengerRes, emailRes] = await Promise.all([
        getUnreadSms().catch(() => ({ count: 0 })),
        getUnreadMessenger().catch(() => ({ count: 0 })),
        getUnreadEmails().catch(() => ({ count: 0 })),
      ]);
      setUnreadMessagesCount(
        (smsRes?.count ?? 0) + (messengerRes?.count ?? 0) + (emailRes?.count ?? 0)
      );
    } catch {
      setUnreadMessagesCount(0);
    }
  };

  const fetchNewQualifiedDashboardCount = async () => {
    try {
      const summary = await getQualifiedForQuoting();
      setNewQualifiedDashboardCount(summary?.count ?? 0);
    } catch {
      setNewQualifiedDashboardCount(0);
    }
  };

  /* eslint-disable react-hooks/set-state-in-effect -- async API helpers update badge state after await; not synchronous setState */
  useEffect(() => {
    fetchReminderCount();
    fetchNewLeadsCount();
    fetchUnreadMessagesCount();
    if (userRole === 'DIRECTOR' || userRole === 'SALES_MANAGER') {
      fetchPendingDiscountCount();
    }
    if (userRole === 'CLOSER') {
      fetchNewQualifiedDashboardCount();
    }
  }, [pathname, userRole]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const closerQualifiedBadgeCount =
    userRole === 'CLOSER' ? newQualifiedDashboardCount : 0;

  const handleLogout = () => {
    localStorage.removeItem('token');
    document.cookie = 'token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    router.push('/login');
    window.location.href = '/login';
  };

  const closeMobile = () => setMobileNavOpen(false);

  const isDirector = userRole === 'DIRECTOR';
  const isCloser = userRole === 'CLOSER';
  const canApproveDiscounts = userRole === 'DIRECTOR' || userRole === 'SALES_MANAGER';

  const mobileNavLinkClass =
    'flex w-full min-h-11 items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground';

  return (
    <header className="border-b border-border bg-card shadow-sm">
      <div className="container mx-auto flex items-center justify-between px-4 py-0 sm:px-6">
        <Logo disableLink={isCloser} size="header" />
        {/* Desktop nav */}
        <nav className="hidden lg:flex items-center gap-4">
          {isCloser ? (
            <>
              <Link href="/leads" className="relative">
                <Button
                  variant={pathname?.startsWith('/leads') ? 'default' : 'ghost'}
                  size="sm"
                  className={
                    pathname?.startsWith('/leads')
                      ? 'text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }
                >
                  <Users className="h-4 w-4 mr-2" />
                  Leads
                </Button>
              </Link>
              <Link href="/closer-dashboard" className="relative">
                <Button
                  variant={pathname?.startsWith('/closer-dashboard') ? 'default' : 'ghost'}
                  size="sm"
                  className={
                    pathname?.startsWith('/closer-dashboard')
                      ? 'text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }
                >
                  <LayoutDashboard className="h-4 w-4 mr-2" />
                  Dashboard
                </Button>
                {closerQualifiedBadgeCount > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold flex items-center justify-center">
                    {closerQualifiedBadgeCount > 99 ? '99+' : closerQualifiedBadgeCount}
                  </span>
                )}
              </Link>
            </>
          ) : (
            <Link href="/leads" className="relative">
              <Button
                variant={pathname?.startsWith('/leads') ? 'default' : 'ghost'}
                size="sm"
                className={
                  pathname?.startsWith('/leads')
                    ? 'text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }
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
          )}
          <div className="relative">
            <Link href="/customers">
              <Button
                variant={pathname?.startsWith('/customers') ? 'default' : 'ghost'}
                size="sm"
                className={
                  pathname?.startsWith('/customers')
                    ? 'text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }
              >
                <Users className="h-4 w-4 mr-2" />
                Customers
              </Button>
            </Link>
            {unreadMessagesCount > 0 && (
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  router.push('/customers?has_unread=1');
                }}
                className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold flex items-center justify-center cursor-pointer hover:opacity-90"
              >
                {unreadMessagesCount > 99 ? '99+' : unreadMessagesCount}
              </button>
            )}
          </div>
          <Link href="/quotes">
            <Button
              variant={pathname?.startsWith('/quotes') ? 'default' : 'ghost'}
              size="sm"
              className={
                pathname?.startsWith('/quotes')
                  ? 'text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }
            >
              <FileText className="h-4 w-4 mr-2" />
              Quotes
            </Button>
          </Link>
          <Link href="/orders">
            <Button
              variant={pathname?.startsWith('/orders') ? 'default' : 'ghost'}
              size="sm"
              className={
                pathname?.startsWith('/orders')
                  ? 'text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }
            >
              <ShoppingCart className="h-4 w-4 mr-2" />
              Orders
            </Button>
          </Link>
          {(isDirector || isCloser) && (
            <Link href="/products">
              <Button
                variant={pathname?.startsWith('/products') ? 'default' : 'ghost'}
                size="sm"
                className={
                  pathname?.startsWith('/products')
                    ? 'text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }
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
              className={
                pathname?.startsWith('/reminders')
                  ? 'text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }
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
          <Link href="/sales-documents">
            <Button
              variant={pathname?.startsWith('/sales-documents') ? 'default' : 'ghost'}
              size="sm"
              className={
                pathname?.startsWith('/sales-documents')
                  ? 'text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }
            >
              <FolderOpen className="h-4 w-4 mr-2" />
              Documents
            </Button>
          </Link>
          {!isCloser && (
            <Link href="/discount-requests" className="relative">
              <Button
                variant={pathname?.startsWith('/discount-requests') ? 'default' : 'ghost'}
                size="sm"
                className={
                  pathname?.startsWith('/discount-requests')
                    ? 'text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }
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
          )}

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
                  <Link href="/settings/users">
                    <DropdownMenuItem className="cursor-pointer">
                      <Users className="h-4 w-4 mr-2" />
                      Users
                    </DropdownMenuItem>
                  </Link>
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
                  <Link href="/settings/quote-templates">
                    <DropdownMenuItem className="cursor-pointer">
                      <FileText className="h-4 w-4 mr-2" />
                      Quote Templates
                    </DropdownMenuItem>
                  </Link>
                  <Link href="/settings/sms-templates">
                    <DropdownMenuItem className="cursor-pointer">
                      <MessageSquare className="h-4 w-4 mr-2" />
                      SMS Templates
                    </DropdownMenuItem>
                  </Link>
                  <Link href="/settings/reminder-triggers">
                    <DropdownMenuItem className="cursor-pointer">
                      <Bell className="h-4 w-4 mr-2" />
                      Reminder Triggers
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

        {/* Mobile menu */}
        <div className="flex lg:hidden">
          <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
            <SheetTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="min-h-11 min-w-11 shrink-0"
                aria-label="Open menu"
              >
                <Menu className="h-6 w-6" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="flex w-[min(100vw,20rem)] flex-col overflow-hidden sm:max-w-sm">
              <SheetTitle className="sr-only">Main navigation</SheetTitle>
              <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto pr-1">
                {isCloser ? (
                  <>
                    <Link
                      href="/leads"
                      onClick={closeMobile}
                      className={cn(
                        mobileNavLinkClass,
                        pathname?.startsWith('/leads') && 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <Users className="h-4 w-4 shrink-0" />
                        Leads
                      </span>
                    </Link>
                    <Link
                      href="/closer-dashboard"
                      onClick={closeMobile}
                      className={cn(
                        mobileNavLinkClass,
                        pathname?.startsWith('/closer-dashboard') && 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <LayoutDashboard className="h-4 w-4 shrink-0" />
                        Dashboard
                      </span>
                      <BadgePill count={closerQualifiedBadgeCount} />
                    </Link>
                  </>
                ) : (
                  <Link
                    href="/leads"
                    onClick={closeMobile}
                    className={cn(
                      mobileNavLinkClass,
                      pathname?.startsWith('/leads') && 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <Users className="h-4 w-4 shrink-0" />
                      Leads
                    </span>
                    <BadgePill count={newLeadsCount} />
                  </Link>
                )}

                <div className="flex flex-col gap-1">
                  <Link
                    href="/customers"
                    onClick={closeMobile}
                    className={cn(
                      mobileNavLinkClass,
                      pathname?.startsWith('/customers') && 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <Users className="h-4 w-4 shrink-0" />
                      Customers
                    </span>
                    <BadgePill count={unreadMessagesCount} />
                  </Link>
                  {unreadMessagesCount > 0 && (
                    <button
                      type="button"
                      onClick={() => {
                        router.push('/customers?has_unread=1');
                        closeMobile();
                      }}
                      className={cn(mobileNavLinkClass, 'text-muted-foreground pl-9 text-xs font-normal')}
                    >
                      View unread only
                    </button>
                  )}
                </div>

                <Link
                  href="/quotes"
                  onClick={closeMobile}
                  className={cn(
                    mobileNavLinkClass,
                    pathname?.startsWith('/quotes') && 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                  )}
                >
                  <span className="flex items-center gap-2">
                    <FileText className="h-4 w-4 shrink-0" />
                    Quotes
                  </span>
                </Link>
                <Link
                  href="/orders"
                  onClick={closeMobile}
                  className={cn(
                    mobileNavLinkClass,
                    pathname?.startsWith('/orders') && 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                  )}
                >
                  <span className="flex items-center gap-2">
                    <ShoppingCart className="h-4 w-4 shrink-0" />
                    Orders
                  </span>
                </Link>
                {(isDirector || isCloser) && (
                  <Link
                    href="/products"
                    onClick={closeMobile}
                    className={cn(
                      mobileNavLinkClass,
                      pathname?.startsWith('/products') && 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <Package className="h-4 w-4 shrink-0" />
                      Products
                    </span>
                  </Link>
                )}
                <Link
                  href="/reminders"
                  onClick={closeMobile}
                  className={cn(
                    mobileNavLinkClass,
                    pathname?.startsWith('/reminders') && 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                  )}
                >
                  <span className="flex items-center gap-2">
                    <Bell className="h-4 w-4 shrink-0" />
                    Reminders
                  </span>
                  <BadgePill count={reminderCount} />
                </Link>
                <Link
                  href="/sales-documents"
                  onClick={closeMobile}
                  className={cn(
                    mobileNavLinkClass,
                    pathname?.startsWith('/sales-documents') && 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                  )}
                >
                  <span className="flex items-center gap-2">
                    <FolderOpen className="h-4 w-4 shrink-0" />
                    Documents
                  </span>
                </Link>
                {!isCloser && (
                  <Link
                    href="/discount-requests"
                    onClick={closeMobile}
                    className={cn(
                      mobileNavLinkClass,
                      pathname?.startsWith('/discount-requests') && 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <Send className="h-4 w-4 shrink-0" />
                      Discount requests
                    </span>
                    {canApproveDiscounts && <BadgePill count={pendingDiscountCount} />}
                  </Link>
                )}

                <div className="my-2 border-t border-border" />

                <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Account
                </p>
                <Link
                  href="/settings/user"
                  onClick={closeMobile}
                  className={cn(
                    mobileNavLinkClass,
                    pathname?.startsWith('/settings/user') && 'bg-accent'
                  )}
                >
                  <span className="flex items-center gap-2">
                    <User className="h-4 w-4 shrink-0" />
                    My Settings
                  </span>
                </Link>
                {isDirector && (
                  <>
                    <Link
                      href="/settings/users"
                      onClick={closeMobile}
                      className={cn(
                        mobileNavLinkClass,
                        pathname?.startsWith('/settings/users') && 'bg-accent'
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <Users className="h-4 w-4 shrink-0" />
                        Users
                      </span>
                    </Link>
                    <Link
                      href="/settings/company"
                      onClick={closeMobile}
                      className={cn(
                        mobileNavLinkClass,
                        pathname?.startsWith('/settings/company') && 'bg-accent'
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <Settings className="h-4 w-4 shrink-0" />
                        Company Settings
                      </span>
                    </Link>
                    <Link
                      href="/settings/email-templates"
                      onClick={closeMobile}
                      className={cn(
                        mobileNavLinkClass,
                        pathname?.startsWith('/settings/email-templates') && 'bg-accent'
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <Mail className="h-4 w-4 shrink-0" />
                        Email Templates
                      </span>
                    </Link>
                    <Link
                      href="/settings/quote-templates"
                      onClick={closeMobile}
                      className={cn(
                        mobileNavLinkClass,
                        pathname?.startsWith('/settings/quote-templates') && 'bg-accent'
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <FileText className="h-4 w-4 shrink-0" />
                        Quote Templates
                      </span>
                    </Link>
                    <Link
                      href="/settings/sms-templates"
                      onClick={closeMobile}
                      className={cn(
                        mobileNavLinkClass,
                        pathname?.startsWith('/settings/sms-templates') && 'bg-accent'
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <MessageSquare className="h-4 w-4 shrink-0" />
                        SMS Templates
                      </span>
                    </Link>
                    <Link
                      href="/settings/reminder-triggers"
                      onClick={closeMobile}
                      className={cn(
                        mobileNavLinkClass,
                        pathname?.startsWith('/settings/reminder-triggers') && 'bg-accent'
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <Bell className="h-4 w-4 shrink-0" />
                        Reminder Triggers
                      </span>
                    </Link>
                    <Link
                      href="/discounts"
                      onClick={closeMobile}
                      className={cn(
                        mobileNavLinkClass,
                        pathname?.startsWith('/discounts') && 'bg-accent'
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <Gift className="h-4 w-4 shrink-0" />
                        Discounts & Giveaways
                      </span>
                    </Link>
                  </>
                )}

                <button
                  type="button"
                  onClick={() => {
                    closeMobile();
                    handleLogout();
                  }}
                  className={cn(mobileNavLinkClass, 'text-destructive hover:text-destructive hover:bg-destructive/10')}
                >
                  <span className="flex items-center gap-2">
                    <LogOut className="h-4 w-4 shrink-0" />
                    Logout
                  </span>
                </button>
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
