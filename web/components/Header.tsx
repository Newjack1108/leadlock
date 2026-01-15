'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import Logo from './Logo';
import { Button } from '@/components/ui/button';
import { LogOut, Users, Settings, Package, User, Mail, Bell, FileText, ShoppingCart, ChevronDown } from 'lucide-react';
import api from '@/lib/api';
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

  return (
    <header className="border-b border-border bg-card shadow-sm">
      <div className="container mx-auto px-6 py-0 flex items-center justify-between">
        <Logo />
        <nav className="flex items-center gap-4">
          {/* Main Navigation */}
          <Link href="/leads">
            <Button
              variant={pathname?.startsWith('/leads') ? 'default' : 'ghost'}
              size="sm"
              className="text-muted-foreground hover:text-foreground"
            >
              <Users className="h-4 w-4 mr-2" />
              Leads
            </Button>
          </Link>
          <Link href="/customers">
            <Button
              variant={pathname?.startsWith('/customers') ? 'default' : 'ghost'}
              size="sm"
              className="text-muted-foreground hover:text-foreground"
            >
              <Users className="h-4 w-4 mr-2" />
              Customers
            </Button>
          </Link>
          <Link href="/quotes">
            <Button
              variant={pathname?.startsWith('/quotes') ? 'default' : 'ghost'}
              size="sm"
              className="text-muted-foreground hover:text-foreground"
            >
              <FileText className="h-4 w-4 mr-2" />
              Quotes
            </Button>
          </Link>
          <Link href="/orders">
            <Button
              variant={pathname?.startsWith('/orders') ? 'default' : 'ghost'}
              size="sm"
              className="text-muted-foreground hover:text-foreground"
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
                className="text-muted-foreground hover:text-foreground"
              >
                <Package className="h-4 w-4 mr-2" />
                Products
              </Button>
            </Link>
          )}
          <Link href="/reminders">
            <Button
              variant={pathname?.startsWith('/reminders') ? 'default' : 'ghost'}
              size="sm"
              className="text-muted-foreground hover:text-foreground"
            >
              <Bell className="h-4 w-4 mr-2" />
              Reminders
            </Button>
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
