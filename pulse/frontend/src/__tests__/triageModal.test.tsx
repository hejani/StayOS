// UI tests for Task 21.7 - approval success/failure (Requirement 15.8).
//
// TriageModal submits the selected option to POST /alerts/{id}/approvals. On a
// successful response it shows the confirmation indicator; on a failed request it
// shows the error indicator and retains the unapproved state (the approve control
// remains available). Both the detail fetch and the approval POST go through
// authFetch, which is mocked so no network is hit.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { authFetch } from '@/lib/api';
import { makeAlert } from './alertFixtures';
import type { Alert } from '@/lib/types';

// Mock the authenticated fetch wrapper (both the detail GET and approval POST).
vi.mock('@/lib/api', () => ({
  authFetch: vi.fn(),
}));

import TriageModal from '@/components/TriageModal';

const mockedAuthFetch = vi.mocked(authFetch);

// A feed alert with a triage brief carrying one recommended ranked option.
function briefedAlert(): Alert {
  return makeAlert({
    alertId: 'brief-1',
    tier: 'CRITICAL',
    status: 'UNACKNOWLEDGED',
    title: 'Complaint escalation',
    triageBrief: {
      summary: 'Guest complaint requires a service-recovery decision.',
      confidence: 76,
      options: [
        {
          label: 'A',
          rank: 1,
          title: 'Offer a suite upgrade',
          detail: 'Move the guest to a suite and comp one night.',
          recommended: true,
        },
      ],
    },
  });
}

beforeEach(() => {
  mockedAuthFetch.mockReset();
});

describe('TriageModal approval outcomes (Requirement 15.8)', () => {
  it('shows the confirmation indicator on a successful approval', async () => {
    const alert = briefedAlert();
    mockedAuthFetch.mockImplementation(async (path: string) => {
      if (path.includes('/approvals')) {
        return { accepted: true, approvalState: 'APPROVED', executed: true } as never;
      }
      // Detail fetch (GET /alerts/{id}).
      return { alert } as never;
    });

    const onActionComplete = vi.fn();
    render(<TriageModal alert={alert} onClose={vi.fn()} onActionComplete={onActionComplete} />);

    // Wait for the brief to load (ranked option visible), then approve.
    await screen.findByText('Offer a suite upgrade');
    fireEvent.click(screen.getByRole('button', { name: /Approve selected option/ }));

    // Confirmation indicator appears and the feed refetch is triggered.
    await screen.findByText('Approved. The action has been authorized.');
    expect(onActionComplete).toHaveBeenCalledTimes(1);
  });

  it('shows the error indicator and retains the unapproved state on a failed approval', async () => {
    const alert = briefedAlert();
    mockedAuthFetch.mockImplementation(async (path: string) => {
      if (path.includes('/approvals')) {
        throw new Error('The approval was not recorded.');
      }
      return { alert } as never;
    });

    const onActionComplete = vi.fn();
    render(<TriageModal alert={alert} onClose={vi.fn()} onActionComplete={onActionComplete} />);

    await screen.findByText('Offer a suite upgrade');
    fireEvent.click(screen.getByRole('button', { name: /Approve selected option/ }));

    // Error indicator is shown...
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('The approval was not recorded.');
    });
    // ...the unapproved state is retained (no confirmation, approve control still present)...
    expect(screen.queryByText('Approved. The action has been authorized.')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Approve selected option/ })).toBeInTheDocument();
    // ...and no feed refetch happened because nothing was approved.
    expect(onActionComplete).not.toHaveBeenCalled();
  });
});
