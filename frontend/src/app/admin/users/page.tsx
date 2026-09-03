'use client';

import { useState, useEffect } from 'react';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { adminAPI } from '@/lib/api';
import Link from 'next/link';
import {User, Users, Building, Plus, Edit, Trash2, Eye, Search, Filter, Shield, UserCheck, UserX} from 'lucide-react';

interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  organization_name: string;
  organization_id: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
}

function AdminUsersContent() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterRole, setFilterRole] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      
      const usersList = await adminAPI.getUsers();
      const transformedUsers: AdminUser[] = usersList.map((user: any) => ({
        id: user.id.toString(),
        email: user.email,
        full_name: user.full_name || 'N/A',
        role: user.role,
        organization_name: user.organization?.name || 'No Organization',
        organization_id: user.organization_id?.toString() || '',
        is_active: user.is_active,
        is_superuser: user.is_superuser,
        created_at: user.created_at
      }));
      setUsers(transformedUsers);
    } catch (error) {
      console.error('Error fetching users:', error);
      setUsers([]);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteUser = async (userId: string, userName: string, userEmail: string) => {
    const confirmMessage = `Are you sure you want to delete the user "${userName}" (${userEmail})?\n\nNote: If this user owns datasets, they will be automatically transferred to your admin account. This action cannot be undone.`;
    
    if (!confirm(confirmMessage)) {
      return;
    }

    try {
      const result = await adminAPI.deleteUser(parseInt(userId), true, true);
      
      // Remove the user from the local state
      setUsers(prev => prev.filter(user => user.id !== userId));
      
      // Show detailed success message
      let successMessage = `User "${userName}" has been successfully deleted.`;
      if (result.datasets_affected > 0) {
        successMessage += `\n\n${result.datasets_affected} dataset(s) have been transferred to your admin account.`;
      }
      alert(successMessage);
      
    } catch (error: any) {
      console.error('Error deleting user:', error);
      
      // Show error message
      const errorMessage = error.response?.data?.detail || 'Failed to delete user';
      alert(`Error: ${errorMessage}`);
    }
  };

  const getRoleColor = (role: string) => {
    switch (role.toLowerCase()) {
      case 'owner': return 'bg-purple-100 text-purple-800';
      case 'admin': return 'bg-red-100 text-red-800';
      case 'manager': return 'bg-blue-100 text-blue-800';
      case 'member': return 'bg-green-100 text-green-800';
      case 'viewer': return 'bg-gray-100 text-gray-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusColor = (isActive: boolean) => {
    return isActive ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800';
  };

  const filteredUsers = users.filter(user => {
    const matchesSearch = 
      user.full_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      user.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
      user.organization_name.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesRole = filterRole === 'all' || user.role === filterRole;
    const matchesStatus = filterStatus === 'all' || 
      (filterStatus === 'active' && user.is_active) ||
      (filterStatus === 'inactive' && !user.is_active) ||
      (filterStatus === 'superuser' && user.is_superuser);
    
    return matchesSearch && matchesRole && matchesStatus;
  });

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <ProtectedRoute requireAdmin>
      <DashboardLayout>
        <div className="py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold text-gray-900">Users Management</h1>
                <p className="mt-2 text-gray-600">Manage and monitor all users in the platform</p>
              </div>
              <Link href="/admin">
                <button className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700">
                  Back to Admin Panel
                </button>
              </Link>
            </div>
          </div>

          {/* Search and Filters */}
          <div className="mb-6 flex flex-col sm:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
              <input
                type="text"
                placeholder="Search users by name, email, or organization..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              />
            </div>
            <div className="flex items-center space-x-2">
              <Filter className="w-5 h-5 text-gray-400" />
              <select
                value={filterRole}
                onChange={(e) => setFilterRole(e.target.value)}
                className="px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900 transition-colors hover:border-gray-400"
              >
                <option value="all">👤 All Roles</option>
                <option value="owner">👑 Owner</option>
                <option value="admin">🛡️ Admin</option>
                <option value="manager">📋 Manager</option>
                <option value="member">👥 Member</option>
                <option value="viewer">👁️ Viewer</option>
              </select>
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900 transition-colors hover:border-gray-400"
              >
                <option value="all">📊 All Status</option>
                <option value="active">✅ Active</option>
                <option value="inactive">❌ Inactive</option>
                <option value="superuser">🔑 Superusers</option>
              </select>
            </div>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center space-x-2">
              <Plus className="w-4 h-4" />
              <span>Add User</span>
            </button>
          </div>

          {/* Users Table */}
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      User
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Organization
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Role
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Created
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {filteredUsers.map((user) => (
                    <tr key={user.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4">
                        <div className="flex items-center">
                          <div className="flex-shrink-0">
                            <div className="h-8 w-8 bg-gray-400 rounded-full flex items-center justify-center">
                              {user.is_superuser ? (
                                <Shield className="h-4 w-4 text-white" />
                              ) : (
                                <User className="h-4 w-4 text-white" />
                              )}
                            </div>
                          </div>
                          <div className="ml-4">
                            <div className="text-sm font-medium text-gray-900">
                              {user.full_name}
                              {user.is_superuser && (
                                <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                                  🔑
                                </span>
                              )}
                            </div>
                            <div className="text-sm text-gray-500">{user.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          <Building className="w-4 h-4 text-gray-400 mr-2" />
                          <span className="text-sm text-gray-900">{user.organization_name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-2 py-1 text-xs rounded-full ${getRoleColor(user.role)}`}>
                          {user.role.charAt(0).toUpperCase() + user.role.slice(1)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-2 py-1 text-xs rounded-full ${getStatusColor(user.is_active)}`}>
                          {user.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {new Date(user.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                        <div className="flex items-center space-x-2">
                          <button className="text-blue-600 hover:text-blue-900" title="View user">
                            <Eye className="w-4 h-4" />
                          </button>
                          <button className="text-indigo-600 hover:text-indigo-900" title="Edit user">
                            <Edit className="w-4 h-4" />
                          </button>
                          <button 
                            className="text-red-600 hover:text-red-900"
                            onClick={() => handleDeleteUser(user.id, user.full_name, user.email)}
                            title="Delete user"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {filteredUsers.length === 0 && (
            <div className="text-center py-12">
              <Users className="mx-auto h-12 w-12 text-gray-400" />
              <h3 className="mt-2 text-sm font-medium text-gray-900">No users found</h3>
              <p className="mt-1 text-sm text-gray-500">
                {searchTerm || filterRole !== 'all' || filterStatus !== 'all'
                  ? 'Try adjusting your search or filter criteria.'
                  : 'Get started by creating a new user.'}
              </p>
            </div>
          )}

          {/* Users Summary */}
          <div className="mt-8 grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-lg p-4 shadow">
              <div className="flex items-center">
                <Users className="h-8 w-8 text-blue-600" />
                <div className="ml-3">
                  <p className="text-sm text-gray-500">Total Users</p>
                  <p className="text-lg font-semibold text-gray-900">{users.length}</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-lg p-4 shadow">
              <div className="flex items-center">
                <UserCheck className="h-8 w-8 text-green-600" />
                <div className="ml-3">
                  <p className="text-sm text-gray-500">Active Users</p>
                  <p className="text-lg font-semibold text-gray-900">{users.filter(u => u.is_active).length}</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-lg p-4 shadow">
              <div className="flex items-center">
                <Shield className="h-8 w-8 text-yellow-600" />
                <div className="ml-3">
                  <p className="text-sm text-gray-500">Superusers</p>
                  <p className="text-lg font-semibold text-gray-900">{users.filter(u => u.is_superuser).length}</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-lg p-4 shadow">
              <div className="flex items-center">
                <UserX className="h-8 w-8 text-red-600" />
                <div className="ml-3">
                  <p className="text-sm text-gray-500">Inactive Users</p>
                  <p className="text-lg font-semibold text-gray-900">{users.filter(u => !u.is_active).length}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}

export default function AdminUsersPage() {
  return <AdminUsersContent />;
}