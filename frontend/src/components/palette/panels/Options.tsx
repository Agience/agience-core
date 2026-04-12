import { usePalette } from "../../../hooks/usePalette";

interface ConfigItem {
  id: string;
  name?: string;
  description?: string;
}

const configOptions: ConfigItem[] = [
  { id: 'options-1', name: 'Option One', description: 'Description for Option One' },
  { id: 'options-2', name: 'Option Two', description: 'Description for Option Two' },
  { id: 'options-3', name: 'Option Three', description: 'Description for Option Three' },
  { id: 'options-4', name: 'Option Four', description: 'Description for Option Four' },
  { id: 'options-5', name: 'Option Five', description: 'Description for Option Five' },
  { id: 'options-6', name: 'Option Six', description: 'Description for Option Six' }
];

export default function OptionsPanel() {
  const { state, updatePanelData } = usePalette();
  const panelState = state.panelData.options;

  const toggleConfig = (id: string) => {
    updatePanelData("options", (prev) => {
      const newConfig = { ...prev.config };
      if (newConfig[id]) {
        delete newConfig[id];
      } else {
        newConfig[id] = true;
      }
      return { ...prev, config: newConfig };
    });
  };

  const renderOption = (option: ConfigItem) => (
    <div
      key={option.id}
      className="flex justify-between items-center px-2 py-1 hover:bg-gray-100 rounded"
    >
      <span className="truncate">{option.name}</span>
      <label className="relative inline-flex items-center cursor-pointer">
        <input
          type="checkbox"
          className="sr-only peer"
          checked={!!panelState.config[option.id]}
          onChange={() => toggleConfig(option.id)}
        />
        <div className="w-8 h-5 bg-gray-200 peer-checked:bg-blue-500 rounded-full transition-all duration-100" />
        <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow transform peer-checked:translate-x-3 transition-transform duration-100" />
      </label>
    </div>
  );

  const half = Math.ceil(configOptions.length / 2);

  return (
    <div className="flex mb-2">
      <div className="w-1/2">
        <div className="max-h-40 overflow-y-auto">
          {configOptions.slice(0, half).map(renderOption)}
        </div>
      </div>
      <div className="w-1/2">
        <div className="max-h-40 overflow-y-auto">
          {configOptions.slice(half).map(renderOption)}
        </div>
      </div>
    </div>
  );
}
