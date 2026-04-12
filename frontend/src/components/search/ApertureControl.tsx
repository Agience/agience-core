// frontend/src/components/search/ApertureControl.tsx
import { useState, useEffect, useRef } from 'react';

interface ApertureControlProps {
  /** Current aperture value (0.0 - 1.0) */
  value: number;
  /** Callback when value changes */
  onChange: (value: number) => void;
  /** Show/hide control */
  show?: boolean;
}

export default function ApertureControl({
  value,
  onChange,
  show = true,
}: ApertureControlProps) {
  const [localValue, setLocalValue] = useState(value);
  
  useEffect(() => {
    setLocalValue(value);
  }, [value]);
  
  const debounceRef = useRef<number | null>(null);
  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);
  const handleChange = (newValue: number) => {
    // Update UI immediately
    setLocalValue(newValue);

    // Debounce onChange calls to avoid rapid-fire updates while dragging
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(() => {
      onChange(newValue);
      debounceRef.current = null;
    }, 250);
  };
  
  // No inline preset stops here; top numberline is clickable per UX

  const getLabel = (v = localValue) => {
    // 0 means 'None' (no results)
    if (v === 0) return 'None';
    if (v <= 0.2) return 'Precise';
    if (v <= 0.4) return 'Focused';
    if (v <= 0.6) return 'Balanced';
    if (v <= 0.8) return 'Wide';
    return 'Very Wide';
  };
  
  if (!show) return null;
  
  return (
    <div className="space-y-3">
      {/* Slider with labels */}
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500 w-12">Narrow</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={localValue}
            onChange={(e) => handleChange(parseFloat(e.target.value))}
            className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-purple-600"
          />
          <span className="text-xs text-gray-500 w-12 text-right">Wide</span>
        </div>
        <div className="flex justify-between text-[10px] text-gray-400 px-12">
          {([0, 0.2, 0.5, 0.8, 1] as number[]).map((v) => (
            <button
              key={v}
              onClick={() => handleChange(v)}
              className={`w-10 text-[10px] text-gray-400 text-left focus:outline-none ${Math.abs(localValue - v) < 0.01 ? 'font-medium text-purple-700' : ''}`}
              aria-pressed={Math.abs(localValue - v) < 0.01}
              title={`Set to ${v.toFixed(2)} — ${getLabel(v)}`}
            >
              {v.toFixed(1)}
            </button>
          ))}
        </div>
        <div className="text-center text-xs text-gray-600">
          {localValue.toFixed(2)} — <span className="font-medium">{getLabel()}</span>
        </div>

        {/* Note: clickable stops moved to the top numberline above per UX request */}
      </div>
      
      {/* Preset buttons removed — use clickable stops above or drag the slider. */}
    </div>
  );
}
