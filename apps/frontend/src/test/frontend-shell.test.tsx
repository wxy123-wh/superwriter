import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

import { FrontendShell } from '../routes/FrontendShell';

describe('FrontendShell', () => {
  it('renders the baseline readiness copy', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <FrontendShell />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'React workspace is ready for route migration.' })).toBeInTheDocument();
    expect(screen.getByText('Superwriter frontend baseline')).toBeInTheDocument();
  });
});
