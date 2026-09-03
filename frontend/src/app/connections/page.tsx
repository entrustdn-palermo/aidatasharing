'use client';

import { useState, useEffect } from 'react';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { dataConnectorsAPI } from '@/lib/api';
import {Database, Plus, TestTube, CheckCircle, XCircle, Clock, Settings, Trash2, Wifi, WifiOff, RefreshCw, Eye, EyeOff, Sparkles} from 'lucide-react';
import SimplifiedConnectorForm from '@/components/connectors/SimplifiedConnectorForm';
import { parseConnectionUrl } from '@/utils/connectionParser';

interface DatabaseConnector {
  id: number;
  name: string;
  connector_type: string;
  description?: string;
  is_active: boolean;
  test_status: 'untested' | 'success' | 'failed';
  last_tested_at?: string;
  created_at: string;
  mindsdb_database_name?: string;
  organization_id: number;
  datasets?: Array<{
    id: number;
    name: string;
    type: string;
    sharing_level: string;
    public_share_enabled?: boolean;
  }>;
}

interface ConnectorForm {
  name: string;
  connector_type: string;
  description: string;
  connection_config: Record<string, any>;
  credentials: Record<string, any>;
}

const initialForm: ConnectorForm = {
  name: '',
  connector_type: 'mysql',
  description: '',
  connection_config: {},
  credentials: {}
};

const CONNECTOR_TYPES = [
  { value: 'mysql', label: 'MySQL', icon: '🐬' },
  { value: 'postgresql', label: 'PostgreSQL', icon: '🐘' },
  { value: 's3', label: 'Amazon S3', icon: '☁️' },
  { value: 'mongodb', label: 'MongoDB', icon: '🍃' },
  { value: 'clickhouse', label: 'ClickHouse', icon: '⚡' },
  { value: 'api', label: 'REST API', icon: '🔗' },
];

const CONNECTOR_FIELDS = {
  mysql: {
    connection_config: [
      { name: 'host', label: 'Host', type: 'text', placeholder: 'localhost', required: true },
      { name: 'port', label: 'Port', type: 'number', placeholder: '3306', required: true },
      { name: 'database', label: 'Database Name', type: 'text', placeholder: 'mydb', required: true },
    ],
    credentials: [
      { name: 'user', label: 'Username', type: 'text', placeholder: 'root', required: true },
      { name: 'password', label: 'Password', type: 'password', placeholder: '••••••••', required: true },
    ]
  },
  postgresql: {
    connection_config: [
      { name: 'host', label: 'Host', type: 'text', placeholder: 'localhost', required: true },
      { name: 'port', label: 'Port', type: 'number', placeholder: '5432', required: true },
      { name: 'database', label: 'Database Name', type: 'text', placeholder: 'postgres', required: true },
    ],
    credentials: [
      { name: 'user', label: 'Username', type: 'text', placeholder: 'postgres', required: true },
      { name: 'password', label: 'Password', type: 'password', placeholder: '••••••••', required: true },
    ]
  },
  s3: {
    connection_config: [
      { name: 'bucket_name', label: 'Bucket Name', type: 'text', placeholder: 'my-bucket', required: true },
      { name: 'region', label: 'Region', type: 'text', placeholder: 'us-east-1', required: true },
    ],
    credentials: [
      { name: 'aws_access_key_id', label: 'Access Key ID', type: 'text', placeholder: 'AKIA...', required: true },
      { name: 'aws_secret_access_key', label: 'Secret Access Key', type: 'password', placeholder: '••••••••', required: true },
    ]
  },
  mongodb: {
    connection_config: [
      { name: 'host', label: 'Host', type: 'text', placeholder: 'localhost', required: true },
      { name: 'port', label: 'Port', type: 'number', placeholder: '27017', required: true },
      { name: 'database', label: 'Database Name', type: 'text', placeholder: 'mydb', required: true },
    ],
    credentials: [
      { name: 'username', label: 'Username', type: 'text', placeholder: 'admin', required: false },
      { name: 'password', label: 'Password', type: 'password', placeholder: '••••••••', required: false },
    ]
  },
  clickhouse: {
    connection_config: [
      { name: 'host', label: 'Host', type: 'text', placeholder: 'localhost', required: true },
      { name: 'port', label: 'Port', type: 'number', placeholder: '9000', required: true },
      { name: 'database', label: 'Database Name', type: 'text', placeholder: 'default', required: true },
    ],
    credentials: [
      { name: 'user', label: 'Username', type: 'text', placeholder: 'default', required: true },
      { name: 'password', label: 'Password', type: 'password', placeholder: '••••••••', required: false },
    ]
  },
  api: {
    connection_config: [
      { name: 'base_url', label: 'Base URL', type: 'url', placeholder: 'https://api.example.com', required: true },
      { name: 'endpoint', label: 'Endpoint Path', type: 'text', placeholder: '/data', required: false },
      { name: 'method', label: 'HTTP Method', type: 'select', options: ['GET', 'POST'], placeholder: 'Select method', required: true },
    ],
    credentials: [
      { name: 'api_key', label: 'API Key', type: 'password', placeholder: '••••••••', required: false },
      { name: 'auth_header', label: 'Auth Header Name', type: 'text', placeholder: 'Authorization', required: false },
    ]
  }
};

export default function ConnectionsPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <ConnectionsPageContent />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function ConnectionsPageContent() {
  const [connectors, setConnectors] = useState<DatabaseConnector[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [form, setForm] = useState<ConnectorForm>(initialForm);
  const [creating, setCreating] = useState(false);
  const [testing, setTesting] = useState<Record<number, boolean>>({});
  const [syncing, setSyncing] = useState<Record<number, boolean>>({});
  const [showCredentials, setShowCredentials] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [useSimplifiedMode, setUseSimplifiedMode] = useState(true);

  useEffect(() => {
    fetchConnectors();
  }, []);

  const fetchConnectors = async () => {
    try {
      const response = await dataConnectorsAPI.getConnectors({ include_datasets: true });
      setConnectors(response);
    } catch (error) {
      console.error('Failed to fetch connectors:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateConnector = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setErrors({});

    try {
      await dataConnectorsAPI.createConnector(form);
      setShowCreateModal(false);
      setForm(initialForm);
      fetchConnectors();
    } catch (error: any) {
      setErrors({ general: error.response?.data?.detail || 'Failed to create connector' });
    } finally {
      setCreating(false);
    }
  };

  const handleCreateSimplifiedConnector = async (data: {
    name: string;
    description: string;
    connector_type: string;
    connection_url: string;
  }) => {
    setCreating(true);
    setErrors({});

    try {
      // Validate the URL before sending to backend
      const parseResult = parseConnectionUrl(data.connection_url, data.connector_type);
      if (!parseResult.success) {
        throw new Error(parseResult.error);
      }

      await dataConnectorsAPI.createSimplifiedConnector(data);
      setShowCreateModal(false);
      fetchConnectors();
    } catch (error: any) {
      setErrors({ general: error.response?.data?.detail || error.message || 'Failed to create connector' });
      throw error; // Re-throw to let the form handle it
    } finally {
      setCreating(false);
    }
  };

  const handleTestConnection = async (connectorId: number) => {
    setTesting(prev => ({ ...prev, [connectorId]: true }));
    
    try {
      await dataConnectorsAPI.testConnector(connectorId);
      fetchConnectors(); // Refresh to get updated status
    } catch (error) {
      console.error('Test failed:', error);
    } finally {
      setTesting(prev => ({ ...prev, [connectorId]: false }));
    }
  };

  const handleSyncWithMindsDB = async (connectorId: number) => {
    setSyncing(prev => ({ ...prev, [connectorId]: true }));
    
    try {
      await dataConnectorsAPI.syncWithMindsDB(connectorId);
      // Show success message or refresh data
    } catch (error) {
      console.error('Sync failed:', error);
    } finally {
      setSyncing(prev => ({ ...prev, [connectorId]: false }));
    }
  };

  const handleDeleteConnector = async (connectorId: number) => {
    if (!confirm('Are you sure you want to delete this connector?')) return;
    
    try {
      await dataConnectorsAPI.deleteConnector(connectorId);
      fetchConnectors();
    } catch (error) {
      console.error('Delete failed:', error);
    }
  };

  const handleCreateDatasetFromConnector = async (connectorId: number) => {
    const connector = connectors.find(c => c.id === connectorId);
    if (!connector) return;

    const datasetName = prompt(`Create dataset from ${connector.name}:`, `${connector.name} Dataset`);
    if (!datasetName) return;

    try {
      const result = await dataConnectorsAPI.createDatasetFromConnector(connectorId, {
        dataset_name: datasetName,
        description: `Dataset created from ${connector.name} API connector`,
        sharing_level: 'private'
      });
      
      alert(`Dataset "${datasetName}" created successfully! You can now chat with this data.`);
      fetchConnectors(); // Refresh to show new dataset
    } catch (error: any) {
      console.error('Dataset creation failed:', error);
      alert(`Failed to create dataset: ${error.response?.data?.detail || error.message}`);
    }
  };

  const handleFormFieldChange = (section: 'connection_config' | 'credentials', field: string, value: any) => {
    setForm(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [field]: value
      }
    }));
  };

  const handleConnectorTypeChange = (newType: string) => {
    setForm(prev => ({
      ...prev,
      connector_type: newType,
      connection_config: {},
      credentials: {}
    }));
  };

  const renderFormField = (field: any, section: 'connection_config' | 'credentials', value: any) => {
    const fieldKey = `${section}.${field.name}`;
    
    if (field.type === 'select') {
      return (
        <select
          value={value || (field.required && field.options?.length ? field.options[0] : '')}
          onChange={(e) => handleFormFieldChange(section, field.name, e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          required={field.required}
        >
          {!field.required && <option value="">{field.placeholder}</option>}
          {field.options?.map((option: string) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      );
    }

    if (field.type === 'password') {
      return (
        <div className="relative">
          <input
            type={showCredentials[fieldKey] ? 'text' : 'password'}
            value={value || ''}
            onChange={(e) => handleFormFieldChange(section, field.name, e.target.value)}
            className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder={field.placeholder}
            required={field.required}
          />
          <button
            type="button"
            onClick={() => setShowCredentials(prev => ({ ...prev, [fieldKey]: !prev[fieldKey] }))}
            className="absolute inset-y-0 right-0 pr-3 flex items-center"
          >
            {showCredentials[fieldKey] ? (
              <EyeOff className="w-4 h-4 text-gray-400" />
            ) : (
              <Eye className="w-4 h-4 text-gray-400" />
            )}
          </button>
        </div>
      );
    }

    return (
      <input
        type={field.type}
        value={value || ''}
        onChange={(e) => handleFormFieldChange(section, field.name, field.type === 'number' ? parseInt(e.target.value) || '' : e.target.value)}
        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder={field.placeholder}
        required={field.required}
      />
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center space-y-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600"></div>
          <p className="text-gray-600">Loading connections...</p>
        </div>
      </div>
    );
  }

  const currentFields = CONNECTOR_FIELDS[form.connector_type as keyof typeof CONNECTOR_FIELDS];

  return (
    <div className="py-6">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 md:px-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Data Connections</h1>
            <p className="text-gray-600 mt-2">Manage your database connections and data sources</p>
          </div>
          <div className="flex items-center space-x-4">
            {/* Mode Toggle */}
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setUseSimplifiedMode(true)}
                className={`inline-flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  useSimplifiedMode
                    ? 'bg-blue-100 text-blue-700 border border-blue-200'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <Sparkles className="w-4 h-4 mr-1" />
                Simple
              </button>
              <button
                onClick={() => setUseSimplifiedMode(false)}
                className={`inline-flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  !useSimplifiedMode
                    ? 'bg-gray-100 text-gray-700 border border-gray-200'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <Settings className="w-4 h-4 mr-1" />
                Advanced
              </button>
            </div>
            
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Connection
            </button>
          </div>
        </div>

        {/* Recent Connectors Summary */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white p-6 rounded-lg shadow">
            <div className="flex items-center">
              <div className="p-3 bg-blue-100 rounded-lg">
                <Database className="w-6 h-6 text-blue-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Total Connections</p>
                <p className="text-2xl font-bold text-gray-900">{connectors.length}</p>
              </div>
            </div>
          </div>
          
          <div className="bg-white p-6 rounded-lg shadow">
            <div className="flex items-center">
              <div className="p-3 bg-green-100 rounded-lg">
                <CheckCircle className="w-6 h-6 text-green-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Active Connections</p>
                <p className="text-2xl font-bold text-gray-900">{connectors.filter(c => c.is_active).length}</p>
              </div>
            </div>
          </div>

          <div className="bg-white p-6 rounded-lg shadow">
            <div className="flex items-center">
              <div className="p-3 bg-orange-100 rounded-lg">
                <Wifi className="w-6 h-6 text-orange-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Recent Activity</p>
                <p className="text-2xl font-bold text-gray-900">{connectors.filter(c => c.last_tested_at).length}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Connectors List */}
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Your Connections</h2>
          </div>
          
          {connectors.length === 0 ? (
            <div className="p-12 text-center">
              <Database className="w-16 h-16 text-gray-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900 mb-2">No connections yet</h3>
              <p className="text-gray-600 mb-4">
                Connect your databases and data sources to start sharing and analyzing data.
              </p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                <Plus className="w-4 h-4 mr-2" />
                Create Your First Connection
              </button>
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {connectors.map((connector) => (
                <div key={connector.id} className="p-6">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start space-x-4">
                      <div className="p-3 bg-blue-100 rounded-lg">
                        <Database className="w-6 h-6 text-blue-600" />
                      </div>
                      
                      <div className="flex-1">
                        <div className="flex items-center space-x-2">
                          <h3 className="text-lg font-semibold text-gray-900">{connector.name}</h3>
                          <span className="text-sm text-gray-500">
                            {CONNECTOR_TYPES.find(t => t.value === connector.connector_type)?.icon}
                            {CONNECTOR_TYPES.find(t => t.value === connector.connector_type)?.label}
                          </span>
                        </div>
                        
                        {connector.description && (
                          <p className="text-gray-600 mt-1">{connector.description}</p>
                        )}
                        
                        <div className="flex items-center space-x-4 mt-3">
                          <div className="flex items-center">
                            {connector.is_active ? (
                              <Wifi className="w-4 h-4 text-green-500 mr-1" />
                            ) : (
                              <WifiOff className="w-4 h-4 text-red-500 mr-1" />
                            )}
                            <span className={`text-sm ${connector.is_active ? 'text-green-600' : 'text-red-600'}`}>
                              {connector.is_active ? 'Active' : 'Inactive'}
                            </span>
                          </div>
                          
                          <div className="flex items-center">
                            {connector.test_status === 'success' && <CheckCircle className="w-4 h-4 text-green-500 mr-1" />}
                            {connector.test_status === 'failed' && <XCircle className="w-4 h-4 text-red-500 mr-1" />}
                            {connector.test_status === 'untested' && <Clock className="w-4 h-4 text-gray-400 mr-1" />}
                            <span className={`text-sm ${
                              connector.test_status === 'success' ? 'text-green-600' :
                              connector.test_status === 'failed' ? 'text-red-600' : 'text-gray-600'
                            }`}>
                              {connector.test_status === 'success' ? 'Test Passed' :
                               connector.test_status === 'failed' ? 'Test Failed' : 'Not Tested'}
                            </span>
                          </div>
                          
                          <span className="text-sm text-gray-500">
                            Created {new Date(connector.created_at).toLocaleDateString()}
                          </span>
                        </div>

                        {/* Datasets from this connector */}
                        {connector.datasets && connector.datasets.length > 0 && (
                          <div className="mt-4">
                            <h4 className="text-sm font-medium text-gray-700 mb-2">
                              Datasets ({connector.datasets.length})
                            </h4>
                            <div className="flex flex-wrap gap-2">
                              {connector.datasets.map((dataset) => (
                                <span
                                  key={dataset.id}
                                  className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                >
                                  {dataset.name}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                    
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handleTestConnection(connector.id)}
                        disabled={testing[connector.id]}
                        className="inline-flex items-center px-3 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                      >
                        {testing[connector.id] ? (
                          <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                        ) : (
                          <TestTube className="w-4 h-4 mr-1" />
                        )}
                        Test
                      </button>
                      
                      {connector.connector_type === 'api' && (
                        <button
                          onClick={() => handleCreateDatasetFromConnector(connector.id)}
                          className="inline-flex items-center px-3 py-2 border border-blue-300 rounded-md text-sm font-medium text-blue-700 bg-blue-50 hover:bg-blue-100"
                        >
                          <Plus className="w-4 h-4 mr-1" />
                          Create Dataset
                        </button>
                      )}
                      
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
        </div>

        {/* Create Modal */}
        {showCreateModal && (
          <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50 flex items-center justify-center">
            <div className="relative mx-auto p-5 border w-11/12 md:w-3/4 lg:w-2/3 shadow-lg rounded-md bg-white max-h-[80vh] overflow-y-auto">
              {useSimplifiedMode ? (
                <SimplifiedConnectorForm
                  onSubmit={handleCreateSimplifiedConnector}
                  onCancel={() => setShowCreateModal(false)}
                  isSubmitting={creating}
                />
              ) : (
                <>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-gray-900">Create New Connection</h3>
                    <button
                      onClick={() => setShowCreateModal(false)}
                      className="text-gray-400 hover:text-gray-600"
                    >
                      <span className="sr-only">Close</span>
                      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                  
                  <form onSubmit={handleCreateConnector} className="space-y-6">
                    {errors.general && (
                      <div className="bg-red-50 border border-red-200 rounded-md p-4">
                        <p className="text-red-600 text-sm">{errors.general}</p>
                      </div>
                    )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Connection Name
                    </label>
                    <input
                      type="text"
                      value={form.name}
                      onChange={(e) => setForm(prev => ({ ...prev, name: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="My Database Connection"
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Connection Type
                    </label>
                    <select
                      value={form.connector_type}
                      onChange={(e) => handleConnectorTypeChange(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      {CONNECTOR_TYPES.map(type => (
                        <option key={type.value} value={type.value}>
                          {type.icon} {type.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Description
                  </label>
                  <textarea
                    value={form.description}
                    onChange={(e) => setForm(prev => ({ ...prev, description: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    rows={3}
                    placeholder="Description of this connection..."
                  />
                </div>

                {/* Connection Configuration Fields */}
                {currentFields && (
                  <>
                    <div>
                      <h4 className="text-md font-medium text-gray-900 mb-4">Connection Configuration</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {currentFields.connection_config.map((field) => (
                          <div key={field.name}>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                              {field.label} {field.required && <span className="text-red-500">*</span>}
                            </label>
                            {renderFormField(field, 'connection_config', form.connection_config[field.name])}
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <h4 className="text-md font-medium text-gray-900 mb-4">Credentials</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {currentFields.credentials.map((field) => (
                          <div key={field.name}>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                              {field.label} {field.required && <span className="text-red-500">*</span>}
                            </label>
                            {renderFormField(field, 'credentials', form.credentials[field.name])}
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                )}

                <div className="flex justify-end space-x-3">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="px-4 py-2 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={creating}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                  >
                    {creating ? 'Creating...' : 'Create Connection'}
                  </button>
                </div>
              </form>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}