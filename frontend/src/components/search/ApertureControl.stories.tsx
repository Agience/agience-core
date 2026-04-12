// frontend/src/components/search/ApertureControl.stories.tsx
// Storybook stories for ApertureControl component (if Storybook is set up)

import { useState } from 'react';
import ApertureControl from './ApertureControl';

export default {
  title: 'Search/ApertureControl',
  component: ApertureControl,
};

export const Default = () => {
  const [value, setValue] = useState(0.5);
  
  return (
    <div className="p-8 max-w-xl">
      <h1 className="text-2xl font-bold mb-4">Aperture Control - Full Mode</h1>
      <ApertureControl value={value} onChange={setValue} show={true} />
      
      <div className="mt-6 p-4 bg-gray-100 rounded">
        <p className="text-sm font-mono">Current value: {value.toFixed(2)}</p>
        <p className="text-sm text-gray-600 mt-2">
          This would filter search results to {Math.round(value * 100)}% threshold
        </p>
      </div>
    </div>
  );
};

export const Compact = () => {
  const [value, setValue] = useState(0.5);
  
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">Aperture Control - Compact Mode</h1>
      <div className="flex items-center gap-4 p-4 bg-white border rounded">
        <span className="text-sm text-gray-600">Search controls:</span>
        <ApertureControl value={value} onChange={setValue} show={true} />
      </div>
      
      <div className="mt-6 p-4 bg-gray-100 rounded">
        <p className="text-sm font-mono">Current value: {value.toFixed(2)}</p>
      </div>
    </div>
  );
};

export const PresetInteraction = () => {
  const [value, setValue] = useState(0.5);
  const [resultCount, setResultCount] = useState(7);
  
  // Simulate result count changes based on aperture
  const handleChange = (newValue: number) => {
    setValue(newValue);
    
    // Simulate: lower aperture = fewer results
    if (newValue <= 0.2) setResultCount(5);
    else if (newValue <= 0.4) setResultCount(6);
    else if (newValue <= 0.6) setResultCount(7);
    else if (newValue <= 0.8) setResultCount(8);
    else setResultCount(9);
  };
  
  return (
    <div className="p-8 max-w-xl">
      <h1 className="text-2xl font-bold mb-4">Interactive Demo</h1>
      
      <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded">
        <p className="text-sm font-medium">Search: "grocery"</p>
        <p className="text-lg font-bold text-blue-700">{resultCount} results</p>
      </div>
      
      <ApertureControl value={value} onChange={handleChange} show={true} />
      
      <div className="mt-6 space-y-2">
        <div className="p-3 bg-white border rounded text-sm">
          <span className="font-medium">Weekly Grocery List</span>
          <span className="text-gray-500 ml-2">Score: 0.0323</span>
        </div>
        <div className="p-3 bg-white border rounded text-sm">
          <span className="font-medium">Store Locations</span>
          <span className="text-gray-500 ml-2">Score: 0.0323</span>
        </div>
        <div className="p-3 bg-white border rounded text-sm">
          <span className="font-medium">Budget for Groceries</span>
          <span className="text-gray-500 ml-2">Score: 0.0308</span>
        </div>
        {resultCount >= 6 && (
          <div className="p-3 bg-white border rounded text-sm">
            <span className="font-medium">Meal Planning</span>
            <span className="text-gray-500 ml-2">Score: 0.0295</span>
          </div>
        )}
        {resultCount >= 7 && (
          <div className="p-3 bg-white border rounded text-sm">
            <span className="font-medium">Recipe: Vegetable Soup</span>
            <span className="text-gray-500 ml-2">Score: 0.0244</span>
          </div>
        )}
        {resultCount >= 8 && (
          <div className="p-3 bg-white border rounded text-sm opacity-60">
            <span className="font-medium">Food Storage Tips</span>
            <span className="text-gray-500 ml-2">Score: 0.0156</span>
          </div>
        )}
        {resultCount >= 9 && (
          <div className="p-3 bg-white border rounded text-sm opacity-40">
            <span className="font-medium">(untitled)</span>
            <span className="text-gray-500 ml-2">Score: 0.0154</span>
          </div>
        )}
      </div>
    </div>
  );
};
