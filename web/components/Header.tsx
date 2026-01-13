'use client';

import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import Logo from './Logo';
import { Button } from '@/components/ui/button';
import { LogOut, LayoutDashboard, Users } from 'lucide-react';

export default function Header() {
  const router = useRouter();
  const pathname = usePathname();

  const handleLogout = () => {
    localStorage.removeItem('token');
    router.push('/login');
  };

  return (
    <header className="border-b border-border bg-card">
      <div className="container mx-auto px-6 py-4 flex items-center justify-between">
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
