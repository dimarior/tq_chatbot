"use client";

import { useSettingsStore } from "@/lib/settingsStore";

export function SettingsPanel() {
  const temperature = useSettingsStore((s) => s.temperature);
  const topK = useSettingsStore((s) => s.topK);
  const setTemperature = useSettingsStore((s) => s.setTemperature);
  const setTopK = useSettingsStore((s) => s.setTopK);

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-panel p-4 text-sm">
      <h3 className="font-semibold text-ink">Parametros</h3>

      <div className="flex flex-col gap-1">
        <label className="flex items-center justify-between text-muted">
          <span>Temperatura</span>
          <span className="font-mono text-ink">{temperature.toFixed(1)}</span>
        </label>
        <input
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={temperature}
          onChange={(e) => setTemperature(Number(e.target.value))}
          className="w-full accent-primary"
        />
        <div className="flex justify-between text-xs text-muted">
          <span>0.0</span>
          <span>1.0</span>
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label className="flex items-center justify-between text-muted">
          <span>Top K</span>
          <span className="font-mono text-ink">{topK}</span>
        </label>
        <input
          type="range"
          min={1}
          max={10}
          step={1}
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
          className="w-full accent-primary"
        />
        <div className="flex justify-between text-xs text-muted">
          <span>1</span>
          <span>10</span>
        </div>
      </div>
    </div>
  );
}
