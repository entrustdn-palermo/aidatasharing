/**
 * API Module Index
 * Central export point for all API modules
 *
 * Usage:
 *   import { authAPI, datasetsAPI } from '@/lib/api';
 *
 * All modules have been migrated to individual files for better:
 * - Tree-shaking: Only import what you need
 * - Code splitting: Smaller bundle sizes
 * - Maintainability: Easier to update individual modules
 */

// Export client for direct access if needed
export { apiClient, API_BASE_URL } from './client';

// Export all modular API modules
export { authAPI } from './auth';
export { adminAPI } from './admin';
export { organizationsAPI } from './organizations';
export { datasetsAPI } from './datasets';
export { dataSharingAPI } from './data-sharing';
export { chatAPI } from './chat';
export { mindsdbAPI } from './mindsdb';
export { modelsAPI } from './models';
export { dataAccessAPI } from './data-access';
export { analyticsAPI } from './analytics';
export { dataConnectorsAPI } from './data-connectors';
export { proxyConnectorsAPI } from './proxy-connectors';
export { sharedLinksAPI } from './shared-links';
export { agentsAPI } from './agents';
