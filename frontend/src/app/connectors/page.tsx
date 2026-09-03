'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {Database, Plus, TestTube, RefreshCw, Trash2, Globe, Copy, Shield, Zap, Link as LinkIcon} from 'lucide-react';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { dataConnectorsAPI } from '@/lib/api';
import SimplifiedConnectorForm from '@/components/connectors/SimplifiedConnectorForm';
import { parseConnectionUrl } from '@/utils/connectionParser';
import apiConfig from '@/config/api.config';
import Link from 'next/link';

interface DatabaseConnector {
  id: number;
  name: string;
  connector_type: string;
  description?: string;
  is_active: boolean;
  test_status: string;
  last_tested_at?: string;
  created_at: string;
  mindsdb_database_name?: string;
  organization_id: number;
  datasets?: any[];
  proxy_enabled?: boolean;
  proxy_url?: string;
  proxy_token?: string;
}

interface SimplifiedConnectorData {
  name: string;
  description: string;
  connector_type: string;
  connection_url: string;
}

export default function ConnectorsPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <ConnectorsContent />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function ConnectorsContent() {
  const router = useRouter();
  const [connectors, setConnectors] = useState<DatabaseConnector[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Modal states
  const [showCreateConnector, setShowCreateConnector] = useState(false);
  const [creating, setCreating] = useState(false);
  
  // Action states
  const [testing, setTesting] = useState<Record<number, boolean>>({});
  const [syncing, setSyncing] = useState<Record<number, boolean>>({});
  const [enablingProxy, setEnablingProxy] = useState<Record<number, boolean>>({});
  const [creatingDataset, setCreatingDataset] = useState<Record<number, boolean>>({});

  const showToast = (title: string, description: string, variant: 'default' | 'destructive' = 'default') => {
    // Simple alert for now - can be replaced with proper toast implementation
    if (variant === 'destructive') {
      alert(`Error: ${description}`);
    } else {
      alert(`${title}: ${description}`);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  useEffect(() => {
    fetchConnectors();
  }, []);

  const fetchConnectors = async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      const connectorsResponse = await dataConnectorsAPI.getConnectors({ include_datasets: true });
      setConnectors(connectorsResponse);
      
    } catch (error: any) {
      console.error('Failed to fetch connectors:', error);
      setError(error.response?.data?.detail || 'Failed to fetch connectors');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateConnector = async (data: SimplifiedConnectorData) => {
    setCreating(true);
    setError(null);

    try {
      // Validate the URL before sending to backend
      const parseResult = parseConnectionUrl(data.connection_url, data.connector_type);
      if (!parseResult.success) {
        throw new Error(parseResult.error);
      }

      await dataConnectorsAPI.createSimplifiedConnector(data);
      setShowCreateConnector(false);
      fetchConnectors();
      showToast("Success", "Database connector created successfully");
    } catch (error: any) {
      console.error('Failed to create connector:', error);
      setError(error.response?.data?.detail || error.message || 'Failed to create connector');
      throw error;
    } finally {
      setCreating(false);
    }
  };

  const handleTestConnection = async (connectorId: number) => {
    setTesting(prev => ({ ...prev, [connectorId]: true }));
    
    try {
      await dataConnectorsAPI.testConnector(connectorId);
      fetchConnectors(); // Refresh to get updated status
      showToast("Success", "Connection test completed successfully");
    } catch (error) {
      console.error('Test failed:', error);
      showToast("Error", "Connection test failed", "destructive");
    } finally {
      setTesting(prev => ({ ...prev, [connectorId]: false }));
    }
  };

  const handleSyncWithMindsDB = async (connectorId: number) => {
    setSyncing(prev => ({ ...prev, [connectorId]: true }));
    
    try {
      await dataConnectorsAPI.syncWithMindsDB(connectorId);
      fetchConnectors(); // Refresh to get updated status
      showToast("Success", "Sync with MindsDB completed successfully");
    } catch (error) {
      console.error('Sync failed:', error);
      showToast("Error", "Sync with MindsDB failed", "destructive");
    } finally {
      setSyncing(prev => ({ ...prev, [connectorId]: false }));
    }
  };

  const handleEnableProxy = async (connectorId: number) => {
    setEnablingProxy(prev => ({ ...prev, [connectorId]: true }));
    
    try {
      // Mock proxy enablement - replace with actual API call
      await new Promise(resolve => setTimeout(resolve, 1500));
      
      // For now, just update local state to show proxy is enabled
      setConnectors(connectors.map(connector => 
        connector.id === connectorId 
          ? { 
              ...connector, 
              proxy_enabled: true,
              proxy_url: `proxy://localhost:1010${connector.id}`,
              proxy_token: `px_${Math.random().toString(36).substr(2, 9)}`
            }
          : connector
      ));
      
      showToast("Success", "Proxy access enabled for this connector");
    } catch (error) {
      console.error('Failed to enable proxy:', error);
      showToast("Error", "Failed to enable proxy access", "destructive");
    } finally {
      setEnablingProxy(prev => ({ ...prev, [connectorId]: false }));
    }
  };

  const handleCreateDataset = async (connectorId: number) => {
    const connector = connectors.find(c => c.id === connectorId);
    if (!connector) return;
    
    // Prompt for dataset name and table/query
    const datasetName = prompt('Enter dataset name:');
    if (!datasetName) return;
    
    let tableOrQuery = '';
    if (connector.connector_type === 'mysql' || connector.connector_type === 'postgresql') {
      tableOrQuery = prompt('Enter table name or SQL query:') || 'SELECT * FROM your_table LIMIT 100';
    } else if (connector.connector_type === 'api') {
      tableOrQuery = prompt('Enter API endpoint (optional):') || '';
    }
    
    setCreatingDataset(prev => ({ ...prev, [connectorId]: true }));
    
    try {
      const result = await dataConnectorsAPI.createDatasetFromConnector(connectorId, {
        dataset_name: datasetName,
        description: `Dataset created from ${connector.name} connector`,
        table_or_endpoint: tableOrQuery,
        sharing_level: 'private'
      });
      
      showToast("Success", `Dataset "${datasetName}" created successfully`);
      fetchConnectors(); // Refresh to show updated dataset counts
      
      // Navigate to the new dataset
      router.push(`/datasets/${result.dataset_id}`);
    } catch (error: any) {
      console.error('Failed to create dataset:', error);
      showToast("Error", error.response?.data?.detail || 'Failed to create dataset', "destructive");
    } finally {
      setCreatingDataset(prev => ({ ...prev, [connectorId]: false }));
    }
  };

  const handleDeleteConnector = async (connectorId: number) => {
    if (!confirm('Are you sure you want to delete this connection?')) {
      return;
    }

    try {
      await dataConnectorsAPI.deleteConnector(connectorId);
      fetchConnectors();
      showToast("Success", "Connector deleted successfully");
    } catch (error) {
      console.error('Delete failed:', error);
      showToast("Error", "Failed to delete connector", "destructive");
    }
  };

  const copyProxyConnection = (connector: DatabaseConnector) => {
    if (!connector.proxy_url || !connector.proxy_token) return;
    
    const connectionString = apiConfig.helpers.getConnectionString(
      connector.connector_type,
      connector.name,
      connector.proxy_token
    );
    
    navigator.clipboard.writeText(connectionString);
    showToast("Success", "Proxy connection string copied to clipboard");
  };

  const getConnectorIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case 'mysql':
      case 'postgresql':
      case 'mongodb':
      case 'clickhouse':
        return <Database className="w-5 h-5" />;
      case 's3':
        return <Globe className="w-5 h-5" />;
      default:
        return <Shield className="w-5 h-5" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success': return 'text-green-600 bg-green-100';
      case 'failed': return 'text-red-600 bg-red-100';
      case 'pending': return 'text-yellow-600 bg-yellow-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 md:px-8">
          <div className="bg-red-50 border border-red-200 rounded-md p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.5 0L4.268 18.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">Error loading connectors</h3>
                <div className="mt-2 text-sm text-red-700">
                  <p>{error}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="py-6">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 md:px-8">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center">
                <Database className="h-6 w-6 mr-2 text-indigo-600" />
                Database Connectors
              </h1>
              <p className="text-gray-600 mt-1 text-sm">
                Manage database connections with secure proxy access
              </p>
            </div>
            <div className="flex space-x-3">
              <Link
                href="/datasets/sharing"
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
              >
                ← Dataset Sharing
              </Link>
              <button
                onClick={() => setShowCreateConnector(true)}
                className="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
              >
                <Plus className="w-4 h-4 mr-2" />
                Add Connector
              </button>
            </div>
          </div>
        </div>

        {/* Stats Overview */}
        <div className="bg-white rounded-lg shadow p-4 mb-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="flex items-center justify-center mb-1">
                <Database className="h-5 w-5 text-indigo-600 mr-1" />
                <span className="text-sm font-medium text-gray-500">Total</span>
              </div>
              <div className="text-xl font-bold text-gray-900">{connectors.length}</div>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center mb-1">
                <Shield className="h-5 w-5 text-green-600 mr-1" />
                <span className="text-sm font-medium text-gray-500">Active</span>
              </div>
              <div className="text-xl font-bold text-gray-900">
                {connectors.filter(c => c.test_status === 'success').length}
              </div>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center mb-1">
                <LinkIcon className="h-5 w-5 text-blue-600 mr-1" />
                <span className="text-sm font-medium text-gray-500">Proxy Enabled</span>
              </div>
              <div className="text-xl font-bold text-gray-900">
                {connectors.filter(c => c.proxy_enabled).length}
              </div>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center mb-1">
                <Globe className="h-5 w-5 text-purple-600 mr-1" />
                <span className="text-sm font-medium text-gray-500">Datasets</span>
              </div>
              <div className="text-xl font-bold text-gray-900">
                {connectors.reduce((total, c) => total + (c.datasets?.length || 0), 0)}
              </div>
            </div>
          </div>
        </div>

        {/* Connectors List */}
        {connectors.length === 0 ? (
          <div className="bg-white rounded-lg p-12 text-center">
            <Database className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No database connectors yet</h3>
            <p className="text-gray-600 mb-6">
              Get started by creating your first database connection with proxy access
            </p>
            <button
              onClick={() => setShowCreateConnector(true)}
              className="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Your First Connector
            </button>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow divide-y divide-gray-200">
            {connectors.map((connector) => (
              <div key={connector.id} className="p-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-4">
                    <div className="flex-shrink-0 text-indigo-600">
                      {getConnectorIcon(connector.connector_type)}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center space-x-3">
                        <h3 className="text-lg font-medium text-gray-900">
                          {connector.name}
                        </h3>
                        {connector.proxy_enabled && (
                          <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                            <LinkIcon className="w-3 h-3 mr-1" />
                            Proxy Enabled
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-600 capitalize">
                        {connector.connector_type} • {connector.description || 'No description'}
                      </p>
                      <div className="flex items-center space-x-4 mt-2">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(connector.test_status)}`}>
                          {connector.test_status}
                        </span>
                        {connector.datasets && connector.datasets.length > 0 && (
                          <span className="text-xs text-gray-500">
                            {connector.datasets.length} dataset{connector.datasets.length !== 1 ? 's' : ''}
                          </span>
                        )}
                        <span className="text-xs text-gray-500">
                          Created {formatDate(connector.created_at)}
                        </span>
                      </div>
                      
                      {/* Proxy Connection Details */}
                      {connector.proxy_enabled && connector.proxy_url && (
                        <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-md">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium text-blue-900">Proxy Connection</span>
                            <button
                              onClick={() => copyProxyConnection(connector)}
                              className="text-blue-600 hover:text-blue-800"
                              title="Copy connection string"
                            >
                              <Copy className="h-4 w-4" />
                            </button>
                          </div>
                          <p className="text-xs text-blue-700">
                            Connect using {connector.connector_type} clients through secure proxy
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                  
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => handleCreateDataset(connector.id)}
                      disabled={creatingDataset[connector.id] || connector.test_status !== 'success'}
                      className={`inline-flex items-center px-3 py-2 border rounded-md text-sm font-medium disabled:opacity-50 ${
                        connector.test_status === 'success' 
                          ? 'border-green-300 text-green-700 bg-green-50 hover:bg-green-100'
                          : 'border-gray-300 text-gray-500 bg-gray-50'
                      }`}
                      title={connector.test_status !== 'success' ? 'Test connector first to create datasets' : ''}
                    >
                      {creatingDataset[connector.id] ? (
                        <RefreshCw className="w-4 h-4 animate-spin mr-1" />
                      ) : (
                        <Plus className="w-4 h-4 mr-1" />
                      )}
                      Create Dataset
                    </button>
                    
                    {connector.test_status === 'success' && !connector.proxy_enabled && (
                      <button
                        onClick={() => handleEnableProxy(connector.id)}
                        disabled={enablingProxy[connector.id]}
                        className="inline-flex items-center px-3 py-2 border border-blue-300 rounded-md text-sm font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 disabled:opacity-50"
                      >
                        {enablingProxy[connector.id] ? (
                          <RefreshCw className="w-4 h-4 animate-spin mr-1" />
                        ) : (
                          <LinkIcon className="w-4 h-4 mr-1" />
                        )}
                        Enable Proxy
                      </button>
                    )}
                    
                    <button
                      onClick={() => handleSyncWithMindsDB(connector.id)}
                      disabled={syncing[connector.id]}
                      className="inline-flex items-center px-3 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                    >
                      {syncing[connector.id] ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <Zap className="w-4 h-4" />
                      )}
                    </button>
                    
                    <button
                      onClick={() => handleTestConnection(connector.id)}
                      disabled={testing[connector.id]}
                      className="inline-flex items-center px-3 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                    >
                      {testing[connector.id] ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <TestTube className="w-4 h-4" />
                      )}
                    </button>
                    
                    <button
                      onClick={() => handleDeleteConnector(connector.id)}
                      className="inline-flex items-center px-3 py-2 border border-red-300 rounded-md text-sm font-medium text-red-700 bg-red-50 hover:bg-red-100"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Create Connector Modal */}
        {showCreateConnector && (
          <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50 flex items-center justify-center">
            <div className="relative mx-auto p-5 border w-11/12 md:w-3/4 lg:w-1/2 shadow-lg rounded-md bg-white max-h-[80vh] overflow-y-auto">
              <SimplifiedConnectorForm
                onSubmit={handleCreateConnector}
                onCancel={() => setShowCreateConnector(false)}
                isSubmitting={creating}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}