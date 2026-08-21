// Component tests for the StayOS shell root page.
//
// Covers the shell's two views and the SSO handoff contract:
//   - Unauthenticated: renders the login form; invalid credentials surface a
//     visible error and the view does NOT switch to the grid.
//   - Successful login: flips in place to the feature grid (no redirect).
//   - Authenticated on mount (shared session already present): renders the grid
//     directly - the SSO entry case.
//   - The grid links LUMI -> /lumi/ and PULSE -> /pulse/ (the launcher targets).
// The Cognito boundary (signIn) and the shared session state (isAuthenticated /
// getCurrentUser) are mocked so no real network or storage is required.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { isAuthenticated, signIn, getCurrentUser } from '@/lib/auth';

// Mock the shared auth primitives the shell consumes.
vi.mock('@/lib/auth', () => ({
  isAuthenticated: vi.fn(),
  signIn: vi.fn(),
  signOut: vi.fn(),
  getCurrentUser: vi.fn(() => null),
}));

import ShellPage from '@/app/page';

const mockedIsAuthenticated = vi.mocked(isAuthenticated);
const mockedSignIn = vi.mocked(signIn);
const mockedGetCurrentUser = vi.mocked(getCurrentUser);

beforeEach(() => {
  vi.clearAllMocks();
  mockedGetCurrentUser.mockReturnValue(null);
});

afterEach(() => cleanup());

describe('StayOS shell - unauthenticated', () => {
  it('renders the login form when there is no session', async () => {
    mockedIsAuthenticated.mockReturnValue(false);
    render(<ShellPage />);
    expect(await screen.findByRole('button', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Email')).toBeInTheDocument();
  });

  it('shows a visible error and stays on login when credentials are invalid', async () => {
    mockedIsAuthenticated.mockReturnValue(false);
    mockedSignIn.mockRejectedValue(new Error('Incorrect username or password.'));

    render(<ShellPage />);
    fireEvent.change(await screen.findByPlaceholderText('Email'), {
      target: { value: 'gm@example.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('Password'), {
      target: { value: 'wrong' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Incorrect username or password.');
    });
    // Did not switch to the grid.
    expect(screen.queryByText('Available')).not.toBeInTheDocument();
  });

  it('flips to the feature grid after a successful login (no redirect)', async () => {
    mockedIsAuthenticated.mockReturnValue(false);
    mockedSignIn.mockResolvedValue({ accessToken: 'a', idToken: 'b', refreshToken: 'c' });
    mockedGetCurrentUser.mockReturnValue({
      email: 'gm@example.com',
      gmAlias: 'ALOHA-CHI-001',
      propertyId: 'chi-001',
    });

    render(<ShellPage />);
    fireEvent.change(await screen.findByPlaceholderText('Email'), {
      target: { value: 'gm@example.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('Password'), {
      target: { value: 'Password123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    // LUMI + PULSE launcher cards appear once authenticated.
    expect(await screen.findByRole('link', { name: 'LUMI' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'PULSE' })).toBeInTheDocument();
  });
});

describe('StayOS shell - authenticated on mount (SSO entry)', () => {
  it('renders the feature grid directly when a shared session already exists', async () => {
    mockedIsAuthenticated.mockReturnValue(true);
    mockedGetCurrentUser.mockReturnValue({
      email: 'gm@example.com',
      gmAlias: 'ALOHA-CHI-001',
      propertyId: 'chi-001',
    });

    render(<ShellPage />);

    // No login form; the launcher is shown with the correct targets.
    const lumi = await screen.findByRole('link', { name: 'LUMI' });
    const pulse = screen.getByRole('link', { name: 'PULSE' });
    expect(lumi).toHaveAttribute('href', '/lumi/');
    expect(pulse).toHaveAttribute('href', '/pulse/');
    expect(screen.queryByPlaceholderText('Email')).not.toBeInTheDocument();
  });
});
