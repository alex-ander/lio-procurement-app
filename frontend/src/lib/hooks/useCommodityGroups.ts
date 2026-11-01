'use client';

import { useQuery } from '@tanstack/react-query';
import { commodityGroups } from '@/lib/api';
import type { CommodityGroup } from '@/types/database';

/**
 * React Query hook to fetch commodity groups with caching
 * Data is cached for 5 minutes to avoid unnecessary backend calls
 */
export function useCommodityGroups() {
  return useQuery<CommodityGroup[]>({
    queryKey: ['commodity-groups'],
    queryFn: () => commodityGroups.list(),
    staleTime: 5 * 60 * 1000, // 5 minutes - commodity groups rarely change
    gcTime: 10 * 60 * 1000, // 10 minutes cache time
  });
}

/**
 * Helper hook to get a specific commodity group by ID
 */
export function useCommodityGroup(id: number | null | undefined) {
  const { data: groups } = useCommodityGroups();

  if (!id || !groups) return null;

  return groups.find((g) => g.id === id) || null;
}
