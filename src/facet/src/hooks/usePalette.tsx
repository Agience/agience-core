import { useContext } from "react";
import { PaletteContext } from "../context/palette/PaletteContext";

export const usePalette = () => {
  const context = useContext(PaletteContext);
  if (!context) throw new Error('usePalette must be used within a PaletteProvider');
  return context;
};