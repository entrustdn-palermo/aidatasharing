'use client';

import { useState, useEffect } from 'react';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { useAuth } from '@/components/auth/AuthProvider';
import { datasetsAPI } from '@/lib/api';
import {BarChart3, Users, Database, Activity, Calendar, Download, RefreshCw, HardDrive, CheckCircle, AlertTriangle, } from 'lucide-react';

interface AnalyticsData {
  organization: {
    name: string;
    totalUsers: number;
    totalDatasets: number;
    storageUsed: number;
    storageLimit: number;
  };
  usage: {
    totalApiCalls: number;
    averageResponseTime: number;
    uptime: number;
  };
  datasetUsage: Array<{
    id: number;
    name: string;
    accessCount: number;
    lastAccessed: string;
    sharingLevel: string;
    size: number;
  }>;
  trends: {
    datasetUploads: Array<{ date: string; count: number }>;
    userActivity: Array<{ date: string; active_users: number }>;
  };
}

export default function AnalyticsPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <AnalyticsPageContent />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function AnalyticsPageContent() {
  const { user } = useAuth();
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDateRange, setSelectedDateRange] = useState('30');
  const [activeTab, setActiveTab] = useState<'overview' | 'datasets' | 'users'>('overview');

  useEffect(() => {
    fetchAnalytics();
  }, [selectedDateRange]);

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Fetch datasets to calculate usage metrics
      const datasets = await datasetsAPI.getDatasets();
      
      // Mock analytics data based on real datasets
      const analyticsData: AnalyticsData = {
        organization: {
          name: user?.organization_name || 'Your Organization',
          totalUsers: 5, // Mock data
          totalDatasets: datasets?.length || 0,
          storageUsed: datasets?.reduce((total: number, dataset: any) => total + (dataset.size_bytes || 0), 0) / (1024 * 1024 * 1024) || 0, // Convert to GB
          storageLimit: 100 // Mock 100GB limit
        },
        usage: {
          totalApiCalls: Math.floor(Math.random() * 10000) + 5000,
          averageResponseTime: Math.floor(Math.random() * 200) + 50,
          uptime: 99.9
        },
        datasetUsage: (datasets || []).map((dataset: any) => ({
          id: dataset.id,
          name: dataset.name,
          accessCount: Math.floor(Math.random() * 100) + 10,
          lastAccessed: dataset.last_accessed || dataset.updated_at,
          sharingLevel: dataset.sharing_level,
          size: dataset.size_bytes || 0
        })),
        trends: {
          datasetUploads: generateMockTrendData(),
          userActivity: generateMockUserActivity()
        }
      };
      
      setAnalytics(analyticsData);
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  const generateMockTrendData = () => {
    const data = [];
    const days = parseInt(selectedDateRange);
    for (let i = days; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      data.push({
        date: date.toISOString().split('T')[0],
        count: Math.floor(Math.random() * 5) + 1
      });
    }
    return data;
  };

  const generateMockUserActivity = () => {
    const data = [];
    const days = parseInt(selectedDateRange);
    for (let i = days; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      data.push({
        date: date.toISOString().split('T')[0],
        active_users: Math.floor(Math.random() * 8) + 2
      });
    }
    return data;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center space-y-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600"></div>
          <p className="text-gray-600">Loading analytics...</p>
        </div>
      </div>
    );
  }

  if (error || !analytics) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <div className="flex items-center">
            <AlertTriangle className="w-6 h-6 text-red-600 mr-3" />
            <h2 className="text-lg font-semibold text-red-800">Error Loading Analytics</h2>
          </div>
          <p className="text-red-700 mt-2">{error || 'Analytics data not available'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="py-6">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 md:px-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Analytics Dashboard</h1>
            <p className="text-gray-600 mt-2">Organization insights and performance metrics for {analytics.organization.name}</p>
          </div>
          
          <div className="flex items-center space-x-4">
            {/* Date Range Selector */}
            <div className="relative">
              <select
                value={selectedDateRange}
                onChange={(e) => setSelectedDateRange(e.target.value)}
                className="appearance-none bg-white border border-gray-300 rounded-lg px-4 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="7">Last 7 Days</option>
                <option value="30">Last 30 Days</option>
                <option value="90">Last 3 Months</option>
              </select>
              <Calendar className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
            
            <button
              onClick={fetchAnalytics}
              className="flex items-center px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Refresh
            </button>
            
            <button className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              <Download className="w-4 h-4 mr-2" />
              Export Report
            </button>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-white p-6 rounded-lg shadow">
            <div className="flex items-center">
              <div className="p-3 bg-blue-100 rounded-lg">
                <Users className="w-6 h-6 text-blue-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Active Users</p>
                <p className="text-2xl font-bold text-gray-900">{analytics.organization.totalUsers}</p>
                <p className="text-sm text-green-600">+12% from last month</p>
              </div>
            </div>
          </div>
          
          <div className="bg-white p-6 rounded-lg shadow">
            <div className="flex items-center">
              <div className="p-3 bg-green-100 rounded-lg">
                <Database className="w-6 h-6 text-green-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Total Datasets</p>
                <p className="text-2xl font-bold text-gray-900">{analytics.organization.totalDatasets}</p>
                <p className="text-sm text-green-600">+8% from last month</p>
              </div>
            </div>
          </div>
          
          <div className="bg-white p-6 rounded-lg shadow">
            <div className="flex items-center">
              <div className="p-3 bg-orange-100 rounded-lg">
                <HardDrive className="w-6 h-6 text-orange-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Storage Used</p>
                <p className="text-2xl font-bold text-gray-900">{analytics.organization.storageUsed.toFixed(1)}GB</p>
                <p className="text-sm text-gray-600">of {analytics.organization.storageLimit}GB</p>
              </div>
            </div>
          </div>

          <div className="bg-white p-6 rounded-lg shadow">
            <div className="flex items-center">
              <div className="p-3 bg-purple-100 rounded-lg">
                <Activity className="w-6 h-6 text-purple-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">API Calls</p>
                <p className="text-2xl font-bold text-gray-900">{analytics.usage.totalApiCalls.toLocaleString()}</p>
                <p className="text-sm text-green-600">+15% from last month</p>
              </div>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="bg-white rounded-lg shadow mb-8">
          <div className="border-b border-gray-200">
            <nav className="flex space-x-8 px-6">
              {[
                { id: 'overview', label: 'Overview', icon: BarChart3 },
                { id: 'datasets', label: 'Dataset Usage', icon: Database },
                { id: 'users', label: 'User Activity', icon: Users }
              ].map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as any)}
                    className={`flex items-center py-4 px-2 border-b-2 font-medium text-sm ${
                      activeTab === tab.id
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }`}
                  >
                    <Icon className="w-4 h-4 mr-2" />
                    {tab.label}
                  </button>
                );
              })}
            </nav>
          </div>

          {/* Tab Content */}
          <div className="p-6">
            {activeTab === 'overview' && (
              <div className="space-y-6">
                {/* System Health */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  <div className="bg-gradient-to-r from-green-50 to-green-100 p-6 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-green-900">System Uptime</h3>
                        <p className="text-3xl font-bold text-green-600">{analytics.usage.uptime}%</p>
                        <p className="text-sm text-green-700">Last 30 days</p>
                      </div>
                      <CheckCircle className="w-12 h-12 text-green-600" />
                    </div>
                  </div>
                  
                  <div className="bg-gradient-to-r from-blue-50 to-blue-100 p-6 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-blue-900">Avg Response Time</h3>
                        <p className="text-3xl font-bold text-blue-600">{analytics.usage.averageResponseTime}ms</p>
                        <p className="text-sm text-blue-700">API responses</p>
                      </div>
                      <Activity className="w-12 h-12 text-blue-600" />
                    </div>
                  </div>
                  
                  <div className="bg-gradient-to-r from-orange-50 to-orange-100 p-6 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-orange-900">Storage Used</h3>
                        <p className="text-3xl font-bold text-orange-600">{analytics.organization.storageUsed.toFixed(1)}GB</p>
                        <p className="text-sm text-orange-700">of {analytics.organization.storageLimit}GB</p>
                      </div>
                      <HardDrive className="w-12 h-12 text-orange-600" />
                    </div>
                  </div>
                </div>

                {/* Activity Trends */}
                <div className="bg-white border border-gray-200 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">Dataset Upload Trends</h3>
                  <div className="space-y-3">
                    {analytics.trends.datasetUploads.slice(-7).map((item, index) => (
                      <div key={index} className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">{new Date(item.date).toLocaleDateString()}</span>
                        <div className="flex items-center">
                          <div className="w-32 bg-gray-200 rounded-full h-2 mr-3">
                            <div 
                              className="bg-blue-600 h-2 rounded-full" 
                              style={{ width: `${Math.min((item.count / 5) * 100, 100)}%` }}
                            ></div>
                          </div>
                          <span className="text-sm font-medium w-8">{item.count}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'datasets' && (
              <div className="space-y-6">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-semibold text-gray-900">Dataset Usage Analytics</h3>
                </div>
                
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Dataset Name
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Access Count
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Sharing Level
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Size
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Last Accessed
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {analytics.datasetUsage.map((dataset) => (
                        <tr key={dataset.id}>
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                            {dataset.name}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            <div className="flex items-center">
                              <div className="w-16 bg-gray-200 rounded-full h-2 mr-3">
                                <div 
                                  className="bg-blue-600 h-2 rounded-full" 
                                  style={{ width: `${Math.min((dataset.accessCount / 100) * 100, 100)}%` }}
                                ></div>
                              </div>
                              {dataset.accessCount}
                            </div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                              dataset.sharingLevel === 'public' ? 'bg-green-100 text-green-800' :
                              dataset.sharingLevel === 'organization' ? 'bg-blue-100 text-blue-800' :
                              'bg-gray-100 text-gray-800'
                            }`}>
                              {dataset.sharingLevel}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {formatFileSize(dataset.size)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {new Date(dataset.lastAccessed).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {activeTab === 'users' && (
              <div className="space-y-6">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-semibold text-gray-900">User Activity Overview</h3>
                </div>
                
                <div className="bg-white border border-gray-200 rounded-lg p-6">
                  <h4 className="text-md font-semibold text-gray-900 mb-4">Daily Active Users</h4>
                  <div className="space-y-3">
                    {analytics.trends.userActivity.slice(-7).map((item, index) => (
                      <div key={index} className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">{new Date(item.date).toLocaleDateString()}</span>
                        <div className="flex items-center">
                          <div className="w-32 bg-gray-200 rounded-full h-2 mr-3">
                            <div 
                              className="bg-purple-600 h-2 rounded-full" 
                              style={{ width: `${(item.active_users / 10) * 100}%` }}
                            ></div>
                          </div>
                          <span className="text-sm font-medium w-8">{item.active_users}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}