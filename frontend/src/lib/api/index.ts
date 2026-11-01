'use client';

import { apiFetch, apiFetchObjectUrl, clearToken, setToken } from './client';
import type {
  CommodityGroup,
  OrganizationInvite,
  OrganizationMemberWithProfile,
  Profile,
  ProcurementRequestWithDetails,
} from '@/types/database';

export { ApiError, getToken, clearToken } from './client';

// ============================================================================
// Types
// ============================================================================

export interface AuthUser {
  id: string;
  email: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface MeResponse {
  user: AuthUser;
  profile: Profile;
}

export type MemberRole = 'admin' | 'buyer' | 'requester';

export interface MyOrganization {
  id: string;
  name: string;
  slug: string;
  role: MemberRole;
  created_at: string;
  updated_at: string;
}

// Request fields an org may optionally mark as required (see backend settings).
export type ConfigurableRequiredField = 'vat_id' | 'department';

export interface OrganizationSettings {
  required_fields: ConfigurableRequiredField[];
}

export interface MembersResponse {
  members: OrganizationMemberWithProfile[];
  invites: OrganizationInvite[];
}

export interface OrderLineInput {
  positionDescription: string;
  unitPrice: number;
  amount: number;
  unit: string;
  totalPrice: number;
}

export interface CreateRequestInput {
  requestorName: string;
  titleShortDescription: string;
  vendorName: string;
  vatId: string;
  commodityGroupId: number;
  totalCost: number;
  department: string;
  orderLines: OrderLineInput[];
}

export interface UpdateRequestInput {
  requestorName: string;
  title: string;
  vendorName: string;
  vatId: string;
  commodityGroupId: number;
  totalCost: number;
  department: string;
  orderLines: OrderLineInput[];
}

export interface ExtractedVendorData {
  title: string;
  vendorName: string;
  vatId: string;
  department: string;
  orderLines: OrderLineInput[];
  totalCost: number;
  commodityGroupId: number | null;
  commodityGroupName: string | null;
}

export interface ExtractionResponse {
  success: boolean;
  data?: ExtractedVendorData;
  error?: string;
  missingFields?: string[];
}

export interface Supplier {
  id: string;
  name: string;
  description: string | null;
  category: string | null;
  country: string | null;
  vat_id: string | null;
  website: string | null;
  email: string | null;
  created_at: string;
}

export interface Article {
  id: string;
  article_number: string;
  supplier_id: string;
  supplier_name: string | null;
  description: string;
  unit_price: string;
  currency: string;
  unit: string;
  quantity: string;
  created_at: string;
}

export interface ArticlePage {
  items: Article[];
  total: number;
  limit: number;
  offset: number;
}

// ============================================================================
// Auth
// ============================================================================

export const auth = {
  async signUp(params: { email: string; password: string; fullName: string }): Promise<TokenResponse> {
    const result = await apiFetch<TokenResponse>('/auth/signup', {
      body: { email: params.email, password: params.password, full_name: params.fullName },
    });
    setToken(result.access_token);
    return result;
  },

  async signIn(params: { email: string; password: string }): Promise<TokenResponse> {
    const result = await apiFetch<TokenResponse>('/auth/signin', { body: params });
    setToken(result.access_token);
    return result;
  },

  signOut(): void {
    clearToken();
  },

  me(): Promise<MeResponse> {
    return apiFetch<MeResponse>('/auth/me');
  },
};

// ============================================================================
// Requests
// ============================================================================

export interface RequestActivity {
  id: string;
  request_id: string;
  actor_id: string | null;
  action: 'created' | 'updated' | 'status_changed' | 'approved' | 'rejected' | 'document_attached';
  summary: string;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export const requests = {
  list(): Promise<ProcurementRequestWithDetails[]> {
    return apiFetch('/requests');
  },

  get(requestId: string): Promise<ProcurementRequestWithDetails> {
    return apiFetch(`/requests/${requestId}`);
  },

  getActivity(requestId: string): Promise<RequestActivity[]> {
    return apiFetch(`/requests/${requestId}/activity`);
  },

  uploadDocument(requestId: string, file: File): Promise<void> {
    const formData = new FormData();
    formData.append('file', file);
    return apiFetch(`/requests/${requestId}/document`, { method: 'PUT', formData });
  },

  /** Auth-fetched object URL for the stored PDF, or null if none attached. */
  documentUrl(requestId: string): Promise<string | null> {
    return apiFetchObjectUrl(`/requests/${requestId}/document`);
  },

  create(input: CreateRequestInput): Promise<ProcurementRequestWithDetails> {
    return apiFetch('/requests', { body: input });
  },

  update(requestId: string, input: UpdateRequestInput): Promise<ProcurementRequestWithDetails> {
    return apiFetch(`/requests/${requestId}`, { method: 'PUT', body: input });
  },

  updateStatus(
    requestId: string,
    status: 'open' | 'in_progress' | 'closed'
  ): Promise<ProcurementRequestWithDetails> {
    return apiFetch(`/requests/${requestId}/status`, { method: 'PATCH', body: { status } });
  },

  decideApproval(
    requestId: string,
    decision: 'approved' | 'rejected'
  ): Promise<ProcurementRequestWithDetails> {
    return apiFetch(`/requests/${requestId}/approval`, { method: 'PATCH', body: { decision } });
  },

  delete(requestId: string): Promise<void> {
    return apiFetch(`/requests/${requestId}`, { method: 'DELETE' });
  },
};

// ============================================================================
// Organizations
// ============================================================================

export const organizations = {
  create(params: { name: string; slug: string }): Promise<MyOrganization> {
    return apiFetch('/organizations', { body: params });
  },

  getMine(): Promise<MyOrganization> {
    return apiFetch('/organizations/me');
  },

  getMembers(): Promise<MembersResponse> {
    return apiFetch('/organizations/me/members');
  },

  invite(email: string, role: MemberRole = 'requester'): Promise<OrganizationInvite> {
    return apiFetch('/organizations/me/invites', { body: { email, role } });
  },

  cancelInvite(inviteId: string): Promise<void> {
    return apiFetch(`/organizations/me/invites/${inviteId}`, { method: 'DELETE' });
  },

  acceptInvite(token: string): Promise<MyOrganization> {
    return apiFetch('/organizations/invites/accept', { body: { token } });
  },

  getSettings(): Promise<OrganizationSettings> {
    return apiFetch('/organizations/me/settings');
  },

  updateSettings(settings: OrganizationSettings): Promise<OrganizationSettings> {
    return apiFetch('/organizations/me/settings', { method: 'PATCH', body: settings });
  },
};

// ============================================================================
// Commodity groups
// ============================================================================

export const commodityGroups = {
  list(): Promise<CommodityGroup[]> {
    return apiFetch('/commodity-groups');
  },
};

// ============================================================================
// Suppliers
// ============================================================================

export const suppliers = {
  list(params?: { search?: string; category?: string }): Promise<Supplier[]> {
    const qs = new URLSearchParams();
    if (params?.search) qs.set('search', params.search);
    if (params?.category) qs.set('category', params.category);
    qs.set('limit', '500');
    return apiFetch(`/suppliers?${qs.toString()}`);
  },

  count(): Promise<{ count: number }> {
    return apiFetch('/suppliers/count');
  },
};

// ============================================================================
// Articles
// ============================================================================

export const articles = {
  list(params?: {
    search?: string;
    supplierId?: string;
    limit?: number;
    offset?: number;
  }): Promise<ArticlePage> {
    const qs = new URLSearchParams();
    if (params?.search) qs.set('search', params.search);
    if (params?.supplierId) qs.set('supplier_id', params.supplierId);
    qs.set('limit', String(params?.limit ?? 25));
    qs.set('offset', String(params?.offset ?? 0));
    return apiFetch(`/articles?${qs.toString()}`);
  },

  count(): Promise<{ count: number }> {
    return apiFetch('/articles/count');
  },
};

// ============================================================================
// PDF + extraction
// ============================================================================

export const pdf = {
  parse(file: File): Promise<{ text: string }> {
    const formData = new FormData();
    formData.append('file', file);
    return apiFetch('/pdf/parse', { formData });
  },
};

export const extraction = {
  extract(text: string): Promise<ExtractionResponse> {
    return apiFetch('/extraction', { body: { text } });
  },
};
