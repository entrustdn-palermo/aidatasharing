'use client';

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';

export default function LegacySharedDatasetPage() {
  const params = useParams();
  const router = useRouter();
  const token = params.token as string;

  useEffect(() => {
    if (token) {
      router.replace(`/shared/${token}`);
    }
  }, [router, token]);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-center">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600 mx-auto" />
        <p className="mt-4 text-sm text-gray-600">Opening shared dataset...</p>
      </div>
    </div>
  );
}
