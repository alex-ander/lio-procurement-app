'use client';

import { useEffect, useState } from 'react';
import * as api from '@/lib/api';
import { Button, Alert } from '@/components/base';
import type { ProcurementRequestWithDetails } from '@/types/database';

export default function ApprovalsPage() {
  const [requests, setRequests] = useState<ProcurementRequestWithDetails[]>([]);
  const [role, setRole] = useState<api.MemberRole | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [deciding, setDeciding] = useState<string | null>(null);

  useEffect(() => {
    load();
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [org, list] = await Promise.all([
        api.organizations.getMine(),
        api.requests.list(),
      ]);
      setRole(org.role);
      setRequests(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load requests');
    }
    setLoading(false);
  };

  const decide = async (requestId: string, decision: 'approved' | 'rejected') => {
    setError('');
    setSuccess('');
    setDeciding(requestId);
    try {
      await api.requests.decideApproval(requestId, decision);
      setSuccess(`Request ${decision}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit decision');
    }
    setDeciding(null);
  };

  if (loading) {
    return (
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-deep"></div>
        </div>
      </div>
    );
  }

  const canApprove = role === 'buyer' || role === 'admin';
  const pending = requests.filter((r) => r.approval_status === 'pending');
  const decided = requests.filter((r) => r.approval_status !== 'pending').slice(0, 10);

  return (
    <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Approvals</h1>
        <p className="text-ink/55 mt-1.5">
          Review and approve procurement requests for your organization
        </p>
      </div>

      {error && <Alert variant="error" className="mb-6">{error}</Alert>}
      {success && <Alert variant="success" className="mb-6">{success}</Alert>}

      {!canApprove && (
        <Alert variant="info" className="mb-6">
          Only buyers and admins can approve requests.
        </Alert>
      )}

      {/* Pending */}
      <div className="lio-card overflow-hidden mb-8">
        <div className="p-6 border-b border-line">
          <h2 className="text-xl font-semibold tracking-tight text-ink">
            Pending ({pending.length})
          </h2>
        </div>
        {pending.length === 0 ? (
          <div className="p-12 text-center text-ink/50">
            Nothing waiting for approval. 🎉
          </div>
        ) : (
          <div className="divide-y divide-line">
            {pending.map((request) => (
              <div key={request.id} className="p-6 flex flex-col md:flex-row md:items-center gap-4">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-ink">{request.title}</p>
                  <p className="text-sm text-ink/55 mt-0.5">
                    {request.requestor_name}
                    {request.department ? ` · ${request.department}` : ''} ·{' '}
                    {request.vendor_name}
                    {request.commodity_groups ? ` · ${request.commodity_groups.name}` : ''}
                  </p>
                </div>
                <div className="text-lg font-semibold text-ink whitespace-nowrap">
                  ${(request.total_cost || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
                {canApprove && (
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={() => decide(request.id, 'approved')}
                      disabled={deciding === request.id}
                      loading={deciding === request.id}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-red-600 border-red-300 hover:bg-red-50"
                      onClick={() => decide(request.id, 'rejected')}
                      disabled={deciding === request.id}
                    >
                      Reject
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recently decided */}
      {decided.length > 0 && (
        <div className="lio-card overflow-hidden">
          <div className="p-6 border-b border-line">
            <h2 className="text-xl font-semibold tracking-tight text-ink">Recently decided</h2>
          </div>
          <div className="divide-y divide-line">
            {decided.map((request) => (
              <div key={request.id} className="p-6 flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-ink">{request.title}</p>
                  <p className="text-sm text-ink/55 mt-0.5">
                    {request.requestor_name} · {request.vendor_name}
                  </p>
                </div>
                <div className="text-sm font-medium text-ink whitespace-nowrap">
                  ${(request.total_cost || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
                <span
                  className={`inline-flex px-2.5 py-1 text-xs font-semibold rounded-full ${
                    request.approval_status === 'approved'
                      ? 'bg-green-100 text-green-800'
                      : 'bg-red-100 text-red-700'
                  }`}
                >
                  {request.approval_status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
