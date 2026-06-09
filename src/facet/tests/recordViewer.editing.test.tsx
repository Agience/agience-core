import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

const updateArtifact = vi.fn(() => Promise.resolve());

vi.mock('../src/hooks/useWorkspaces', () => ({
  useWorkspaces: () => ({ activeWorkspaceId: 'ws-1' }),
}));

vi.mock('../src/hooks/useWorkspace', () => {
  return {
    useWorkspace: () => ({
      artifacts: [
        {
          id: 'org-1',
          state: 'draft',
          context: JSON.stringify({
            content_type: 'application/vnd.agience.organization+json',
            identity: {
              display_name: 'Acme Labs',
              legal_name: 'Acme Labs LLC',
              entity_kind: 'company',
              jurisdiction: 'DE',
              website_uri: 'https://acme.example',
            },
            licensing: {
              employee_count: 8,
              annual_gross_revenue_usd: 750000,
              packaging: { hosted_service: false },
            },
            relationships: {
              affiliate_organization_ids: ['org-2'],
            },
          }),
          content: 'Operator profile',
        },
      ],
      displayedArtifacts: [],
      updateArtifact,
    }),
  };
});

import RecordViewer from '../src/content-types/_record/viewer';

describe('RecordViewer editing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('edits an organization record and persists context', async () => {
    const artifact = {
      id: 'org-1',
      state: 'draft',
      context: JSON.stringify({
        content_type: 'application/vnd.agience.organization+json',
        identity: {
          display_name: 'Acme Labs',
          legal_name: 'Acme Labs LLC',
          entity_kind: 'company',
          jurisdiction: 'DE',
          website_uri: 'https://acme.example',
        },
        licensing: {
          employee_count: 8,
          annual_gross_revenue_usd: 750000,
          packaging: { hosted_service: false },
        },
        relationships: {
          affiliate_organization_ids: ['org-2'],
        },
      }),
      content: 'Operator profile',
      collection_ids: [],
    };

    render(<RecordViewer artifact={artifact} />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    fireEvent.change(screen.getByLabelText('Title'), {
      target: { value: 'Acme Research' },
    });
    fireEvent.change(screen.getByLabelText('Employees'), {
      target: { value: '9' },
    });
    fireEvent.change(screen.getByLabelText('Affiliates'), {
      target: { value: 'org-2\norg-3' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(updateArtifact).toHaveBeenCalledTimes(1);
    });

    expect(updateArtifact).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'org-1',
        context: expect.any(String),
      })
    );

    const payload = JSON.parse(updateArtifact.mock.calls[0][0].context);
    expect(payload.identity.display_name).toBe('Acme Research');
    expect(payload.licensing.employee_count).toBe(9);
    expect(payload.relationships.affiliate_organization_ids).toEqual(['org-2', 'org-3']);
  });
});