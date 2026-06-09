import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Pagination } from './Pagination';

describe('Pagination', () => {
  it('renders nothing when total is 0', () => {
    const { container } = render(
      <Pagination page={1} pageSize={10} total={0} onPageChange={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the current range and total', () => {
    render(<Pagination page={2} pageSize={10} total={45} onPageChange={() => {}} itemLabel="stays" />);
    // page 2, size 10 -> 11–20 of 45
    expect(screen.getByText('11')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
    expect(screen.getByText('45')).toBeInTheDocument();
    expect(screen.getByText(/stays/)).toBeInTheDocument();
  });

  it('computes total pages and shows current page', () => {
    render(<Pagination page={1} pageSize={20} total={45} onPageChange={() => {}} />);
    // ceil(45/20) = 3 pages
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('disables Previous on the first page', () => {
    render(<Pagination page={1} pageSize={10} total={30} onPageChange={() => {}} />);
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /next/i })).toBeEnabled();
  });

  it('disables Next on the last page', () => {
    render(<Pagination page={3} pageSize={10} total={30} onPageChange={() => {}} />);
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
  });

  it('calls onPageChange with the next/previous page', async () => {
    const onPageChange = vi.fn();
    const user = userEvent.setup();
    render(<Pagination page={2} pageSize={10} total={50} onPageChange={onPageChange} />);

    await user.click(screen.getByRole('button', { name: /next/i }));
    expect(onPageChange).toHaveBeenCalledWith(3);

    await user.click(screen.getByRole('button', { name: /previous/i }));
    expect(onPageChange).toHaveBeenCalledWith(1);
  });

  it('caps the end at total on a partial last page', () => {
    render(<Pagination page={3} pageSize={10} total={25} onPageChange={() => {}} />);
    // 21–25 of 25: start is 21 (unique), and "25" appears for both end and
    // total — assert both occurrences are present.
    expect(screen.getByText('21')).toBeInTheDocument();
    expect(screen.getAllByText('25')).toHaveLength(2);
  });
});
