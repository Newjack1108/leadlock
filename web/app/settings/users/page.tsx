'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Users, Plus, Pencil, UserX } from 'lucide-react';
import api from '@/lib/api';
import { listUsers, createUser, updateUser, deactivateUser } from '@/lib/api';
import { UserList } from '@/lib/types';
import { toast } from 'sonner';

const ROLES = ['DIRECTOR', 'SALES_MANAGER', 'CLOSER'] as const;

export default function UsersPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [users, setUsers] = useState<UserList[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserList | null>(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    email: '',
    full_name: '',
    password: '',
    role: 'CLOSER' as string,
  });

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

  useEffect(() => {
    if (userRole === 'DIRECTOR') {
      fetchUsers();
    } else if (userRole !== null) {
      setLoading(false);
    }
  }, [userRole]);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const data = await listUsers();
      setUsers(data);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else if (error.response?.status === 403) {
        toast.error('Access denied. Director only.');
        router.push('/dashboard');
      } else {
        toast.error('Failed to load users');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingUser(null);
    setFormData({
      email: '',
      full_name: '',
      password: '',
      role: 'CLOSER',
    });
    setDialogOpen(true);
  };

  const handleEdit = (user: UserList) => {
    setEditingUser(user);
    setFormData({
      email: user.email,
      full_name: user.full_name,
      password: '',
      role: user.role,
    });
    setDialogOpen(true);
  };

  const handleDeactivate = async (user: UserList) => {
    if (!confirm(`Are you sure you want to deactivate ${user.full_name}? They will not be able to log in.`)) {
      return;
    }
    try {
      await deactivateUser(user.id);
      toast.success('User deactivated');
      fetchUsers();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to deactivate user');
    }
  };

  const handleSave = async () => {
    if (!formData.full_name.trim()) {
      toast.error('Full name is required');
      return;
    }
    if (!editingUser && !formData.password.trim()) {
      toast.error('Password is required when creating a new user');
      return;
    }
    if (!editingUser && !formData.email.trim()) {
      toast.error('Email is required');
      return;
    }

    try {
      setSaving(true);
      if (editingUser) {
        const payload: { full_name?: string; role?: string; password?: string } = {
          full_name: formData.full_name.trim(),
          role: formData.role,
        };
        if (formData.password.trim()) {
          payload.password = formData.password;
        }
        await updateUser(editingUser.id, payload);
        toast.success('User updated successfully');
      } else {
        await createUser({
          email: formData.email.trim(),
          full_name: formData.full_name.trim(),
          password: formData.password,
          role: formData.role,
        });
        toast.success('User created successfully');
      }
      setDialogOpen(false);
      fetchUsers();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save user');
    } finally {
      setSaving(false);
    }
  };

  if (userRole !== null && userRole !== 'DIRECTOR') {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">
            Access denied. This page is for directors only.
          </div>
        </main>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Users</h1>
            <p className="text-muted-foreground mt-2">
              Manage team members and their roles
            </p>
          </div>
          <Button onClick={handleCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Add User
          </Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Team Members
            </CardTitle>
            <CardDescription>
              Create and manage user accounts. Inactive users cannot log in.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {users.length === 0 ? (
              <p className="text-muted-foreground text-center py-8">
                No users yet. Click &quot;Add User&quot; to create the first team member.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-3 px-4 font-medium">Email</th>
                      <th className="text-left py-3 px-4 font-medium">Name</th>
                      <th className="text-left py-3 px-4 font-medium">Role</th>
                      <th className="text-left py-3 px-4 font-medium">Status</th>
                      <th className="text-right py-3 px-4 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((user) => (
                      <tr
                        key={user.id}
                        className={`border-b last:border-0 ${!user.is_active ? 'opacity-60' : ''}`}
                      >
                        <td className="py-3 px-4">{user.email}</td>
                        <td className="py-3 px-4">{user.full_name}</td>
                        <td className="py-3 px-4">
                          <Badge variant="secondary">{user.role.replace('_', ' ')}</Badge>
                        </td>
                        <td className="py-3 px-4">
                          {user.is_active ? (
                            <Badge variant="default">Active</Badge>
                          ) : (
                            <Badge variant="outline" className="text-muted-foreground">
                              Inactive
                            </Badge>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right">
                          {user.is_active && (
                            <div className="flex justify-end gap-2">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleEdit(user)}
                              >
                                <Pencil className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-destructive hover:text-destructive"
                                onClick={() => handleDeactivate(user)}
                                title="Deactivate"
                              >
                                <UserX className="h-4 w-4" />
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{editingUser ? 'Edit User' : 'Add User'}</DialogTitle>
              <DialogDescription>
                {editingUser
                  ? 'Update the user details. Leave password blank to keep the current password.'
                  : 'Create a new team member. They will be able to log in with the email and password you set.'}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="user@example.com"
                  disabled={!!editingUser}
                />
                {editingUser && (
                  <p className="text-xs text-muted-foreground">Email cannot be changed</p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="full_name">Full Name</Label>
                <Input
                  id="full_name"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                  placeholder="John Smith"
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">
                  Password {editingUser && '(leave blank to keep current)'}
                </Label>
                <Input
                  id="password"
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  placeholder={editingUser ? '••••••••' : 'Enter password'}
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="role">Role</Label>
                <Select
                  value={formData.role}
                  onValueChange={(v) => setFormData({ ...formData, role: v })}
                  disabled={saving}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ROLES.map((r) => (
                      <SelectItem key={r} value={r}>
                        {r.replace('_', ' ')}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Director: full access. Sales Manager: can approve discounts. Closer: standard access.
                </p>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? 'Saving...' : editingUser ? 'Update' : 'Create'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}
