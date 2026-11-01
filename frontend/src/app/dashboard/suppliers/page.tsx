'use client';

import { useEffect, useMemo, useState } from 'react';
import * as api from '@/lib/api';
import type { Supplier } from '@/lib/api';
import { Input, Alert } from '@/components/base';

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<string>('all');

  useEffect(() => {
    const load = async () => {
      try {
        setSuppliers(await api.suppliers.list());
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load suppliers');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const categories = useMemo(
    () => Array.from(new Set(suppliers.map((s) => s.category).filter(Boolean))).sort() as string[],
    [suppliers]
  );

  const filtered = suppliers.filter((s) => {
    if (category !== 'all' && s.category !== category) return false;
    if (search && !s.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const enrichedCount = suppliers.filter((s) => (s.description || '').trim().length > 0).length;

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
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Suppliers</h1>
        <p className="text-ink/55 mt-1.5">
          Your supplier catalog · {suppliers.length} suppliers
        </p>
      </div>

      {error && <Alert variant="error" className="mb-6">{error}</Alert>}

      {/* Enrichment hint — most descriptions are empty by design */}
      <Alert variant="info" className="mb-6">
        {enrichedCount} of {suppliers.length} suppliers have a description.
        The rest are awaiting enrichment — a great spot to plug in AI-generated
        supplier profiles.
      </Alert>

      {/* Filters */}
      <div className="lio-card p-4 mb-6">
        <div className="flex flex-col md:flex-row gap-4 md:items-center">
          <div className="flex-1">
            <Input
              placeholder="Search suppliers by name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="h-11 md:max-w-xs w-full px-3.5 border border-line rounded-xl text-sm text-ink bg-white focus:outline-none focus:ring-2 focus:ring-accent-deep/60 focus:border-accent-deep/40"
          >
            <option value="all">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <span className="text-sm text-ink/45 md:w-28 md:text-right">
            {filtered.length} shown
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="lio-card overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-12 text-center text-ink/50">No suppliers found</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-ink-800/[0.03] border-b border-line">
                <tr>
                  {['Supplier', 'Category', 'Country', 'Tax ID', 'Description'].map((h) => (
                    <th
                      key={h}
                      className="px-6 py-3 text-left text-xs font-medium text-ink/45 uppercase tracking-wider"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {filtered.map((s) => (
                  <tr key={s.id} className="hover:bg-ink-800/[0.02]">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-ink">{s.name}</div>
                      {s.website && (
                        <div className="text-xs text-ink/40">
                          {s.website.replace(/^https?:\/\//, '')}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex px-2.5 py-1 text-xs font-medium rounded-full bg-accent-soft/30 text-accent-deep">
                        {s.category || '—'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink/70">
                      {s.country || '—'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink/70 font-mono">
                      {s.vat_id || '—'}
                    </td>
                    <td className="px-6 py-4 text-sm max-w-md">
                      {s.description && s.description.trim() ? (
                        <span className="text-ink/70">{s.description}</span>
                      ) : (
                        <span className="italic text-ink/35">No description yet</span>
                      )}
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
