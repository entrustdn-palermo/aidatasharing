'use client';

import { useState, useEffect } from 'react';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { adminAPI } from '@/lib/api';
import Link from 'next/link';
import {Users, Building, Plus, Edit, Trash2, Eye, Search, Filter, X, Save, Calendar, Mail, Globe} from 'lucide-react';

interface Organization {
  id: string;
  name: string;
  type: string;
  description: string;
  memberCount: number;
  createdDate: string;
  status: 'active' | 'inactive' | 'suspended';
  adminEmail: string;
  website?: string;
  is_active: boolean;
  allow_external_sharing?: boolean;
  default_sharing_level?: string;
  created_at: string;
  updated_at: string;
}

function AdminOrganizationsContent() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [viewModalOpen, setViewModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [selectedOrganization, setSelectedOrganization] = useState<Organization | null>(null);
  const [editFormData, setEditFormData] = useState({
    name: '',
    description: '',
    type: '',
    contact_email: '',
    website: '',
    is_active: true,
    allow_external_sharing: true,
    default_sharing_level: 'organization'
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchOrganizations();
  }, []);

  const fetchOrganizations = async () => {
    try {
      setLoading(true);
      
      // Use the API client instead of direct fetch
      const orgsList = await adminAPI.getOrganizations();
      const transformedOrgs: Organization[] = orgsList.map((org: any) => ({
        id: org.id.toString(),
        name: org.name,
        type: org.type,
        description: org.description || '',
        memberCount: org.user_count || 0,
        createdDate: org.created_at,
        status: org.is_active ? 'active' : 'inactive',
        adminEmail: org.contact_email || 'N/A',
        website: org.website,
        is_active: org.is_active,
        allow_external_sharing: org.allow_external_sharing,
        default_sharing_level: org.default_sharing_level,
        created_at: org.created_at,
        updated_at: org.updated_at
      }));
      setOrganizations(transformedOrgs);
    } catch (error) {
      console.error('Error fetching organizations:', error);
      setOrganizations([]);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteOrganization = async (orgId: string, orgName: string) => {
    if (!confirm(`Are you sure you want to delete the organization "${orgName}"? This action will soft-delete the organization and cannot be easily undone.`)) {
      return;
    }

    try {
      await adminAPI.deleteOrganization(parseInt(orgId));
      
      // Remove the organization from the local state
      setOrganizations(prev => prev.filter(org => org.id !== orgId));
      
      // Show success message
      alert(`Organization "${orgName}" has been successfully deleted.`);
    } catch (error: any) {
      console.error('Error deleting organization:', error);
      
      // Show error message
      const errorMessage = error.response?.data?.detail || 'Failed to delete organization';
      alert(`Error: ${errorMessage}`);
    }
  };

  const handleViewOrganization = (org: Organization) => {
    setSelectedOrganization(org);
    setViewModalOpen(true);
  };

  const handleEditOrganization = (org: Organization) => {
    setSelectedOrganization(org);
    setEditFormData({
      name: org.name,
      description: org.description || '',
      type: org.type,
      contact_email: org.adminEmail,
      website: org.website || '',
      is_active: org.is_active,
      allow_external_sharing: org.allow_external_sharing || true,
      default_sharing_level: org.default_sharing_level || 'organization'
    });
    setEditModalOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!selectedOrganization) return;

    try {
      setSaving(true);
      
      await adminAPI.updateOrganization(parseInt(selectedOrganization.id), {
        name: editFormData.name,
        description: editFormData.description,
        type: editFormData.type,
        is_active: editFormData.is_active
      });

      // Update the organization in the local state
      setOrganizations(prev => prev.map(org => 
        org.id === selectedOrganization.id 
          ? {
              ...org,
              name: editFormData.name,
              description: editFormData.description,
              type: editFormData.type,
              is_active: editFormData.is_active,
              status: editFormData.is_active ? 'active' : 'inactive',
              adminEmail: editFormData.contact_email
            }
          : org
      ));

      setEditModalOpen(false);
      setSelectedOrganization(null);
      alert('Organization updated successfully!');
    } catch (error: any) {
      console.error('Error updating organization:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to update organization';
      alert(`Error: ${errorMessage}`);
    } finally {
      setSaving(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-100 text-green-800';
      case 'inactive': return 'bg-gray-100 text-gray-800';
      case 'suspended': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const filteredOrganizations = organizations.filter(org => {
    const matchesSearch = org.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         org.description.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = filterStatus === 'all' || org.status === filterStatus;
    return matchesSearch && matchesStatus;
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
                <h1 className="text-3xl font-bold text-gray-900">Organizations Management</h1>
                <p className="mt-2 text-gray-600">Manage and monitor all organizations in the platform</p>
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
                placeholder="Search organizations by name or type..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              />
            </div>
            <div className="flex items-center space-x-2">
              <Filter className="w-5 h-5 text-gray-400" />
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900 transition-colors hover:border-gray-400"
              >
                <option value="all">📊 All Status</option>
                <option value="active">✅ Active</option>
                <option value="inactive">⚪ Inactive</option>
                <option value="suspended">🚫 Suspended</option>
              </select>
            </div>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center space-x-2">
              <Plus className="w-4 h-4" />
              <span>Add Organization</span>
            </button>
          </div>

          {/* Organizations Table */}
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Organization
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Type
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Members
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
                  {filteredOrganizations.map((org) => (
                    <tr key={org.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4">
                        <div className="flex items-center">
                          <div className="flex-shrink-0">
                            <Building className="h-8 w-8 text-gray-400" />
                          </div>
                          <div className="ml-4">
                            <div className="text-sm font-medium text-gray-900">{org.name}</div>
                            <div className="text-sm text-gray-500">{org.description}</div>
                            <div className="text-xs text-gray-400">{org.adminEmail}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className="px-2 py-1 text-xs rounded-full bg-blue-100 text-blue-800">
                          {org.type}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        <div className="flex items-center">
                          <Users className="w-4 h-4 text-gray-400 mr-1" />
                          {org.memberCount}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-2 py-1 text-xs rounded-full ${getStatusColor(org.status)}`}>
                          {org.status.charAt(0).toUpperCase() + org.status.slice(1)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {new Date(org.createdDate).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                        <div className="flex items-center space-x-2">
                          <button 
                            className="text-blue-600 hover:text-blue-900"
                            onClick={() => handleViewOrganization(org)}
                            title="View organization details"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          <button 
                            className="text-indigo-600 hover:text-indigo-900"
                            onClick={() => handleEditOrganization(org)}
                            title="Edit organization"
                          >
                            <Edit className="w-4 h-4" />
                          </button>
                          <button 
                            className="text-red-600 hover:text-red-900"
                            onClick={() => handleDeleteOrganization(org.id, org.name)}
                            title="Delete organization"
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

          {filteredOrganizations.length === 0 && (
            <div className="text-center py-12">
              <Building className="mx-auto h-12 w-12 text-gray-400" />
              <h3 className="mt-2 text-sm font-medium text-gray-900">No organizations found</h3>
              <p className="mt-1 text-sm text-gray-500">
                {searchTerm || filterStatus !== 'all' 
                  ? 'Try adjusting your search or filter criteria.'
                  : 'Get started by creating a new organization.'}
              </p>
            </div>
          )}

          {/* View Organization Modal */}
          {viewModalOpen && selectedOrganization && (
            <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
              <div className="bg-white rounded-lg p-6 w-full max-w-2xl mx-4 max-h-screen overflow-y-auto">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-2xl font-bold text-gray-900 flex items-center">
                    <Building className="mr-2 h-6 w-6 text-blue-600" />
                    Organization Details
                  </h2>
                  <button 
                    onClick={() => setViewModalOpen(false)}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    <X className="w-6 h-6" />
                  </button>
                </div>

                <div className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Organization Name</label>
                      <div className="bg-gray-50 p-3 rounded-lg">
                        <p className="text-gray-900 font-semibold">{selectedOrganization.name}</p>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Type</label>
                      <div className="bg-gray-50 p-3 rounded-lg">
                        <span className="px-2 py-1 text-xs rounded-full bg-blue-100 text-blue-800">
                          {selectedOrganization.type}
                        </span>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Status</label>
                      <div className="bg-gray-50 p-3 rounded-lg">
                        <span className={`px-2 py-1 text-xs rounded-full ${getStatusColor(selectedOrganization.status)}`}>
                          {selectedOrganization.status.charAt(0).toUpperCase() + selectedOrganization.status.slice(1)}
                        </span>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Member Count</label>
                      <div className="bg-gray-50 p-3 rounded-lg flex items-center">
                        <Users className="w-4 h-4 text-gray-400 mr-2" />
                        <span className="text-gray-900">{selectedOrganization.memberCount}</span>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Contact Email</label>
                      <div className="bg-gray-50 p-3 rounded-lg flex items-center">
                        <Mail className="w-4 h-4 text-gray-400 mr-2" />
                        <span className="text-gray-900">{selectedOrganization.adminEmail}</span>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Created Date</label>
                      <div className="bg-gray-50 p-3 rounded-lg flex items-center">
                        <Calendar className="w-4 h-4 text-gray-400 mr-2" />
                        <span className="text-gray-900">{new Date(selectedOrganization.createdDate).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Description</label>
                    <div className="bg-gray-50 p-3 rounded-lg">
                      <p className="text-gray-900">{selectedOrganization.description || 'No description provided'}</p>
                    </div>
                  </div>

                  {selectedOrganization.website && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Website</label>
                      <div className="bg-gray-50 p-3 rounded-lg flex items-center">
                        <Globe className="w-4 h-4 text-gray-400 mr-2" />
                        <a 
                          href={selectedOrganization.website} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800"
                        >
                          {selectedOrganization.website}
                        </a>
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-8 flex justify-end">
                  <button
                    onClick={() => setViewModalOpen(false)}
                    className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Edit Organization Modal */}
          {editModalOpen && selectedOrganization && (
            <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
              <div className="bg-white rounded-lg p-6 w-full max-w-2xl mx-4 max-h-screen overflow-y-auto">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-2xl font-bold text-gray-900 flex items-center">
                    <Edit className="mr-2 h-6 w-6 text-indigo-600" />
                    Edit Organization
                  </h2>
                  <button 
                    onClick={() => setEditModalOpen(false)}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    <X className="w-6 h-6" />
                  </button>
                </div>

                <div className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Organization Name *</label>
                      <input
                        type="text"
                        value={editFormData.name}
                        onChange={(e) => setEditFormData({ ...editFormData, name: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        placeholder="Enter organization name"
                        required
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Type *</label>
                      <select
                        value={editFormData.type}
                        onChange={(e) => setEditFormData({ ...editFormData, type: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        required
                      >
                        <option value="">Select type</option>
                        <option value="enterprise">Enterprise</option>
                        <option value="startup">Startup</option>
                        <option value="non_profit">Non-profit</option>
                        <option value="government">Government</option>
                        <option value="education">Education</option>
                        <option value="other">Other</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Contact Email</label>
                      <input
                        type="email"
                        value={editFormData.contact_email}
                        onChange={(e) => setEditFormData({ ...editFormData, contact_email: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        placeholder="Enter contact email"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Website</label>
                      <input
                        type="url"
                        value={editFormData.website}
                        onChange={(e) => setEditFormData({ ...editFormData, website: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        placeholder="https://example.com"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Description</label>
                    <textarea
                      value={editFormData.description}
                      onChange={(e) => setEditFormData({ ...editFormData, description: e.target.value })}
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                      placeholder="Enter organization description"
                    />
                  </div>

                  <div className="flex items-center space-x-4">
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={editFormData.is_active}
                        onChange={(e) => setEditFormData({ ...editFormData, is_active: e.target.checked })}
                        className="mr-2 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                      />
                      <span className="text-sm text-gray-700">Active organization</span>
                    </label>

                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={editFormData.allow_external_sharing}
                        onChange={(e) => setEditFormData({ ...editFormData, allow_external_sharing: e.target.checked })}
                        className="mr-2 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                      />
                      <span className="text-sm text-gray-700">Allow external sharing</span>
                    </label>
                  </div>
                </div>

                <div className="mt-8 flex justify-end space-x-3">
                  <button
                    onClick={() => setEditModalOpen(false)}
                    className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleSaveEdit}
                    disabled={saving || !editFormData.name || !editFormData.type}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center"
                  >
                    {saving ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                        Saving...
                      </>
                    ) : (
                      <>
                        <Save className="w-4 h-4 mr-2" />
                        Save Changes
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}

export default function AdminOrganizationsPage() {
  return <AdminOrganizationsContent />;
}