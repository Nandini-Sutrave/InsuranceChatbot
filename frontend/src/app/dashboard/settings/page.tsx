"use client";

import { Save, Settings } from "lucide-react";
import { useEffect, useState } from "react";

export default function SettingsPage() {
  const [model, setModel] = useState("gemini-1.5-flash");
  const [temperature, setTemperature] = useState("0.0");
  const [maxTokens, setMaxTokens] = useState("2048");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setModel(localStorage.getItem("settings.model") || "gemini-1.5-flash");
    setTemperature(localStorage.getItem("settings.temperature") || "0.0");
    setMaxTokens(localStorage.getItem("settings.maxTokens") || "2048");
  }, []);

  const save = () => {
    localStorage.setItem("settings.model", model);
    localStorage.setItem("settings.temperature", temperature);
    localStorage.setItem("settings.maxTokens", maxTokens);
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  };

  return (
    <div className="h-full overflow-y-auto p-6 lg:p-8">
      <div className="mx-auto max-w-3xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="mt-2 text-sm text-muted-foreground">Workspace preferences for the Insurance AI client.</p>
        </div>
        <section className="surface p-5">
          <div className="mb-5 flex items-center gap-2"><Settings className="h-5 w-5 text-primary" /><h2 className="font-semibold">Runtime configuration</h2></div>
          <div className="grid gap-4">
            <label className="text-sm font-medium">Model<input className="control mt-1 w-full" value={model} onChange={(e) => setModel(e.target.value)} /></label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-sm font-medium">Temperature<input className="control mt-1 w-full" value={temperature} onChange={(e) => setTemperature(e.target.value)} /></label>
              <label className="text-sm font-medium">Max Tokens<input className="control mt-1 w-full" value={maxTokens} onChange={(e) => setMaxTokens(e.target.value)} /></label>
            </div>
            <button className="btn-primary w-fit" onClick={save}><Save className="h-4 w-4" />{saved ? "Saved" : "Save preferences"}</button>
          </div>
        </section>
      </div>
    </div>
  );
}
