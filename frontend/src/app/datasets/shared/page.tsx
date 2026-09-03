'use client';

import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { useAuth } from '@/components/auth/AuthProvider';
import { useState, useEffect } from 'react';
import { dataSharingAPI } from '@/lib/api';
import { SharingLevelBadge } from '@/components/datasets/SharingLevelSelector';
import Link from 'next/link';
import {Share2, Copy, ExternalLink, Eye, Shield, PowerOff, Calendar, Users, MessageSquare} from 'lucide-react';

interface SharedDataset {
  id: number;
  name: string;
  description: string;
  share_token: string;
  share_url: string;
  view_count: number;
  chat_enabled: boolean;
  password_protected: boolean;
  created_at: string;
  last_accessed?: string;
  sharing_level?: 'private' | 'organization' | 'public';
  type?: string;
  size_bytes?: number;
  is_valid?: boolean;
  validation_details?: {
    is_expired: boolean;
    connector_valid: boolean;
    file_valid: boolean;
  };
}

export default function SharedDatasetsPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <SharedDatasetsContent />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function SharedDatasetsContent() {
  const { user } = useAuth();
  const [sharedDatasets, setSharedDatasets] = useState<SharedDataset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  useEffect(() => {
    fetchSharedDatasets();
  }, []);

  const fetchSharedDatasets = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await dataSharingAPI.getMySharedDatasets();
      console.log('Shared datasets response:', response); // Debug log
      setSharedDatasets(response);
    } catch (error: any) {
      console.error('Failed to fetch shared datasets:', error);
      setError(error.response?.data?.detail || 'Failed to fetch shared datasets');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDisableSharing = async (datasetId: number, datasetName: string) => {
    if (!confirm(`Are you sure you want to disable sharing for "${datasetName}"? This will invalidate the share link.`)) {
      return;
    }

    try {
      await dataSharingAPI.disableSharing(datasetId);
      fetchSharedDatasets(); // Refresh the list
    } catch (error: any) {
      console.error('Failed to disable sharing:', error);
      alert(error.response?.data?.detail || 'Failed to disable sharing');
    }
  };

  const copyShareLink = (shareUrl: string) => {
    const fullUrl = shareUrl.startsWith('http') ? shareUrl : `${window.location.origin}${shareUrl}`;
    navigator.clipboard.writeText(fullUrl);
    alert('Share link copied to clipboard!');
  };

  const openShareLink = (shareUrl: string) => {
    const fullUrl = shareUrl.startsWith('http') ? shareUrl : `${window.location.origin}${shareUrl}`;
    window.open(fullUrl, '_blank');
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
                <h3 className="text-sm font-medium text-red-800">Error loading shared datasets</h3>
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
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center">
                <Share2 className="h-7 w-7 mr-3 text-blue-600" />
                Shared Datasets
              </h1>
              <p className="mt-1 text-sm text-gray-600">
                Manage your shared datasets and monitor access analytics across different sharing levels.
              </p>
            </div>
            <div className="flex space-x-3">
              <button
                onClick={fetchSharedDatasets}
                className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-md text-sm font-medium"
              >
                Refresh
              </button>
              <button
                onClick={async () => {
                  console.log('Fetching ONLY valid datasets...');
                  const response = await dataSharingAPI.getMySharedDatasets(false);
                  console.log('Only valid shared datasets:', response);
                }}
                className="bg-yellow-600 hover:bg-yellow-700 text-white px-4 py-2 rounded-md text-sm font-medium"
              >
                Debug (Only Valid)
              </button>
              <Link
                href="/datasets"
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-medium"
              >
                View All Datasets
              </Link>
            </div>
          </div>
        </div>

        {/* Stats Overview */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <Share2 className="h-8 w-8 text-blue-600" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">Total Shared</dt>
                    <dd className="text-lg font-medium text-gray-900">{sharedDatasets.length}</dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <Eye className="h-8 w-8 text-green-600" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">Total Views</dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {sharedDatasets.reduce((sum, dataset) => sum + (dataset.view_count || 0), 0)}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <MessageSquare className="h-8 w-8 text-purple-600" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">Chat Enabled</dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {sharedDatasets.filter(dataset => dataset.chat_enabled).length}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <Shield className="h-8 w-8 text-orange-600" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">Protected</dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {sharedDatasets.filter(dataset => dataset.password_protected).length}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Shared Datasets List */}
        {sharedDatasets.length === 0 ? (
          <div className="text-center py-12">
            <Share2 className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-2 text-sm font-medium text-gray-900">No shared datasets</h3>
            <p className="mt-1 text-sm text-gray-500">
              You haven't shared any datasets yet. Share a dataset to get started.
            </p>
            <div className="mt-6">
              <Link
                href="/datasets"
                className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
              >
                <Share2 className="w-4 h-4 mr-2" />
                Browse Datasets
              </Link>
            </div>
          </div>
        ) : (
          <div className="bg-white shadow overflow-hidden sm:rounded-md">
            <ul className="divide-y divide-gray-200">
              {sharedDatasets.map((dataset) => (
                <li key={dataset.id}>
                  <div className="px-6 py-6 hover:bg-gray-50">
                    <div className="flex items-center justify-between">
                      {/* Dataset Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center space-x-3">
                          <h3 className="text-lg font-medium text-gray-900 truncate">
                            {dataset.name}
                          </h3>
                          <SharingLevelBadge level={(dataset.sharing_level?.toLowerCase() || 'private') as 'private' | 'organization' | 'public'} />
                          <div className="flex space-x-2">
                            {dataset.chat_enabled && (
                              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                                <MessageSquare className="w-3 h-3 mr-1" />
                                Chat
                              </span>
                            )}
                            {dataset.password_protected && (
                              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                                <Shield className="w-3 h-3 mr-1" />
                                Protected
                              </span>
                            )}
                            {dataset.is_valid === false && (
                              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">
                                ⚠️ Validation Issues
                              </span>
                            )}
                          </div>
                        </div>
                        
                        <p className="mt-1 text-sm text-gray-600 line-clamp-2">
                          {dataset.description || 'No description provided'}
                        </p>
                        
                        <div className="flex items-center space-x-4 text-xs text-gray-500 mt-2">
                          {dataset.type && <span>Type: {dataset.type.toUpperCase()}</span>}
                          {dataset.size_bytes && (
                            <>
                              <span>•</span>
                              <span>Size: {formatFileSize(dataset.size_bytes)}</span>
                            </>
                          )}
                        </div>

                        {/* Share Link */}
                        <div className="mt-3 bg-gray-50 rounded-md p-3">
                          <div className="flex items-center space-x-2">
                            <input
                              type="text"
                              value={dataset.share_url.startsWith('http') ? dataset.share_url : `${window.location.origin}${dataset.share_url}`}
                              readOnly
                              className="flex-1 text-sm bg-white border border-gray-300 rounded px-3 py-1 font-mono"
                            />
                            <button
                              onClick={() => copyShareLink(dataset.share_url)}
                              className="p-1 text-gray-500 hover:text-gray-700"
                              title="Copy link"
                            >
                              <Copy className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => openShareLink(dataset.share_url)}
                              className="p-1 text-gray-500 hover:text-gray-700"
                              title="Open link"
                            >
                              <ExternalLink className="h-4 w-4" />
                            </button>
                          </div>
                        </div>

                        {/* Stats */}
                        <div className="mt-3 flex items-center space-x-6 text-sm text-gray-500">
                          <div className="flex items-center">
                            <Eye className="w-4 h-4 mr-1" />
                            <span>{dataset.view_count} views</span>
                          </div>
                          <div className="flex items-center">
                            <Calendar className="w-4 h-4 mr-1" />
                            <span>Created {new Date(dataset.created_at).toLocaleDateString()}</span>
                          </div>
                          {dataset.last_accessed && (
                            <div className="flex items-center">
                              <Users className="w-4 h-4 mr-1" />
                              <span>Last accessed {new Date(dataset.last_accessed).toLocaleDateString()}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center space-x-2 ml-6">
                        <Link
                          href={`/datasets/${dataset.id}`}
                          className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                        >
                          View Dataset
                        </Link>
                        
                        <button
                          onClick={() => handleDisableSharing(dataset.id, dataset.name)}
                          className="flex items-center px-3 py-2 border border-red-300 text-red-700 rounded-md hover:bg-red-50 text-sm"
                        >
                          <PowerOff className="w-4 h-4 mr-1" />
                          Disable
                        </button>
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}