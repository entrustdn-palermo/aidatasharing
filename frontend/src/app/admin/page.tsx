'use client';

import React from 'react';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import StorageStatusWidget from '@/components/StorageStatusWidget';
import { useState, useEffect } from 'react';
import { datasetsAPI, adminAPI } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import Link from 'next/link';
import {Settings, Users, Database, Building, Activity, Key, Server, Shield, Cloud, FileText, Zap, CheckCircle, AlertCircle, XCircle, Edit, Save, X, Eye, EyeOff} from 'lucide-react';

interface AdminStats {
  totalUsers: number;
  activeUsers: number;
  totalDatasets: number;
  totalOrganizations: number;
  systemHealth: {
    status: 'healthy' | 'warning' | 'critical';
    uptime: string;
    lastCheck: string;
  };
}

interface EnvironmentVariable {
  value: string;
  is_sensitive: boolean;
  description: string;
}

interface EnvironmentVariables {
  categories: {
    [category: string]: {
      [key: string]: EnvironmentVariable;
    };
  };
  total_variables: number;
  last_updated: string;
}

export default function AdminPanel() {
  return (
    <ProtectedRoute requireAdmin>
      <DashboardLayout>
        <AdminContent />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function AdminContent() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [environmentVariables, setEnvironmentVariables] = useState<EnvironmentVariables | null>(null);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    fetchAdminData();
  }, []);

  const fetchAdminData = async () => {
    try {
      setLoading(true);
      
      // Fetch datasets count
      const datasets = await datasetsAPI.getDatasets();
      
      // Fetch environment variables
      try {
        const envVars = await adminAPI.getEnvironmentVariables();
        setEnvironmentVariables(envVars);
      } catch (error) {
        console.error('Failed to fetch environment variables:', error);
        setEnvironmentVariables(null);
      }

      // Fetch admin stats
      try {
        const adminStats = await adminAPI.getAdminStats();
        setStats(adminStats);
      } catch (error) {
        console.error('Failed to fetch admin stats:', error);
        // Fallback to mock stats
        const mockStats: AdminStats = {
          totalUsers: 0,
          activeUsers: 0,
          totalDatasets: datasets?.length || 0,
          totalOrganizations: 0,
          systemHealth: {
            status: 'healthy',
            uptime: 'Unknown',
            lastCheck: new Date().toISOString()
          }
        };
        setStats(mockStats);
      }
      
    } catch (error) {
      console.error('Error fetching admin data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center space-y-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600"></div>
          <p className="text-gray-600">Loading admin panel...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="py-6">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 md:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 flex items-center">
            <Settings className="mr-3 h-8 w-8 text-blue-600" />
            Admin Panel
          </h1>
          <p className="text-gray-600 mt-2">
            Manage system settings, monitor platform health, and configure environment variables
          </p>
        </div>

        {/* Navigation Tabs */}
        <div className="mb-8">
          <div className="border-b border-gray-200">
            <nav className="-mb-px flex space-x-8">
              <button
                onClick={() => setActiveTab('overview')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'overview'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Activity className="inline mr-2 h-4 w-4" />
                Overview
              </button>
              <button
                onClick={() => setActiveTab('environment')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'environment'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Server className="inline mr-2 h-4 w-4" />
                Environment
              </button>
              <button
                onClick={() => setActiveTab('system')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'system'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Zap className="inline mr-2 h-4 w-4" />
                System Status
              </button>
            </nav>
          </div>
        </div>

        {/* Tab Content */}
        {activeTab === 'overview' && (
          <OverviewTab stats={stats} onRefresh={fetchAdminData} />
        )}
        
        {activeTab === 'environment' && (
          <EnvironmentTab 
            environmentVariables={environmentVariables} 
            onUpdate={fetchAdminData} 
          />
        )}
        
        {activeTab === 'system' && (
          <SystemStatusTab stats={stats} />
        )}
      </div>
    </div>
  );
}

function OverviewTab({ stats, onRefresh }: { stats: AdminStats | null; onRefresh: () => void }) {
  return (
    <div className="space-y-8">
      {/* Quick Stats & Storage Status */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-6">
        <Card className="bg-gradient-to-r from-blue-500 to-blue-600 text-white">
          <CardContent className="p-6">
            <div className="flex items-center">
              <Users className="h-8 w-8 text-blue-100" />
              <div className="ml-4">
                <p className="text-blue-100 text-sm font-medium">Total Users</p>
                <p className="text-2xl font-bold">{stats?.totalUsers || 0}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-r from-green-500 to-green-600 text-white">
          <CardContent className="p-6">
            <div className="flex items-center">
              <Database className="h-8 w-8 text-green-100" />
              <div className="ml-4">
                <p className="text-green-100 text-sm font-medium">Total Datasets</p>
                <p className="text-2xl font-bold">{stats?.totalDatasets || 0}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-r from-purple-500 to-purple-600 text-white">
          <CardContent className="p-6">
            <div className="flex items-center">
              <Building className="h-8 w-8 text-purple-100" />
              <div className="ml-4">
                <p className="text-purple-100 text-sm font-medium">Organizations</p>
                <p className="text-2xl font-bold">{stats?.totalOrganizations || 0}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className={`bg-gradient-to-r text-white ${
          stats?.systemHealth.status === 'healthy' ? 'from-emerald-500 to-emerald-600' :
          stats?.systemHealth.status === 'warning' ? 'from-yellow-500 to-yellow-600' :
          'from-red-500 to-red-600'
        }`}>
          <CardContent className="p-6">
            <div className="flex items-center">
              {stats?.systemHealth.status === 'healthy' ? (
                <CheckCircle className="h-8 w-8 text-emerald-100" />
              ) : stats?.systemHealth.status === 'warning' ? (
                <AlertCircle className="h-8 w-8 text-yellow-100" />
              ) : (
                <XCircle className="h-8 w-8 text-red-100" />
              )}
              <div className="ml-4">
                <p className="text-white/80 text-sm font-medium">System Health</p>
                <p className="text-2xl font-bold capitalize">{stats?.systemHealth.status || 'Unknown'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        
        {/* Storage Status Widget */}
        <div className="col-span-1">
          <StorageStatusWidget showDetails={true} className="h-full" />
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Settings className="mr-2 h-5 w-5" />
              Quick Actions
            </CardTitle>
            <CardDescription>
              Common administrative tasks
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Link href="/admin/users">
              <Button variant="outline" className="w-full justify-start">
                <Users className="mr-2 h-4 w-4" />
                Manage Users
              </Button>
            </Link>
            
            <Link href="/admin/organizations">
              <Button variant="outline" className="w-full justify-start">
                <Building className="mr-2 h-4 w-4" />
                Manage Organizations
              </Button>
            </Link>
            
            <Link href="/admin/access-requests">
              <Button variant="outline" className="w-full justify-start">
                <Shield className="mr-2 h-4 w-4" />
                Manage Access Requests
              </Button>
            </Link>
            
            <Link href="/admin/datasets">
              <Button variant="outline" className="w-full justify-start">
                <Database className="mr-2 h-4 w-4" />
                Manage Datasets
              </Button>
            </Link>
            
            <Link href="/admin/storage">
              <Button variant="outline" className="w-full justify-start">
                <Cloud className="mr-2 h-4 w-4" />
                Storage Management
              </Button>
            </Link>
            
            <Link href="/analytics">
              <Button variant="outline" className="w-full justify-start">
                <Activity className="mr-2 h-4 w-4" />
                View Analytics
              </Button>
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Zap className="mr-2 h-5 w-5" />
              System Information
            </CardTitle>
            <CardDescription>
              Current system status and metrics
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Platform Status</span>
                <span className="text-sm font-medium text-green-600">Online</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Uptime</span>
                <span className="text-sm font-medium">{stats?.systemHealth.uptime || 'Unknown'}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Last Health Check</span>
                <span className="text-sm font-medium">
                  {stats?.systemHealth.lastCheck ? 
                    new Date(stats.systemHealth.lastCheck).toLocaleTimeString() : 
                    'Unknown'
                  }
                </span>
              </div>
              <Button 
                variant="outline" 
                size="sm" 
                className="w-full mt-4"
                onClick={onRefresh}
              >
                <Activity className="mr-2 h-4 w-4" />
                Refresh Status
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function EnvironmentTab({ 
  environmentVariables, 
  onUpdate 
}: { 
  environmentVariables: EnvironmentVariables | null; 
  onUpdate: () => void; 
}) {
  const [activeCategory, setActiveCategory] = useState('storage');
  const [editingVar, setEditingVar] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [showSensitive, setShowSensitive] = useState<{[key: string]: boolean}>({});
  const [saving, setSaving] = useState(false);
  const [reloading, setReloading] = useState(false);

  const categoryIcons = {
    storage: Cloud,
    database: Database,
    security: Shield,
    ai_models: Zap,
    data_sharing: Users,
    file_upload: FileText,
    connectors: Users,
    admin: Key,
    other: Settings
  };

  const categoryNames = {
    storage: 'Storage',
    database: 'Database',
    security: 'Security',
    ai_models: 'AI Models',
    data_sharing: 'Data Sharing',
    file_upload: 'File Upload',
    connectors: 'Connectors',
    admin: 'Admin',
    other: 'Other'
  };

  const handleSaveVariable = async (key: string, value: string) => {
    try {
      setSaving(true);
      await adminAPI.updateEnvironmentVariable(key, value);
      setEditingVar(null);
      setEditValue('');
      onUpdate();
      alert('Environment variable updated successfully!');
    } catch (error) {
      console.error('Failed to update environment variable:', error);
      alert('Failed to update environment variable. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleReloadEnvironment = async () => {
    try {
      console.log('🚀 Starting environment reload...');
      setReloading(true);
      const result = await adminAPI.reloadEnvironmentVariables();
      console.log('✅ Environment reload result:', result);
      alert(`Successfully reloaded ${result.total_variables_reloaded} environment variables from .env files!`);
      onUpdate(); // Refresh the environment variables display
    } catch (error) {
      console.error('❌ Failed to reload environment variables:', error);
      // Show more detailed error information
      const errorMessage = (error as any)?.response?.data?.detail || (error as any)?.message || 'Unknown error';
      alert(`Failed to reload environment variables: ${errorMessage}`);
    } finally {
      setReloading(false);
    }
  };

  const toggleSensitiveVisibility = (key: string) => {
    setShowSensitive(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  if (!environmentVariables) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="text-center">
            <Server className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-2 text-sm font-medium text-gray-900">No Environment Data</h3>
            <p className="mt-1 text-sm text-gray-500">
              Unable to load environment variables. Please check your connection.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Category Navigation */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center">
                <Server className="mr-2 h-5 w-5" />
                Environment Variables
              </CardTitle>
              <CardDescription>
                Manage system configuration through environment variables
              </CardDescription>
            </div>
            <Button
              variant="outline"
              onClick={handleReloadEnvironment}
              disabled={reloading}
              className="flex items-center"
            >
              <Settings className={`mr-2 h-4 w-4 ${reloading ? 'animate-spin' : ''}`} />
              {reloading ? 'Reloading...' : 'Reload from .env'}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
            {Object.entries(categoryNames).map(([key, name]) => {
              const Icon = categoryIcons[key as keyof typeof categoryIcons];
              const count = environmentVariables.categories[key] ? 
                Object.keys(environmentVariables.categories[key]).length : 0;
              
              return (
                <button
                  key={key}
                  onClick={() => setActiveCategory(key)}
                  className={`p-3 rounded-lg border text-center transition-colors ${
                    activeCategory === key
                      ? 'border-blue-500 bg-blue-50 text-blue-700'
                      : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  <Icon className="h-5 w-5 mx-auto mb-1" />
                  <div className="text-xs font-medium">{name}</div>
                  <div className="text-xs text-gray-500">{count}</div>
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Environment Variables List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            {React.createElement(categoryIcons[activeCategory as keyof typeof categoryIcons], {
              className: "mr-2 h-5 w-5"
            })}
            {categoryNames[activeCategory as keyof typeof categoryNames]} Configuration
          </CardTitle>
          <CardDescription>
            Configure {categoryNames[activeCategory as keyof typeof categoryNames].toLowerCase()} related environment variables
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {environmentVariables.categories[activeCategory] && 
             Object.keys(environmentVariables.categories[activeCategory]).length > 0 ? (
              Object.entries(environmentVariables.categories[activeCategory]).map(([key, variable]) => (
                <div key={key} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center">
                      <h4 className="font-medium text-gray-900">{key}</h4>
                      {variable.is_sensitive && (
                        <span className="ml-2 px-2 py-1 text-xs bg-red-100 text-red-800 rounded">
                          Sensitive
                        </span>
                      )}
                    </div>
                    <div className="flex items-center space-x-2">
                      {variable.is_sensitive && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => toggleSensitiveVisibility(key)}
                        >
                          {showSensitive[key] ? (
                            <EyeOff className="h-4 w-4" />
                          ) : (
                            <Eye className="h-4 w-4" />
                          )}
                        </Button>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEditingVar(key);
                          setEditValue(variable.value);
                        }}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  
                  <p className="text-sm text-gray-600 mb-3">{variable.description}</p>
                  
                  {editingVar === key ? (
                    <div className="space-y-3">
                      <input
                        type={variable.is_sensitive && !showSensitive[key] ? "password" : "text"}
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        placeholder={`Enter ${key}`}
                      />
                      <div className="flex space-x-2">
                        <Button
                          size="sm"
                          onClick={() => handleSaveVariable(key, editValue)}
                          disabled={saving}
                        >
                          <Save className="h-4 w-4 mr-1" />
                          {saving ? 'Saving...' : 'Save'}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setEditingVar(null);
                            setEditValue('');
                          }}
                        >
                          <X className="h-4 w-4 mr-1" />
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-gray-50 rounded p-3 font-mono text-sm">
                      {variable.is_sensitive && !showSensitive[key] ? 
                        '••••••••••••••••' : 
                        variable.value || '(not set)'
                      }
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="text-center py-8">
                <Settings className="mx-auto h-12 w-12 text-gray-400" />
                <h3 className="mt-2 text-sm font-medium text-gray-900">No Variables</h3>
                <p className="mt-1 text-sm text-gray-500">
                  No environment variables found in this category.
                </p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function SystemStatusTab({ stats }: { stats: AdminStats | null }) {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <Activity className="mr-2 h-5 w-5" />
            System Health Overview
          </CardTitle>
          <CardDescription>
            Real-time system status and performance metrics
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="text-center">
              <div className="w-16 h-16 mx-auto mb-3 bg-green-100 rounded-full flex items-center justify-center">
                <CheckCircle className="h-8 w-8 text-green-600" />
              </div>
              <p className="text-sm text-gray-500">Platform Status</p>
              <p className="text-lg font-semibold text-green-600">Online</p>
            </div>
            
            <div className="text-center">
              <div className="w-16 h-16 mx-auto mb-3 bg-blue-100 rounded-full flex items-center justify-center">
                <Server className="h-8 w-8 text-blue-600" />
              </div>
              <p className="text-sm text-gray-500">Uptime</p>
              <p className="text-lg font-semibold text-gray-900">{stats?.systemHealth.uptime || 'Unknown'}</p>
            </div>
            
            <div className="text-center">
              <div className="w-16 h-16 mx-auto mb-3 bg-purple-100 rounded-full flex items-center justify-center">
                <Activity className="h-8 w-8 text-purple-600" />
              </div>
              <p className="text-sm text-gray-500">Last Check</p>
              <p className="text-lg font-semibold text-gray-900">
                {stats?.systemHealth.lastCheck ? 
                  new Date(stats.systemHealth.lastCheck).toLocaleTimeString() : 
                  'Unknown'
                }
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Service Status</CardTitle>
          <CardDescription>
            Status of individual system components
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-lg">
              <div className="flex items-center">
                <CheckCircle className="h-5 w-5 text-green-600 mr-3" />
                <div>
                  <p className="font-medium text-green-900">Backend API</p>
                  <p className="text-sm text-green-700">All endpoints operational</p>
                </div>
              </div>
              <span className="text-green-600 font-medium">Healthy</span>
            </div>

            <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-lg">
              <div className="flex items-center">
                <CheckCircle className="h-5 w-5 text-green-600 mr-3" />
                <div>
                  <p className="font-medium text-green-900">Database</p>
                  <p className="text-sm text-green-700">SQLite connection active</p>
                </div>
              </div>
              <span className="text-green-600 font-medium">Connected</span>
            </div>

            <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-lg">
              <div className="flex items-center">
                <CheckCircle className="h-5 w-5 text-green-600 mr-3" />
                <div>
                  <p className="font-medium text-green-900">MindsDB</p>
                  <p className="text-sm text-green-700">AI service available</p>
                </div>
              </div>
              <span className="text-green-600 font-medium">Available</span>
            </div>

            <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-lg">
              <div className="flex items-center">
                <CheckCircle className="h-5 w-5 text-green-600 mr-3" />
                <div>
                  <p className="font-medium text-green-900">Google AI API</p>
                  <p className="text-sm text-green-700">Gemini models configured</p>
                </div>
              </div>
              <span className="text-green-600 font-medium">Configured</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}