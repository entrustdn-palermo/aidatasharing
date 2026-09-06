'use client';

import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { useWizardSteps } from '@/hooks/useWizardSteps';
import {
  agriAPI,
  datasetsAPI,
  type AgriCrop,
  type AgriRegion,
  type RegionalAggregate,
} from '@/lib/api';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  FileSpreadsheet,
  Info,
  Loader2,
  RotateCcw,
  Upload,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

// ── Wizard data model ─────────────────────────────────────────────────
// All wizard state lives here, in the page component. The component never
// unmounts between steps, so going back preserves every entered choice.

interface FileChoice {
  file: File;
  datasetName: string;
}

interface YieldChoice {
  /** The file this suggestion was computed for — lets us skip re-fetching
   *  (and clobbering the user's override) when Continue is pressed twice. */
  sourceFile: File;
  numericColumns: string[];
  suggestion: string | null;
  selected: string | null;
}

interface TagChoice {
  regionId: number | null;
  cropId: number | null;
  season: string;
}

interface UploadResult {
  datasetId: number;
  yourYieldMean: number | null;
  aggregate: RegionalAggregate;
}

const STEP_LABELS = ['Upload', 'Yield Column', 'Region & Crop', 'Review', 'Results'];

// Formats the yield-column suggestion endpoint can read columns from.
const TABULAR_EXTENSIONS = ['csv', 'xlsx', 'xls', 'parquet'];
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB, matches the single-page upload

export default function FarmerWizardPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <FarmerWizardContent />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function FarmerWizardContent() {
  const router = useRouter();
  const wizard = useWizardSteps(STEP_LABELS.length);

  const [fileChoice, setFileChoice] = useState<FileChoice | null>(null);
  const [yieldChoice, setYieldChoice] = useState<YieldChoice | null>(null);
  const [tagChoice, setTagChoice] = useState<TagChoice>({
    regionId: null,
    cropId: null,
    season: '',
  });
  const [result, setResult] = useState<UploadResult | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const clearError = useCallback(() => setError(null), []);

  const startOver = useCallback(() => {
    setFileChoice(null);
    setYieldChoice(null);
    setTagChoice({ regionId: null, cropId: null, season: '' });
    setResult(null);
    setError(null);
    wizard.reset();
  }, [wizard]);

  // ── Step 1 → 2: validate file, fetch yield-column suggestion ──────
  const handleFileContinue = useCallback(async () => {
    if (!fileChoice) {
      setError('Choose a file to continue.');
      return;
    }
    // Already suggested for this exact file (user went back and forward):
    // keep their override, don't re-fetch or reset the selection.
    if (yieldChoice && yieldChoice.sourceFile === fileChoice.file) {
      setError(null);
      wizard.next();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const suggestion = await agriAPI.suggestYieldColumnForFile(fileChoice.file);
      if (suggestion.numeric_columns.length === 0) {
        setError(
          'No numeric columns found in this file. A yield column must be numeric — check the file and try again.',
        );
        return;
      }
      setYieldChoice({
        sourceFile: fileChoice.file,
        numericColumns: suggestion.numeric_columns,
        suggestion: suggestion.suggestion,
        selected: suggestion.suggestion ?? suggestion.numeric_columns[0],
      });
      wizard.next();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Could not read columns from the file.');
    } finally {
      setBusy(false);
    }
  }, [fileChoice, yieldChoice, wizard]);

  // ── Step 3 → 4: require region, crop, season ──────────────────────
  const handleTagsContinue = useCallback(() => {
    if (tagChoice.regionId === null) {
      setError('Pick a region.');
      return;
    }
    if (tagChoice.cropId === null) {
      setError('Pick a crop.');
      return;
    }
    if (!tagChoice.season.trim()) {
      setError('Enter a season (e.g. 2026A).');
      return;
    }
    setError(null);
    wizard.next();
  }, [tagChoice, wizard]);

  // ── Step 4 → 5: submit agri-tagged upload, fetch aggregate ────────
  const handleSubmit = useCallback(async () => {
    if (!fileChoice || !yieldChoice?.selected) {
      setError('Missing file or yield column — go back and complete those steps.');
      return;
    }
    // The stepper lets users jump back to completed steps; they may have
    // cleared a choice there. Re-validate before committing the upload.
    if (tagChoice.regionId === null || tagChoice.cropId === null || !tagChoice.season.trim()) {
      setError('Region, crop, and season are required — fix them on the Region & Crop step.');
      wizard.goTo(2);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await datasetsAPI.uploadDataset(fileChoice.file, {
        name: fileChoice.datasetName || fileChoice.file.name.replace(/\.[^/.]+$/, ''),
        agri_tags: {
          region_id: tagChoice.regionId as number,
          crop_id: tagChoice.cropId as number,
          season: tagChoice.season.trim(),
          yield_column: yieldChoice.selected,
        },
      });
      const dataset = response.dataset;
      const stats = dataset?.column_statistics?.[yieldChoice.selected];
      const yourYieldMean =
        typeof stats?.mean === 'number' && Number.isFinite(stats.mean)
          ? stats.mean
          : null;

      const aggregate = await agriAPI.regionalAggregate({
        region_id: tagChoice.regionId as number,
        crop_id: tagChoice.cropId as number,
        season: tagChoice.season.trim(),
      });
      setResult({ datasetId: dataset.id, yourYieldMean, aggregate });
      wizard.next();
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          'Upload failed. Your choices are preserved — fix the issue and submit again.',
      );
    } finally {
      setBusy(false);
    }
  }, [fileChoice, yieldChoice, tagChoice, wizard]);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Share Your Harvest Data</h1>
        <p className="mt-1 text-sm text-gray-500">
          Upload your yield data and compare it with your region — individual rows
          are never shared, only pooled averages.
        </p>
      </div>

      <StepIndicator wizard={wizard} />

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="rounded-xl border border-gray-200 bg-white p-6">
        {wizard.currentStep === 0 && (
          <UploadStep
            fileChoice={fileChoice}
            setFileChoice={setFileChoice}
            onFileChange={clearError}
          />
        )}
        {wizard.currentStep === 1 && (
          <YieldColumnStep yieldChoice={yieldChoice} setYieldChoice={setYieldChoice} />
        )}
        {wizard.currentStep === 2 && (
          <RegionCropStep tagChoice={tagChoice} setTagChoice={setTagChoice} />
        )}
        {wizard.currentStep === 3 && (
          <ReviewStep
            fileChoice={fileChoice}
            yieldChoice={yieldChoice}
            tagChoice={tagChoice}
          />
        )}
        {wizard.currentStep === 4 && result && (
          <ResultsStep result={result} onViewDataset={() => router.push(`/datasets/${result.datasetId}`)} />
        )}
      </div>

      <WizardNav
        wizard={wizard}
        busy={busy}
        onFileContinue={handleFileContinue}
        onTagsContinue={handleTagsContinue}
        onSubmit={handleSubmit}
        onStartOver={startOver}
      />
    </div>
  );
}

// ── Step indicator ────────────────────────────────────────────────────

function StepIndicator({ wizard }: { wizard: ReturnType<typeof useWizardSteps> }) {
  return (
    <ol className="flex items-center gap-1 text-xs sm:text-sm">
      {STEP_LABELS.map((label, i) => {
        // A step reads as "done" once the user has gotten past it — keyed off
        // furthestStep, not currentStep, so jumping back keeps earlier steps
        // marked complete rather than resetting them.
        const done = i < wizard.furthestStep;
        const active = i === wizard.currentStep;
        const reachable = wizard.canGoTo(i);
        return (
          <li key={label} className="flex items-center gap-1">
            {i > 0 && <span className="mx-1 h-px w-3 bg-gray-300 sm:w-5" />}
            <button
              type="button"
              disabled={!reachable}
              onClick={() => wizard.goTo(i)}
              className={`flex items-center gap-1.5 rounded-full px-2 py-1 font-medium transition-colors ${
                active
                  ? 'bg-blue-600 text-white'
                  : done
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-400'
              } ${reachable && !active ? 'hover:bg-gray-100' : ''} ${!reachable ? 'cursor-not-allowed' : ''}`}
            >
              <span
                className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] ${
                  active ? 'bg-white/20' : done ? 'bg-blue-100' : 'bg-gray-100'
                }`}
              >
                {done && !active ? <Check className="h-3 w-3" /> : i + 1}
              </span>
              <span className="hidden sm:inline">{label}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

// ── Step 1: Upload ────────────────────────────────────────────────────

function UploadStep({
  fileChoice,
  setFileChoice,
  onFileChange,
}: {
  fileChoice: FileChoice | null;
  setFileChoice: (c: FileChoice | null) => void;
  onFileChange: () => void;
}) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const acceptFile = useCallback(
    (file: File) => {
      setLocalError(null);
      const extension = file.name.split('.').pop()?.toLowerCase();
      if (!extension || !TABULAR_EXTENSIONS.includes(extension)) {
        setLocalError(
          `Unsupported file type "${file.name}". The wizard needs a tabular file: ${TABULAR_EXTENSIONS.join(', ').toUpperCase()}.`,
        );
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setLocalError(`File ${file.name} exceeds the 50MB limit.`);
        return;
      }
      setFileChoice({
        file,
        datasetName: fileChoice?.datasetName || file.name.replace(/\.[^/.]+$/, ''),
      });
      onFileChange();
    },
    [setFileChoice, onFileChange, fileChoice?.datasetName],
  );

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Upload your data file</h2>
        <p className="mt-1 text-sm text-gray-500">
          CSV or Excel export from your farm records. We will ask which column
          holds your yield per hectare.
        </p>
      </div>

      <label
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsDragOver(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragOver(false);
          const dropped = Array.from(e.dataTransfer.files);
          if (dropped.length > 0) acceptFile(dropped[0]);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
          isDragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <Upload className="h-8 w-8 text-gray-400" />
        <span className="mt-2 text-sm font-medium text-gray-700">
          {fileChoice ? fileChoice.file.name : 'Drop your file here, or click to browse'}
        </span>
        <span className="mt-1 text-xs text-gray-400">
          {TABULAR_EXTENSIONS.map((e) => e.toUpperCase()).join(', ')} · up to 50MB
        </span>
        <input
          type="file"
          className="hidden"
          accept={TABULAR_EXTENSIONS.map((e) => `.${e}`).join(',')}
          onChange={(e) => {
            const selected = e.target.files?.[0];
            if (selected) acceptFile(selected);
          }}
        />
      </label>

      {fileChoice && (
        <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
          <FileSpreadsheet className="h-5 w-5 shrink-0 text-green-600" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-gray-900">{fileChoice.file.name}</p>
            <p className="text-xs text-gray-500">
              {(fileChoice.file.size / 1024).toFixed(1)} KB
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setFileChoice(null);
              setLocalError(null);
            }}
            className="text-xs font-medium text-gray-500 hover:text-gray-700"
          >
            Remove
          </button>
        </div>
      )}

      {fileChoice && (
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Dataset name
          </label>
          <input
            type="text"
            value={fileChoice.datasetName}
            onChange={(e) =>
              setFileChoice({ ...fileChoice, datasetName: e.target.value })
            }
            className="flex h-10 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            placeholder="e.g. Rice plots 2026"
          />
        </div>
      )}

      {localError && (
        <p className="flex items-start gap-2 text-sm text-red-600">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          {localError}
        </p>
      )}
    </div>
  );
}

// ── Step 2: Yield column ──────────────────────────────────────────────

function YieldColumnStep({
  yieldChoice,
  setYieldChoice,
}: {
  yieldChoice: YieldChoice | null;
  setYieldChoice: (c: YieldChoice) => void;
}) {
  if (!yieldChoice) {
    return <p className="text-sm text-gray-500">Go back to the upload step to choose a file.</p>;
  }
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Which column is your yield?</h2>
        <p className="mt-1 text-sm text-gray-500">
          Only numeric columns are listed. We guessed the most likely one — change
          it if we got it wrong.
        </p>
      </div>

      <div className="space-y-2">
        {yieldChoice.numericColumns.map((col) => {
          const checked = yieldChoice.selected === col;
          return (
            <label
              key={col}
              className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors ${
                checked ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'
              }`}
            >
              <input
                type="radio"
                name="yield-column"
                checked={checked}
                onChange={() => setYieldChoice({ ...yieldChoice, selected: col })}
                className="h-4 w-4 border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-sm font-medium text-gray-900">{col}</span>
              {yieldChoice.suggestion === col && (
                <span className="ml-auto rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-700">
                  Suggested
                </span>
              )}
            </label>
          );
        })}
      </div>
    </div>
  );
}

// ── Step 3: Region / Crop / Season ────────────────────────────────────

function RegionCropStep({
  tagChoice,
  setTagChoice,
}: {
  tagChoice: TagChoice;
  setTagChoice: (c: TagChoice) => void;
}) {
  const [regions, setRegions] = useState<AgriRegion[]>([]);
  const [crops, setCrops] = useState<AgriCrop[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([agriAPI.listRegions(), agriAPI.listCrops()])
      .then(([r, c]) => {
        if (cancelled) return;
        setRegions(r);
        setCrops(c);
      })
      .catch((err: any) => {
        if (!cancelled) {
          setLoadError(err?.response?.data?.detail || 'Could not load region/crop lists.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Where and what did you grow?</h2>
        <p className="mt-1 text-sm text-gray-500">
          These tags place your data in the right regional pool.
        </p>
      </div>

      {loadError && (
        <p className="flex items-start gap-2 text-sm text-red-600">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          {loadError}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">Region</label>
          <select
            value={tagChoice.regionId ?? ''}
            onChange={(e) =>
              setTagChoice({ ...tagChoice, regionId: e.target.value ? Number(e.target.value) : null })
            }
            disabled={!loaded}
            className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
          >
            <option value="">{loaded ? 'Select a region' : 'Loading…'}</option>
            {regions.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
                {r.code ? ` (${r.code})` : ''}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">Crop</label>
          <select
            value={tagChoice.cropId ?? ''}
            onChange={(e) =>
              setTagChoice({ ...tagChoice, cropId: e.target.value ? Number(e.target.value) : null })
            }
            disabled={!loaded}
            className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
          >
            <option value="">{loaded ? 'Select a crop' : 'Loading…'}</option>
            {crops.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">Season</label>
        <input
          type="text"
          value={tagChoice.season}
          maxLength={50}
          onChange={(e) => setTagChoice({ ...tagChoice, season: e.target.value })}
          placeholder="e.g. 2026A"
          className="flex h-10 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <p className="mt-1 text-xs text-gray-400">
          Use the same season label as your records (e.g. 2026A for the first
          2026 planting season).
        </p>
      </div>
    </div>
  );
}

// ── Step 4: Review ────────────────────────────────────────────────────

function ReviewStep({
  fileChoice,
  yieldChoice,
  tagChoice,
}: {
  fileChoice: FileChoice | null;
  yieldChoice: YieldChoice | null;
  tagChoice: TagChoice;
}) {
  const [names, setNames] = useState<{ region: string; crop: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (tagChoice.regionId === null || tagChoice.cropId === null) return;
    Promise.all([agriAPI.listRegions(), agriAPI.listCrops()])
      .then(([regions, crops]) => {
        if (cancelled) return;
        setNames({
          region:
            regions.find((r) => r.id === tagChoice.regionId)?.name ??
            `Region #${tagChoice.regionId}`,
          crop:
            crops.find((c) => c.id === tagChoice.cropId)?.name ??
            `Crop #${tagChoice.cropId}`,
        });
      })
      .catch(() => {
        /* review falls back to ids */
      });
    return () => {
      cancelled = true;
    };
  }, [tagChoice.regionId, tagChoice.cropId]);

  const rows = [
    { label: 'File', value: fileChoice ? `${fileChoice.file.name} → "${fileChoice.datasetName}"` : '—' },
    { label: 'Yield column', value: yieldChoice?.selected ?? '—' },
    { label: 'Region', value: names?.region ?? (tagChoice.regionId !== null ? `#${tagChoice.regionId}` : '—') },
    { label: 'Crop', value: names?.crop ?? (tagChoice.cropId !== null ? `#${tagChoice.cropId}` : '—') },
    { label: 'Season', value: tagChoice.season.trim() || '—' },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Review your choices</h2>
        <p className="mt-1 text-sm text-gray-500">
          Submitting uploads your dataset and tags it for the regional pool.
        </p>
      </div>

      <dl className="divide-y divide-gray-100 rounded-lg border border-gray-200">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-4 px-4 py-3">
            <dt className="text-sm font-medium text-gray-500">{row.label}</dt>
            <dd className="truncate text-right text-sm text-gray-900">{row.value}</dd>
          </div>
        ))}
      </dl>

      <p className="flex items-start gap-2 rounded-lg bg-blue-50 p-3 text-xs text-blue-700">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        Your individual rows are never shown to anyone else. Regional results pool
        at least five contributing datasets before displaying an average.
      </p>
    </div>
  );
}

// ── Step 5: Results ───────────────────────────────────────────────────

function ResultsStep({
  result,
  onViewDataset,
}: {
  result: UploadResult;
  onViewDataset: () => void;
}) {
  const { aggregate, yourYieldMean } = result;
  const fmt = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <CheckCircle2 className="h-6 w-6 text-green-600" />
        <h2 className="text-lg font-semibold text-gray-900">Upload complete</h2>
      </div>

      {aggregate.state === 'ready' ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
              Your yield
            </p>
            <p className="mt-1 text-2xl font-bold text-gray-900">
              {yourYieldMean !== null ? fmt(yourYieldMean) : '—'}
              <span className="ml-1 text-sm font-normal text-gray-500">/ ha</span>
            </p>
            <p className="mt-1 text-xs text-gray-400">mean of your {aggregate.season} data</p>
          </div>
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-blue-600">
              Regional Aggregate
            </p>
            <p className="mt-1 text-2xl font-bold text-blue-900">
              {aggregate.pooled_mean_yield !== null ? fmt(aggregate.pooled_mean_yield) : '—'}
              <span className="ml-1 text-sm font-normal text-blue-500">/ ha</span>
            </p>
            <p className="mt-1 text-xs text-blue-500">
              pools {aggregate.contributor_count} datasets
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-semibold text-amber-800">
            Not enough regional data yet
          </p>
          <p className="mt-1 text-sm text-amber-700">
            This region + crop + season has {aggregate.contributor_count} of the{' '}
            {aggregate.minimum} contributing datasets needed before an average can
            be shown. Your upload is counted — check back once more farms have
            shared data for {aggregate.season}.
          </p>
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onViewDataset}
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700"
        >
          View dataset
        </button>
      </div>
    </div>
  );
}

// ── Navigation footer ─────────────────────────────────────────────────

function WizardNav({
  wizard,
  busy,
  onFileContinue,
  onTagsContinue,
  onSubmit,
  onStartOver,
}: {
  wizard: ReturnType<typeof useWizardSteps>;
  busy: boolean;
  onFileContinue: () => void;
  onTagsContinue: () => void;
  onSubmit: () => void;
  onStartOver: () => void;
}) {
  const step = wizard.currentStep;

  const handlePrimary = () => {
    if (step === 0) onFileContinue();
    else if (step === 1) wizard.next();
    else if (step === 2) onTagsContinue();
    else if (step === 3) onSubmit();
  };

  const primaryLabel =
    step === 0 ? 'Continue' : step === 3 ? 'Submit upload' : 'Continue';

  if (step === 4) {
    return (
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onStartOver}
          className="inline-flex h-10 items-center gap-2 rounded-lg border-2 border-gray-300 bg-white px-4 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          <RotateCcw className="h-4 w-4" />
          Share another file
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between">
      <button
        type="button"
        onClick={wizard.back}
        disabled={wizard.isFirstStep || busy}
        className="inline-flex h-10 items-center gap-2 rounded-lg px-4 text-sm font-medium text-gray-600 hover:bg-gray-100 disabled:pointer-events-none disabled:opacity-40"
      >
        <ArrowLeft className="h-4 w-4" />
        Back
      </button>
      <button
        type="button"
        onClick={handlePrimary}
        disabled={busy}
        className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-600 px-6 text-sm font-medium text-white hover:bg-blue-700 disabled:pointer-events-none disabled:opacity-50"
      >
        {busy && <Loader2 className="h-4 w-4 animate-spin" />}
        {primaryLabel}
        {!busy && step < 3 && <ArrowRight className="h-4 w-4" />}
      </button>
    </div>
  );
}
