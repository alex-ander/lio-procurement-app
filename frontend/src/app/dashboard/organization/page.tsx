'use client';

import { useState, useEffect } from 'react';
import * as api from '@/lib/api';
import { useCommodityGroups } from '@/lib/hooks/useCommodityGroups';
import { Button, Input, Alert, TextArea } from '@/components/base';
import type { OrganizationMemberWithProfile, OrganizationInvite } from '@/types/database';

type Tab = 'members' | 'settings';

const ROLE_BADGES: Record<string, string> = {
  admin: 'bg-ink text-white',
  buyer: 'bg-accent-soft/40 text-accent-deep',
  requester: 'bg-ink-800/[0.06] text-ink/70',
};

export default function OrganizationPage() {
  const { data: commodityGroups } = useCommodityGroups();
  const [tab, setTab] = useState<Tab>('members');
  const [members, setMembers] = useState<OrganizationMemberWithProfile[]>([]);
  const [invites, setInvites] = useState<OrganizationInvite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<api.MemberRole>('requester');
  const [inviting, setInviting] = useState(false);
  const [organizationName, setOrganizationName] = useState<string>('');
  const [role, setRole] = useState<api.MemberRole | null>(null);
  const [requiredFields, setRequiredFields] = useState<api.ConfigurableRequiredField[]>([]);
  const [accountingGuidelines, setAccountingGuidelines] = useState('');
  const [commodityRules, setCommodityRules] = useState<api.CommodityClassificationRule[]>([]);
  const [newRulePattern, setNewRulePattern] = useState('');
  const [newRuleGroupId, setNewRuleGroupId] = useState<number | ''>('');
  const [savingSettings, setSavingSettings] = useState(false);

  useEffect(() => {
    loadOrganization();
  }, []);

  const loadOrganization = async () => {
    setLoading(true);
    setError('');

    try {
      const org = await api.organizations.getMine();
      setOrganizationName(org.name);
      setRole(org.role);

      const [result, settings] = await Promise.all([
        api.organizations.getMembers(),
        api.organizations.getSettings(),
      ]);
      setMembers(result.members);
      setInvites(result.invites);
      setRequiredFields(settings.required_fields);
      setAccountingGuidelines(settings.accounting_guidelines || '');
      setCommodityRules(settings.commodity_rules || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load organization');
    }

    setLoading(false);
  };

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setInviting(true);

    if (!inviteEmail || !inviteEmail.includes('@')) {
      setError('Please enter a valid email address');
      setInviting(false);
      return;
    }

    try {
      await api.organizations.invite(inviteEmail, inviteRole);
      setSuccess(`Invitation sent to ${inviteEmail}`);
      setInviteEmail('');
      await loadOrganization(); // Reload to show new invite
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send invitation');
    }

    setInviting(false);
  };

  const handleCancelInvite = async (inviteId: string) => {
    try {
      await api.organizations.cancelInvite(inviteId);
      setSuccess('Invitation cancelled');
      await loadOrganization();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel invitation');
    }
  };

  const REQUIRABLE_FIELDS: { key: api.ConfigurableRequiredField; label: string }[] = [
    { key: 'vat_id', label: 'Tax ID' },
    { key: 'department', label: 'Department' },
  ];

  const toggleRequiredField = async (field: api.ConfigurableRequiredField) => {
    const next = requiredFields.includes(field)
      ? requiredFields.filter((f) => f !== field)
      : [...requiredFields, field];
    setRequiredFields(next);
    setSavingSettings(true);
    setError('');
    setSuccess('');
    try {
      const saved = await api.organizations.updateSettings({ required_fields: next });
      setRequiredFields(saved.required_fields);
      setSuccess('Settings updated');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update settings');
      await loadOrganization(); // revert to server state
    }
    setSavingSettings(false);
  };

  const saveAccountingSettings = async (
    nextGuidelines: string,
    nextRules: api.CommodityClassificationRule[]
  ) => {
    setSavingSettings(true);
    setError('');
    setSuccess('');
    try {
      const saved = await api.organizations.updateSettings({
        required_fields: requiredFields,
        accounting_guidelines: nextGuidelines,
        commodity_rules: nextRules,
      });
      setRequiredFields(saved.required_fields);
      setAccountingGuidelines(saved.accounting_guidelines || '');
      setCommodityRules(saved.commodity_rules || []);
      setSuccess('Accounting classification rules updated');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update settings');
      await loadOrganization();
    }
    setSavingSettings(false);
  };

  const handleAddCommodityRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRulePattern.trim() || !newRuleGroupId) {
      setError('Please enter an item/condition description and select a target commodity group');
      return;
    }
    const nextRules = [
      ...commodityRules,
      {
        pattern: newRulePattern.trim(),
        commodity_group_id: Number(newRuleGroupId),
      },
    ];
    setCommodityRules(nextRules);
    setNewRulePattern('');
    setNewRuleGroupId('');
    await saveAccountingSettings(accountingGuidelines, nextRules);
  };

  const handleRemoveCommodityRule = async (index: number) => {
    const nextRules = commodityRules.filter((_, idx) => idx !== index);
    setCommodityRules(nextRules);
    await saveAccountingSettings(accountingGuidelines, nextRules);
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-deep"></div>
        </div>
      </div>
    );
  }

  // The whole page is for admins (the nav only shows it to them, but guard anyway).
  if (role !== null && role !== 'admin') {
    return (
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert variant="info">
          Only organization admins can manage members and settings.
        </Alert>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">{organizationName}</h1>
        <p className="text-ink/55 mt-1.5">
          Manage your organization&apos;s members and settings
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {(
          [
            { key: 'members', label: 'Members' },
            { key: 'settings', label: 'Settings' },
          ] as { key: Tab; label: string }[]
        ).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              tab === t.key
                ? 'bg-ink text-white'
                : 'bg-white border border-line text-ink/70 hover:bg-ink-800/[0.03]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <Alert variant="error" className="mb-6">{error}</Alert>}
      {success && <Alert variant="success" className="mb-6">{success}</Alert>}

      {tab === 'members' && (
        <>
          {/* Invite Form */}
          <div className="lio-card p-6 mb-6">
            <h2 className="text-xl font-semibold tracking-tight text-ink mb-1">Invite New Member</h2>
            <p className="text-sm text-ink/50 mb-4">
              Invites are tracked in the app — no emails are sent.
            </p>
            <form onSubmit={handleInvite} className="flex flex-col sm:flex-row gap-3">
              <Input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="colleague@example.com"
                className="flex-1"
                disabled={inviting}
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as api.MemberRole)}
                disabled={inviting}
                className="h-11 px-3.5 border border-line rounded-xl text-sm text-ink bg-white focus:outline-none focus:ring-2 focus:ring-accent-deep/60"
              >
                <option value="requester">Requester</option>
                <option value="buyer">Buyer</option>
                <option value="admin">Admin</option>
              </select>
              <Button type="submit" loading={inviting} disabled={inviting} className="min-w-[140px]">
                Send Invite
              </Button>
            </form>
          </div>

          {/* Current Members */}
          <div className="lio-card overflow-hidden mb-6">
            <div className="p-6 border-b border-line">
              <h2 className="text-xl font-semibold tracking-tight text-ink">
                Members ({members.length})
              </h2>
            </div>
            <div className="divide-y divide-line">
              {members.length === 0 ? (
                <div className="p-6 text-center text-ink/50">No members found</div>
              ) : (
                members.map((member) => (
                  <div key={member.id} className="p-6 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-ink">
                        {member.profiles?.full_name || 'Unknown User'}
                      </p>
                      <p className="text-sm text-ink/50">{member.profiles?.email}</p>
                    </div>
                    <span
                      className={`inline-flex px-3 py-1 text-xs font-semibold rounded-full ${
                        ROLE_BADGES[member.role] || ROLE_BADGES.requester
                      }`}
                    >
                      {member.role}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Pending Invites */}
          {invites.length > 0 && (
            <div className="lio-card overflow-hidden">
              <div className="p-6 border-b border-line">
                <h2 className="text-xl font-semibold tracking-tight text-ink">
                  Pending Invites ({invites.length})
                </h2>
              </div>
              <div className="divide-y divide-line">
                {invites.map((invite) => (
                  <div key={invite.id} className="p-6 flex items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-ink">{invite.email}</p>
                      <p className="text-sm text-ink/50">
                        Invited {new Date(invite.created_at).toLocaleDateString('en-US')} · as {invite.role}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleCancelInvite(invite.id)}
                    >
                      Cancel
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'settings' && (
        <div className="space-y-6">
          <div className="lio-card p-6">
            <h2 className="text-xl font-semibold tracking-tight text-ink">Request Settings</h2>
            <p className="text-sm text-ink/55 mt-1 mb-4">
              Choose which optional fields are required when creating a request.
            </p>
            <div className="space-y-2">
              {REQUIRABLE_FIELDS.map((field) => {
                const checked = requiredFields.includes(field.key);
                return (
                  <label
                    key={field.key}
                    className="flex items-center gap-3 rounded-xl border border-line px-4 py-3 cursor-pointer hover:bg-ink-800/[0.02]"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={savingSettings}
                      onChange={() => toggleRequiredField(field.key)}
                      className="h-4 w-4 accent-accent-deep"
                    />
                    <span className="text-sm text-ink">Require {field.label}</span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="lio-card p-6 space-y-6">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-ink">
                Commodity Group Accounting Rules
              </h2>
              <p className="text-sm text-ink/55 mt-1">
                Configure organization-specific accounting rules for AI commodity group classification.
                The system also automatically learns from your organization&apos;s past bookings and manual commodity group corrections.
              </p>
            </div>

            <div className="space-y-3">
              <TextArea
                label="Accounting Policy / Guidelines"
                value={accountingGuidelines}
                onChange={(e) => setAccountingGuidelines(e.target.value)}
                rows={3}
                placeholder="e.g., Cable ties always have to be booked under Electrical Engineering, printer toner under IT Hardware, and small software subscriptions under Office Supplies."
              />
              <div className="flex justify-end">
                <Button
                  type="button"
                  size="sm"
                  loading={savingSettings}
                  disabled={savingSettings}
                  onClick={() => saveAccountingSettings(accountingGuidelines, commodityRules)}
                >
                  Save Guidelines
                </Button>
              </div>
            </div>

            <div className="border-t border-line pt-5 space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-ink">Custom Item-to-Commodity Group Mappings</h3>
                <p className="text-xs text-ink/55 mt-0.5">
                  Map specific items or conditions directly to a target commodity group.
                </p>
              </div>

              {commodityRules.length > 0 && (
                <div className="divide-y divide-line rounded-xl border border-line overflow-hidden">
                  {commodityRules.map((rule, idx) => {
                    const matchedGroup = commodityGroups?.find((g) => g.id === rule.commodity_group_id);
                    return (
                      <div key={idx} className="px-4 py-3 flex items-center justify-between gap-4 bg-white">
                        <div className="min-w-0 text-sm">
                          <span className="font-medium text-ink">&ldquo;{rule.pattern}&rdquo;</span>
                          <span className="mx-2 text-ink/40">&rarr;</span>
                          <span className="text-ink/80">
                            {matchedGroup
                              ? `${matchedGroup.id} · ${matchedGroup.category} · ${matchedGroup.name}`
                              : `${rule.commodity_group_id} · ${rule.commodity_group_name || ''}`}
                          </span>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={savingSettings}
                          onClick={() => handleRemoveCommodityRule(idx)}
                        >
                          Remove
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}

              <form onSubmit={handleAddCommodityRule} className="flex flex-col sm:flex-row gap-3">
                <Input
                  value={newRulePattern}
                  onChange={(e) => setNewRulePattern(e.target.value)}
                  placeholder="Item or condition (e.g., Cable ties, Printer toner, Small software subscriptions)"
                  className="flex-1"
                  disabled={savingSettings}
                />
                <select
                  value={newRuleGroupId}
                  onChange={(e) => setNewRuleGroupId(e.target.value ? Number(e.target.value) : '')}
                  disabled={savingSettings}
                  className="h-11 px-3.5 border border-line rounded-xl text-sm text-ink bg-white focus:outline-none focus:ring-2 focus:ring-accent-deep/60 sm:max-w-xs"
                >
                  <option value="">Select commodity group...</option>
                  {commodityGroups?.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.id} - {g.category} - {g.name}
                    </option>
                  ))}
                </select>
                <Button type="submit" variant="outline" disabled={savingSettings} className="shrink-0">
                  + Add Rule
                </Button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
