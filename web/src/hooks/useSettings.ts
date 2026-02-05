import { useCallback, useEffect, useState } from "react";
import { fetchSettings, updateSettings as apiUpdateSettings, resetSetting } from "../api";
import type { Settings } from "../types";

export function useSettings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetchSettings()
      .then((data) => { setSettings(data); setError(null); })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const update = useCallback(async (updates: Partial<Settings>): Promise<boolean> => {
    try {
      const updated = await apiUpdateSettings(updates);
      setSettings(updated);
      setError(null);
      return true;
    } catch (err: any) {
      setError(err.message);
      return false;
    }
  }, []);

  const reset = useCallback(async (key: string) => {
    try {
      await resetSetting(key);
      load(); // Reload all settings after reset
    } catch (err: any) {
      setError(err.message);
    }
  }, [load]);

  return { settings, loading, error, update, reset, reload: load };
}
