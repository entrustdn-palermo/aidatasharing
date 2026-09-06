'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Database, Brain, Play, Trash2, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { modelsAPI, DatasetModelInfo, ModelStatusInfo } from '@/lib/api';

interface DatasetModelsCardProps {
  datasetId: number;
  columnStatistics: Record<string, any> | null;
  isOwner: boolean;
}

export function DatasetModelsCard({ datasetId, columnStatistics, isOwner }: DatasetModelsCardProps) {
  const [models, setModels] = useState<DatasetModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Training form
  const [targetColumn, setTargetColumn] = useState('');
  const [training, setTraining] = useState(false);
  const [trainError, setTrainError] = useState<string | null>(null);

  // Polling
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelledRef = useRef(false);

  // Prediction form per model
  const [predictInputs, setPredictInputs] = useState<Record<number, Record<string, string>>>({});
  const [predictResults, setPredictResults] = useState<Record<number, Record<string, any>[]>>({});
  const [predictingIds, setPredictingIds] = useState<Set<number>>(new Set());
  const [expandedPredictId, setExpandedPredictId] = useState<number | null>(null);

  const columns = columnStatistics ? Object.keys(columnStatistics) : [];

  const fetchModels = useCallback(async () => {
    try {
      const all = await modelsAPI.listModels();
      // Filter to models belonging to this dataset
      setModels(all.filter((m) => m.dataset_id === datasetId));
    } catch (e: any) {
      console.error('Failed to fetch models:', e);
    }
  }, [datasetId]);

  const pollTrainingModels = useCallback((currentModels: DatasetModelInfo[]) => {
    const trainingModels = currentModels.filter((m) => m.status === 'training');
    if (trainingModels.length === 0 || cancelledRef.current) return;

    let attempts = 0;
    const maxAttempts = 60;

    const poll = async () => {
      if (cancelledRef.current || attempts >= maxAttempts) return;
      attempts++;

      try {
        const all = await modelsAPI.listModels();
        const updated = all.filter((m) => m.dataset_id === datasetId);
        setModels(updated);

        const stillTraining = updated.some((m) => m.status === 'training');
        if (stillTraining) {
          pollingRef.current = setTimeout(poll, 5000);
        }
      } catch {
        // Retry on network error
        pollingRef.current = setTimeout(poll, 5000);
      }
    };

    pollingRef.current = setTimeout(poll, 5000);
  }, [datasetId]);

  // Initial fetch
  useEffect(() => {
    cancelledRef.current = false;
    setLoading(true);
    fetchModels().finally(() => setLoading(false));
    return () => {
      cancelledRef.current = true;
      if (pollingRef.current) clearTimeout(pollingRef.current);
    };
  }, [fetchModels]);

  // Start polling when models are loaded
  useEffect(() => {
    if (!loading) {
      pollTrainingModels(models);
    }
  }, [loading, models, pollTrainingModels]);

  const handleTrain = async () => {
    if (!targetColumn) return;
    setTraining(true);
    setTrainError(null);
    try {
      const created = await modelsAPI.trainModel({
        dataset_id: datasetId,
        target_column: targetColumn,
      });
      setModels((prev) => [created, ...prev]);
      setTargetColumn('');
      // Start polling immediately
      cancelledRef.current = false;
      pollTrainingModels([created, ...models]);
    } catch (e: any) {
      setTrainError(e.response?.data?.detail || e.message || 'Training failed');
    } finally {
      setTraining(false);
    }
  };

  const handleDelete = async (modelId: number) => {
    if (!confirm('Delete this model? This will also drop it from MindsDB.')) return;
    try {
      await modelsAPI.deleteModel(modelId);
      setModels((prev) => prev.filter((m) => m.id !== modelId));
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Failed to delete model');
    }
  };

  const handlePredict = async (model: DatasetModelInfo) => {
    const input = predictInputs[model.id] || {};
    const parsed: Record<string, any> = {};
    for (const [k, v] of Object.entries(input)) {
      const num = Number(v);
      parsed[k] = isNaN(num) ? v : num;
    }
    setPredictingIds((prev) => new Set(prev).add(model.id));
    try {
      const result = await modelsAPI.predict(model.id, parsed);
      setPredictResults((prev) => ({ ...prev, [model.id]: result.predictions }));
      setExpandedPredictId(model.id);
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Prediction failed');
    } finally {
      setPredictingIds((prev) => {
        const next = new Set(prev);
        next.delete(model.id);
        return next;
      });
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'training':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
            <Loader2 className="w-3 h-3 mr-1 animate-spin" />
            Training
          </span>
        );
      case 'complete':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
            <div className="w-2 h-2 bg-green-500 rounded-full mr-1.5" />
            Complete
          </span>
        );
      case 'error':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
            <div className="w-2 h-2 bg-red-500 rounded-full mr-1.5" />
            Error
          </span>
        );
      default:
        return (
          <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
            {status}
          </span>
        );
    }
  };

  const formatTrainingTime = (seconds: number | null) => {
    if (seconds == null) return '';
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  };

  const formatAccuracy = (accuracy: string | null) => {
    if (!accuracy) return null;
    try {
      const parsed = JSON.parse(accuracy);
      const key = Object.keys(parsed)[0];
      if (key && parsed[key] != null) {
        const val = typeof parsed[key] === 'number' ? parsed[key] : parseFloat(parsed[key]);
        if (!isNaN(val)) return `${key}: ${(val * 100).toFixed(1)}%`;
      }
    } catch {
      // Not JSON, show raw
    }
    return accuracy;
  };

  // Derive feature columns for prediction form
  const getFeatureColumns = (model: DatasetModelInfo): string[] => {
    if (model.feature_columns && model.feature_columns.length > 0) {
      return model.feature_columns.filter((c) => c !== model.target_column);
    }
    // Fallback: all columns minus target
    return columns.filter((c) => c !== model.target_column);
  };

  if (loading) {
    return (
      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      </div>
    );
  }

  return (
    <div id="ai-models" className="bg-white shadow rounded-lg p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <Brain className="h-5 w-5 text-indigo-600" />
          <h2 className="text-lg font-medium text-gray-900">AI Models</h2>
        </div>
        {models.length > 0 && (
          <span className="text-sm text-gray-500">{models.length} model{models.length !== 1 ? 's' : ''}</span>
        )}
      </div>

      {/* Train form — only for owner */}
      {isOwner && columns.length > 0 && (
        <div className="mb-6 p-4 border border-dashed border-gray-300 rounded-lg">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Train New Model</h3>
          <div className="flex items-end space-x-3">
            <div className="flex-1">
              <label className="block text-xs text-gray-500 mb-1">Target Column</label>
              <select
                value={targetColumn}
                onChange={(e) => setTargetColumn(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Select target...</option>
                {columns.map((col) => (
                  <option key={col} value={col}>{col}</option>
                ))}
              </select>
            </div>
            <button
              onClick={handleTrain}
              disabled={!targetColumn || training}
              className="flex items-center px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {training ? (
                <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Training...</>
              ) : (
                <><Brain className="w-4 h-4 mr-1.5" /> Train</>
              )}
            </button>
          </div>
          {trainError && (
            <p className="mt-2 text-sm text-red-600">{trainError}</p>
          )}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg mb-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* No models state */}
      {!error && models.length === 0 && (
        <div className="py-8 text-center">
          <Database className="mx-auto h-8 w-8 text-gray-300" />
          <p className="mt-2 text-sm text-gray-500">No models trained yet</p>
          {isOwner && columns.length > 0 && (
            <p className="text-xs text-gray-400 mt-1">Select a target column above to train your first model</p>
          )}
        </div>
      )}

      {/* Model list */}
      {models.length > 0 && (
        <ul className="divide-y divide-gray-200">
          {models.map((model) => {
            const features = getFeatureColumns(model);
            return (
              <li key={model.id} className="py-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-2 mb-1">
                      <p className="text-sm font-medium text-gray-900 truncate">{model.name}</p>
                      {getStatusBadge(model.status)}
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                      <span>Target: <strong>{model.target_column}</strong></span>
                      {model.accuracy && (
                        <span>Accuracy: <strong>{formatAccuracy(model.accuracy)}</strong></span>
                      )}
                      {model.training_time != null && (
                        <span>Training: <strong>{formatTrainingTime(model.training_time)}</strong></span>
                      )}
                      <span>Predictions: <strong>{model.prediction_count}</strong></span>
                    </div>
                    {model.error_message && model.status === 'error' && (
                      <p className="mt-1 text-xs text-red-600">{model.error_message}</p>
                    )}
                  </div>
                  {isOwner && (
                    <button
                      onClick={() => handleDelete(model.id)}
                      className="ml-3 p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                      title="Delete model"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>

                {/* Predict form (complete models only) */}
                {model.status === 'complete' && features.length > 0 && (
                  <div className="mt-3 ml-4 pl-3 border-l-2 border-indigo-200">
                    <button
                      onClick={() => setExpandedPredictId(expandedPredictId === model.id ? null : model.id)}
                      className="flex items-center text-xs font-medium text-indigo-600 hover:text-indigo-800"
                    >
                      {expandedPredictId === model.id ? (
                        <><ChevronUp className="w-3 h-3 mr-1" /> Hide prediction form</>
                      ) : (
                        <><ChevronDown className="w-3 h-3 mr-1" /> Predict with this model</>
                      )}
                    </button>

                    {expandedPredictId === model.id && (
                      <div className="mt-2 space-y-2">
                        <div className="grid grid-cols-2 gap-2">
                          {features.map((col) => (
                            <div key={col}>
                              <label className="block text-xs text-gray-500 mb-0.5">{col}</label>
                              <input
                                type="text"
                                value={predictInputs[model.id]?.[col] || ''}
                                onChange={(e) =>
                                  setPredictInputs((prev) => ({
                                    ...prev,
                                    [model.id]: { ...(prev[model.id] || {}), [col]: e.target.value },
                                  }))
                                }
                                placeholder="Value"
                                className="w-full border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                              />
                            </div>
                          ))}
                        </div>
                        <button
                          onClick={() => handlePredict(model)}
                          disabled={predictingIds.has(model.id)}
                          className="flex items-center px-3 py-1.5 bg-indigo-50 text-indigo-700 text-xs font-medium rounded-md hover:bg-indigo-100 disabled:opacity-50"
                        >
                          {predictingIds.has(model.id) ? (
                            <><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Predicting...</>
                          ) : (
                            <><Play className="w-3 h-3 mr-1" /> Predict</>
                          )}
                        </button>

                        {/* Prediction results */}
                        {predictResults[model.id] && predictResults[model.id].length > 0 && (
                          <div className="mt-2 p-3 bg-gray-50 border border-gray-200 rounded-md">
                            <p className="text-xs font-medium text-gray-700 mb-1">Prediction Results</p>
                            <div className="space-y-1">
                              {predictResults[model.id].map((row, i) => (
                                <div key={i} className="text-xs text-gray-600 font-mono bg-white p-2 rounded border border-gray-100">
                                  {Object.entries(row).map(([k, v]) => (
                                    <span key={k} className="mr-3">
                                      <span className="text-gray-400">{k}:</span>{' '}
                                      <span className="font-medium">{String(v)}</span>
                                    </span>
                                  ))}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
