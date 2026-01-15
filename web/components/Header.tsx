'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import Logo from './Logo';
import { Button } from '@/components/ui/button';
import { LogOut, LayoutDashboard, Users, Settings, Package, User, Mail, Bell } from 'lucide-react';
import api from '@/lib/api';

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
          <Link href="/dashboard">
            <Button
              variant={pathname === '/dashboard' ? 'default' : 'ghost'}
              size="sm"
              className="text-muted-foreground hover:text-foreground"
            >
              <LayoutDashboard className="h-4 w-4 mr-2" />
              Dashboard
            </Button>
          </Link>
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
          {isDirector && (
            <>
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
              <Link href="/settings/email-templates">
                <Button
                  variant={pathname?.startsWith('/settings/email-templates') ? 'default' : 'ghost'}
                  size="sm"
                  className="text-muted-foreground hover:text-foreground"
                >
                  <Mail className="h-4 w-4 mr-2" />
                  Email Templates
                </Button>
              </Link>
              <Link href="/settings/company">
                <Button
                  variant={pathname === '/settings/company' ? 'default' : 'ghost'}
                  size="sm"
                  className="text-muted-foreground hover:text-foreground"
                >
                  <Settings className="h-4 w-4 mr-2" />
                  Company Settings
                </Button>
              </Link>
            </>
          )}
          <Link href="/settings/user">
            <Button
              variant={pathname === '/settings/user' ? 'default' : 'ghost'}
              size="sm"
              className="text-muted-foreground hover:text-foreground"
            >
              <User className="h-4 w-4 mr-2" />
              My Settings
            </Button>
          </Link>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleLogout}
            className="text-muted-foreground hover:text-foreground"
          >
            <LogOut className="h-4 w-4 mr-2" />
            Logout
          </Button>
        </nav>
      </div>
    </header>
  );
}
