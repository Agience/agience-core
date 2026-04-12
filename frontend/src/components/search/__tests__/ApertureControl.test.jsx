// src/components/search/__tests__/ApertureControl.test.jsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import ApertureControl from '../ApertureControl';

describe('ApertureControl', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders slider with initial value', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toHaveValue('0.5');
    });

    it('shows current value and label', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      expect(screen.getByText('0.50 —')).toBeInTheDocument();
      expect(screen.getByText('Balanced')).toBeInTheDocument();
    });

    it('shows Narrow and Wide labels', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      expect(screen.getByText('Narrow')).toBeInTheDocument();
      expect(screen.getByText('Wide')).toBeInTheDocument();
    });

    it('renders preset stop buttons', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      // Preset stops: 0, 0.2, 0.5, 0.8, 1.0
      expect(screen.getByText('0.0')).toBeInTheDocument();
      expect(screen.getByText('0.2')).toBeInTheDocument();
      expect(screen.getByText('0.5')).toBeInTheDocument();
      expect(screen.getByText('0.8')).toBeInTheDocument();
      expect(screen.getByText('1.0')).toBeInTheDocument();
    });
  });

  describe('Label Mapping', () => {
    it('shows "None" label for value 0', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0} onChange={onChange} />);
      
      expect(screen.getByText('None')).toBeInTheDocument();
    });

    it('shows "Precise" label for value 0.1', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.1} onChange={onChange} />);
      
      expect(screen.getByText('Precise')).toBeInTheDocument();
    });

    it('shows "Focused" label for value 0.3', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.3} onChange={onChange} />);
      
      expect(screen.getByText('Focused')).toBeInTheDocument();
    });

    it('shows "Balanced" label for value 0.5', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      expect(screen.getByText('Balanced')).toBeInTheDocument();
    });

    it('shows "Wide" label for value 0.7', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.7} onChange={onChange} />);
      
      const labels = screen.getAllByText('Wide');
      expect(labels.length).toBeGreaterThan(0);
      expect(labels.some((el) => el.classList.contains('font-medium'))).toBe(true);
    });

    it('shows "Very Wide" label for value 1.0', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={1.0} onChange={onChange} />);
      
      expect(screen.getByText('Very Wide')).toBeInTheDocument();
    });
  });

  describe('Slider Interaction', () => {
    it('updates local value immediately when slider changes', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      const slider = screen.getByRole('slider');
      fireEvent.change(slider, { target: { value: '0.8' } });
      
      // Local value updates immediately
      expect(slider).toHaveValue('0.8');
    });

    it('debounces onChange callback when slider changes', async () => {
      vi.useFakeTimers();
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      const slider = screen.getByRole('slider');
      fireEvent.change(slider, { target: { value: '0.8' } });
      
      // onChange not called immediately (debounced)
      expect(onChange).not.toHaveBeenCalled();
      
      // Fast-forward debounce timer (250ms)
      vi.advanceTimersByTime(250);
      
      expect(onChange).toHaveBeenCalledWith(0.8);
      
      vi.useRealTimers();
    });

    it('debounces multiple rapid slider changes', async () => {
      vi.useFakeTimers();
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      const slider = screen.getByRole('slider');
      
      // Rapid changes
      fireEvent.change(slider, { target: { value: '0.6' } });
      vi.advanceTimersByTime(100);
      fireEvent.change(slider, { target: { value: '0.7' } });
      vi.advanceTimersByTime(100);
      fireEvent.change(slider, { target: { value: '0.8' } });
      
      // Only one onChange call after debounce
      vi.advanceTimersByTime(250);
      
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith(0.8);
      
      vi.useRealTimers();
    });
  });

  describe('Preset Stops', () => {
    it('sets value to preset when stop button clicked', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      // Click the 0.8 preset stop
      await user.click(screen.getByText('0.8'));
      
      // Should update immediately (no debounce for preset clicks)
      const slider = screen.getByRole('slider');
      expect(slider).toHaveValue('0.8');
    });

    it('highlights current preset stop', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      // Find the 0.5 stop button
      const stopButton = screen.getByText('0.5');
      
      // Should have highlighting classes (font-medium text-purple-700)
      expect(stopButton).toHaveClass('font-medium', 'text-purple-700');
    });

    it('does not highlight other preset stops', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      const stop02 = screen.getByText('0.2');
      const stop08 = screen.getByText('0.8');
      
      // Should not have highlighting classes
      expect(stop02).not.toHaveClass('font-medium');
      expect(stop08).not.toHaveClass('font-medium');
    });
  });

  describe('Show/Hide', () => {
    it('renders control when show=true', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} show={true} />);
      
      expect(screen.getByRole('slider')).toBeInTheDocument();
    });

    it('does not render control when show=false', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} show={false} />);
      
      expect(screen.queryByRole('slider')).not.toBeInTheDocument();
    });
  });

  describe('Value Sync', () => {
    it('updates local value when prop value changes', () => {
      const onChange = vi.fn();
      const { rerender } = render(<ApertureControl value={0.5} onChange={onChange} />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toHaveValue('0.5');
      
      // Parent updates value
      rerender(<ApertureControl value={0.7} onChange={onChange} />);
      
      expect(slider).toHaveValue('0.7');
    });
  });

  describe('Accessibility', () => {
    it('provides aria-pressed state for preset buttons', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      const stop05 = screen.getByText('0.5');
      const stop08 = screen.getByText('0.8');
      
      expect(stop05).toHaveAttribute('aria-pressed', 'true');
      expect(stop08).toHaveAttribute('aria-pressed', 'false');
    });

    it('provides title attributes for preset buttons', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.5} onChange={onChange} />);
      
      const stop05 = screen.getByText('0.5');
      expect(stop05).toHaveAttribute('title', 'Set to 0.50 — Balanced');
    });
  });

  describe('Edge Cases', () => {
    it('handles value 0.0 correctly', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.0} onChange={onChange} />);
      
      expect(screen.getByText('0.00 —')).toBeInTheDocument();
      expect(screen.getByText('None')).toBeInTheDocument();
    });

    it('handles value 1.0 correctly', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={1.0} onChange={onChange} />);
      
      expect(screen.getByText('1.00 —')).toBeInTheDocument();
      expect(screen.getByText('Very Wide')).toBeInTheDocument();
    });

    it('handles intermediate values between presets', () => {
      const onChange = vi.fn();
      render(<ApertureControl value={0.65} onChange={onChange} />);
      
      expect(screen.getByText('0.65 —')).toBeInTheDocument();
      const labels = screen.getAllByText('Wide');
      expect(labels.length).toBeGreaterThan(0);
      expect(labels.some((el) => el.classList.contains('font-medium'))).toBe(true);
    });

    it('cleans up debounce timer on unmount', () => {
      vi.useFakeTimers();
      const onChange = vi.fn();
      const { unmount } = render(<ApertureControl value={0.5} onChange={onChange} />);
      
      const slider = screen.getByRole('slider');
      fireEvent.change(slider, { target: { value: '0.8' } });
      
      // Unmount before debounce completes
      unmount();
      vi.advanceTimersByTime(250);
      
      // onChange should not be called after unmount
      expect(onChange).not.toHaveBeenCalled();
      
      vi.useRealTimers();
    });
  });
});
