'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import * as api from '@/lib/api';
import { Alert } from '@/components/base';
import type { ProcurementRequestWithDetails } from '@/types/database';
import { useCommodityGroups } from '@/lib/hooks/useCommodityGroups';

const STATUS_BADGE: Record<string, string> = {
  open: 'bg-green-100 text-green-800',
  in_progress: 'bg-amber-100 text-amber-800',
  closed: 'bg-ink-800/[0.08] text-ink/70',
};

const APPROVAL_BADGE: Record<string, string> = {
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-700',
  pending: 'bg-amber-100 text-amber-800',
};

const titleCase = (s: string) =>
  s.replace('_', ' ').replace(/\b\w/g, (l) => l.toUpperCase());

export default function RequestsPage() {
  const [requests, setRequests] = useState<ProcurementRequestWithDetails[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterCommodityGroup, setFilterCommodityGroup] = useState<number | 'all'>('all');
  const { data: commodityGroups } = useCommodityGroups();

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        setRequests(await api.requests.list());
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load requests');
      }
      setLoading(false);
    };
    load();
  }, []);

  const filteredRequests = requests.filter((req) => {
    if (filterStatus !== 'all' && req.status !== filterStatus) return false;
    if (filterCommodityGroup !== 'all' && req.commodity_group_id !== filterCommodityGroup)
      return false;
    return true;
  });

  if (loading) {
    return (
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-deep"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Procurement Requests</h1>
        <p className="text-ink/55 mt-1.5">Manage and track all procurement requests</p>
      </div>

      {error && <Alert variant="error" className="mb-6">{error}</Alert>}

      {/* Filters */}
      <div className="lio-card p-4 mb-6">
        <div className="flex flex-col space-y-4">
          <div className="flex items-center space-x-2">
            <span className="text-sm font-medium text-ink/70 w-24">Status:</span>
            <div className="flex items-center space-x-2 flex-1">
              {['all', 'open', 'in_progress', 'closed'].map((status) => (
                <button
                  key={status}
                  onClick={() => setFilterStatus(status)}
                  className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                    filterStatus === status
                      ? 'bg-ink text-white'
                      : 'bg-ink-800/[0.05] text-ink/70 hover:bg-ink-800/10'
                  }`}
                >
                  {status === 'all' ? 'All' : titleCase(status)}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-sm font-medium text-ink/70 w-24">Category:</span>
            <select
              value={filterCommodityGroup}
              onChange={(e) =>
                setFilterCommodityGroup(e.target.value === 'all' ? 'all' : Number(e.target.value))
              }
              className="flex-1 max-w-md px-4 py-2 border border-line rounded-xl text-sm text-ink bg-white focus:outline-none focus:ring-2 focus:ring-accent-deep/60"
            >
              <option value="all">All Categories</option>
              {commodityGroups?.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.category} - {group.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center justify-end">
            <span className="text-sm text-ink/45">
              {filteredRequests.length} request{filteredRequests.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="lio-card overflow-hidden">
        {filteredRequests.length === 0 ? (
          <div className="p-12 text-center text-ink/50">No requests found</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-ink-800/[0.03] border-b border-line">
                <tr>
                  {['Requestor', 'Title', 'Vendor', 'Category', 'Status', 'Approval', 'Total Cost', ''].map(
                    (h) => (
                      <th
                        key={h}
                        className="px-6 py-3 text-left text-xs font-medium text-ink/45 uppercase tracking-wider"
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {filteredRequests.map((request) => (
                  <tr
                    key={request.id}
                    className="hover:bg-ink-800/[0.02] cursor-pointer"
                    onClick={() => {
                      window.location.href = `/dashboard/requests/${request.id}`;
                    }}
                  >
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-ink">
                      {request.requestor_name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink/70">
                      {request.title || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink/70">
                      {request.vendor_name || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink/70">
                      {request.commodity_groups?.name || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                          STATUS_BADGE[request.status]
                        }`}
                      >
                        {titleCase(request.status)}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                          APPROVAL_BADGE[request.approval_status]
                        }`}
                      >
                        {titleCase(request.approval_status)}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-ink">
                      ${(request.total_cost || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right">
                      <Link
                        href={`/dashboard/requests/${request.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="text-accent-deep hover:underline font-medium"
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
