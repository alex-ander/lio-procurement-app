'use client';

import { useEffect, useState } from 'react';
import * as api from '@/lib/api';
import type { ArticlePage } from '@/lib/api';
import { Input, Alert } from '@/components/base';

const PAGE_SIZE = 25;

function formatPrice(value: string, currency: string): string {
  const n = Number(value);
  if (Number.isNaN(n)) return value;
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(n);
  } catch {
    return `${currency} ${n.toFixed(2)}`;
  }
}

function formatQuantity(value: string): string {
  const n = Number(value);
  if (Number.isNaN(n)) return value;
  // Drop trailing zeros: 1.000 -> "1", 1.500 -> "1.5"
  return String(Number(n.toFixed(3)));
}

export default function ArticlesPage() {
  const [page, setPage] = useState<ArticlePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [offset, setOffset] = useState(0);

  // Debounce the search box, and reset to the first page whenever it changes.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const result = await api.articles.list({
          search: debouncedSearch || undefined,
          limit: PAGE_SIZE,
          offset,
        });
        if (!cancelled) {
          setPage(result);
          setError('');
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load articles');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [debouncedSearch, offset]);

  const total = page?.total ?? 0;
  const items = page?.items ?? [];
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  return (
    <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Articles</h1>
        <p className="text-ink/55 mt-1.5">
          Your article catalog · {total.toLocaleString('en-US')} articles
        </p>
      </div>

      {error && <Alert variant="error" className="mb-6">{error}</Alert>}

      {/* Filters */}
      <div className="lio-card p-4 mb-6">
        <div className="flex flex-col md:flex-row gap-4 md:items-center">
          <div className="flex-1">
            <Input
              placeholder="Search by description or article number…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <span className="text-sm text-ink/45 md:w-40 md:text-right">
            {total === 0 ? 'No results' : `${from}–${to} of ${total.toLocaleString('en-US')}`}
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="lio-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-deep"></div>
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-ink/50">No articles found</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-ink-800/[0.03] border-b border-line">
                <tr>
                  {['Article', 'Description', 'Supplier', 'Unit price', 'Unit', 'Qty'].map((h) => (
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
                {items.map((a) => (
                  <tr key={a.id} className="hover:bg-ink-800/[0.02]">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-ink/70">
                      {a.article_number}
                    </td>
                    <td className="px-6 py-4 text-sm text-ink max-w-md">{a.description}</td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex px-2.5 py-1 text-xs font-medium rounded-full bg-accent-soft/30 text-accent-deep">
                        {a.supplier_name || '—'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink/80 tabular-nums">
                      {formatPrice(a.unit_price, a.currency)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink/60">{a.unit}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink/60 tabular-nums">
                      {formatQuantity(a.quantity)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {items.length > 0 && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-line">
            <span className="text-sm text-ink/45">
              Showing {from}–{to} of {total.toLocaleString('en-US')}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={!hasPrev}
                className="px-3.5 py-2 rounded-full text-sm font-medium border border-line text-ink/70 hover:bg-ink-800/[0.03] disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={!hasNext}
                className="px-3.5 py-2 rounded-full text-sm font-medium border border-line text-ink/70 hover:bg-ink-800/[0.03] disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
