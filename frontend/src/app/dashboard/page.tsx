'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import * as api from '@/lib/api';
import { Button } from '@/components/base';
import { PieChart, type PieChartData } from '@/components/PieChart';
import type { CommodityGroup, ProcurementRequestWithDetails } from '@/types/database';

export default function DashboardPage() {
  const [requests, setRequests] = useState<ProcurementRequestWithDetails[]>([]);
  const [commodityGroups, setCommodityGroups] = useState<CommodityGroup[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [requestsData, groups] = await Promise.all([
          api.requests.list(),
          api.commodityGroups.list(),
        ]);
        setRequests(requestsData);
        setCommodityGroups(groups);
      } catch (err) {
        console.error('Failed to load dashboard data:', err);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-deep"></div>
        </div>
      </div>
    );
  }

  // Calculate stats
  const totalRequests = requests.length;
  const openRequests = requests.filter((r) => r.status === 'open').length;
  const inProgressRequests = requests.filter((r) => r.status === 'in_progress').length;
  const closedRequests = requests.filter((r) => r.status === 'closed').length;
  const totalValue = requests.reduce((sum, r) => sum + (r.total_cost || 0), 0);

  // Prepare pie chart data for all requests by status
  const statusData: PieChartData[] = [
    { name: 'Open', value: openRequests },
    { name: 'In Progress', value: inProgressRequests },
    { name: 'Closed', value: closedRequests },
  ].filter((item) => item.value > 0);

  // Prepare pie chart data for closed requests by commodity group
  const closedRequestsData = requests.filter((r) => r.status === 'closed');
  const closedCommodityGroupData: PieChartData[] = [];
  
  if (closedRequestsData.length > 0 && commodityGroups.length > 0) {
    const groupTotals = new Map<number, { name: string; value: number }>();
    
    closedRequestsData.forEach((request) => {
      if (request.commodity_group_id && request.total_cost) {
        const group = commodityGroups.find((g) => g.id === request.commodity_group_id);
        if (group) {
          const existing = groupTotals.get(group.id);
          if (existing) {
            existing.value += request.total_cost;
          } else {
            groupTotals.set(group.id, {
              name: group.name,
              value: request.total_cost,
            });
          }
        }
      }
    });
    
    closedCommodityGroupData.push(...groupTotals.values());
  }

  // Prepare pie chart data for ALL requests by commodity group
  const allCommodityGroupData: PieChartData[] = [];
  
  if (requests.length > 0 && commodityGroups.length > 0) {
    const groupTotals = new Map<number, { name: string; value: number }>();
    
    requests.forEach((request) => {
      if (request.commodity_group_id && request.total_cost) {
        const group = commodityGroups.find((g) => g.id === request.commodity_group_id);
        if (group) {
          const existing = groupTotals.get(group.id);
          if (existing) {
            existing.value += request.total_cost;
          } else {
            groupTotals.set(group.id, {
              name: group.name,
              value: request.total_cost,
            });
          }
        }
      }
    });
    
    allCommodityGroupData.push(...groupTotals.values());
  }

  // Placeholder data for empty charts
  const placeholderStatusData: PieChartData[] = [
    { name: 'Open', value: 45 },
    { name: 'In Progress', value: 30 },
    { name: 'Closed', value: 25 },
  ];

  const placeholderCommodityData: PieChartData[] = [
    { name: 'IT Equipment', value: 35 },
    { name: 'Office Supplies', value: 25 },
    { name: 'Furniture', value: 20 },
    { name: 'Software', value: 20 },
  ];

  return (
    <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Overview</h1>
        <p className="text-ink/55 mt-1.5">
          Welcome to your procurement workspace
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {/* Total Requests */}
        <div className="lio-card p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-ink/55">Total Requests</p>
              <p className="text-3xl font-semibold tracking-tight text-ink mt-2">{totalRequests}</p>
            </div>
            <div className="w-12 h-12 bg-accent-soft/40 rounded-xl flex items-center justify-center">
              <svg
                className="w-6 h-6 text-accent-deep"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
          </div>
        </div>

        {/* Open Requests */}
        <div className="lio-card p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-ink/55">Open</p>
              <p className="text-3xl font-bold text-green-600 mt-2">{openRequests}</p>
            </div>
            <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
              <svg
                className="w-6 h-6 text-green-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
            </div>
          </div>
        </div>

        {/* In Progress */}
        <div className="lio-card p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-ink/55">In Progress</p>
              <p className="text-3xl font-bold text-yellow-600 mt-2">{inProgressRequests}</p>
            </div>
            <div className="w-12 h-12 bg-yellow-100 rounded-lg flex items-center justify-center">
              <svg
                className="w-6 h-6 text-yellow-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
          </div>
        </div>

        {/* Closed */}
        <div className="lio-card p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-ink/55">Closed</p>
              <p className="text-3xl font-bold text-gray-600 mt-2">{closedRequests}</p>
            </div>
            <div className="w-12 h-12 bg-gray-100 rounded-lg flex items-center justify-center">
              <svg
                className="w-6 h-6 text-gray-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
            </div>
          </div>
        </div>
      </div>

      {/* Pie Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Requests by Status */}
        <div className="lio-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold tracking-tight text-ink">Requests by Status</h2>
          </div>
          <div className="relative flex items-center justify-center min-h-[320px]">
            {statusData.length > 0 ? (
              <PieChart
                data={statusData}
                size={280}
                showLabels={false}
                showLegend={true}
              />
            ) : (
              <>
                <div className="opacity-30">
                  <PieChart
                    data={placeholderStatusData}
                    size={280}
                    showLabels={false}
                    showLegend={true}
                  />
                </div>
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="bg-white/95 backdrop-blur-sm rounded-lg shadow-lg p-6 max-w-[200px] text-center">
                    <p className="text-sm text-gray-700 font-medium">
                      Your data will appear here once you create your first request
                    </p>
                    <Link href="/dashboard/new-request" className="mt-3 inline-block">
                      <Button variant="primary" size="sm">
                        Create Request
                      </Button>
                    </Link>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Closed Requests by Commodity Group */}
        <div className="lio-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold tracking-tight text-ink">
              Closed Requests by Group
            </h2>
          </div>
          <div className="relative flex items-center justify-center min-h-[320px]">
            {closedCommodityGroupData.length > 0 ? (
              <PieChart
                data={closedCommodityGroupData}
                size={280}
                showLabels={false}
                showLegend={true}
              />
            ) : (
              <>
                <div className="opacity-30">
                  <PieChart
                    data={placeholderCommodityData}
                    size={280}
                    showLabels={false}
                    showLegend={true}
                  />
                </div>
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="bg-white/95 backdrop-blur-sm rounded-lg shadow-lg p-6 max-w-[200px] text-center">
                    <p className="text-sm text-gray-700 font-medium">
                      Your closed requests data will appear here
                    </p>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* All Requests by Commodity Group */}
        <div className="lio-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold tracking-tight text-ink">
              All Requests by Group
            </h2>
          </div>
          <div className="relative flex items-center justify-center min-h-[320px]">
            {allCommodityGroupData.length > 0 ? (
              <PieChart
                data={allCommodityGroupData}
                size={280}
                showLabels={false}
                showLegend={true}
              />
            ) : (
              <>
                <div className="opacity-30">
                  <PieChart
                    data={placeholderCommodityData}
                    size={280}
                    showLabels={false}
                    showLegend={true}
                  />
                </div>
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="bg-white/95 backdrop-blur-sm rounded-lg shadow-lg p-6 max-w-[200px] text-center">
                    <p className="text-sm text-gray-700 font-medium">
                      Your requests data will appear here once commodity groups are assigned
                    </p>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Recent Requests */}
      <div className="lio-card">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold tracking-tight text-ink">Recent Requests</h2>
            <div className="flex items-center gap-3">
              <Link href="/dashboard/requests">
                <Button variant="outline" size="sm">
                  View All
                </Button>
              </Link>
              <Link href="/dashboard/new-request">
                <Button variant="primary" size="sm">
                  + New Request
                </Button>
              </Link>
            </div>
          </div>
        </div>

        {requests.length === 0 ? (
          <div className="p-12 text-center">
            <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg
                className="w-8 h-8 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">No requests yet</h3>
            <p className="text-gray-600 mb-6">
              Get started by creating your first procurement request
            </p>
            <Link href="/dashboard/new-request">
              <Button>Create First Request</Button>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Requestor
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Title
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Vendor
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Total Cost
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {requests.slice(0, 5).map((request) => (
                  <tr key={request.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {request.requestor_name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {request.title || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {request.vendor_name || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                          request.status === 'open'
                            ? 'bg-green-100 text-green-800'
                            : request.status === 'in_progress'
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {request.status.replace('_', ' ').replace(/\b\w/g, (l: string) => l.toUpperCase())}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      ${(request.total_cost || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
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

