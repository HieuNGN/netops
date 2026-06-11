import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTheme } from "../hooks/useTheme";
import {
  Sun,
  Moon,
  Monitor,
  Save,
  Check,
  Plus,
  Minus,
  X,
} from "lucide-react";
import { useToast, HintPopover } from "../components/ui";
import apiClient from "../api/client";
import { integrationsApi } from "../api/endpoints";
import type { IntegrationConfig, IntegrationType } from "../api/endpoints";
import {
  INTEGRATION_TYPES,
  getFieldsForType,
  HINTS,
} from "../lib/integrations";

export function Settings() {
  const { theme, setTheme } = useTheme();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [isSaving, setIsSaving] = useState(false);
  const [localTheme, setLocalTheme] = useState<"light" | "dark" | "system">(
    theme,
  );
  const [loading, setLoading] = useState(true);

  const [snmpConfig, setSnmpConfig] = useState({
    community: "public",
    timeout: 5,
    retries: 3,
  });
  const [pollingConfig, setPollingConfig] = useState({
    topology_interval: 30,
    check_interval: 60,
  });
  const [apiUrl, setApiUrl] = useState(
    import.meta.env.VITE_API_URL || "http://localhost:8000",
  );

  const [showIntegrationForm, setShowIntegrationForm] = useState(
    searchParams.get("focus") === "integrations",
  );
  const [editingIntegration, setEditingIntegration] =
    useState<IntegrationConfig | null>(null);
  const [intFormType, setIntFormType] = useState<IntegrationType>("telegram");
  const [intFormName, setIntFormName] = useState("");
  const [intFormSecrets, setIntFormSecrets] = useState<Record<string, string>>(
    {},
  );

  useEffect(() => {
    setLocalTheme(theme);
  }, [theme]);

  useEffect(() => {
    apiClient
      .get("/api/config")
      .then((r) => {
        if (r.data.topology_interval)
          setPollingConfig((p) => ({
            ...p,
            topology_interval: r.data.topology_interval,
          }));
        if (r.data.check_interval)
          setPollingConfig((p) => ({
            ...p,
            check_interval: r.data.check_interval,
          }));
        if (r.data.snmp_timeout !== undefined)
          setSnmpConfig((s) => ({ ...s, timeout: r.data.snmp_timeout }));
        if (r.data.snmp_retries !== undefined)
          setSnmpConfig((s) => ({ ...s, retries: r.data.snmp_retries }));
        if (r.data.snmp_community)
          setSnmpConfig((s) => ({ ...s, community: r.data.snmp_community }));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleThemeChange = (newTheme: "light" | "dark" | "system") => {
    setLocalTheme(newTheme);
    setTheme(newTheme);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await apiClient.put("/api/config", {
        topology_interval: pollingConfig.topology_interval,
        check_interval: pollingConfig.check_interval,
        snmp_timeout: snmpConfig.timeout,
        snmp_retries: snmpConfig.retries,
        snmp_community: snmpConfig.community,
      });
      toast.success(
        "Settings saved",
        "Restart server to apply polling/SNMP changes",
      );
    } catch {
      toast.error("Failed to save settings");
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveApiUrl = () => {
    localStorage.setItem("api_url", apiUrl);
    toast.success("API URL saved", "Page reload required");
  };

  const { data: integrations = [], isLoading: integrationsLoading } = useQuery({
    queryKey: ["integrations"],
    queryFn: async () => (await integrationsApi.list()).data,
  });

  const createIntegration = useMutation({
    mutationFn: (data: {
      type: IntegrationType;
      name: string;
      secrets_json: Record<string, any>;
    }) => integrationsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      resetIntegrationForm();
      toast.success("Integration created");
    },
    onError: (e: any) => {
      const detail = e?.response?.data?.detail;
      toast.error(
        typeof detail === "string" ? detail : "Failed to create integration",
      );
    },
  });

  const updateIntegration = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) =>
      integrationsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      resetIntegrationForm();
      toast.success("Integration updated");
    },
    onError: (e: any) => {
      toast.error(e?.response?.data?.detail || "Failed to update integration");
    },
  });

  const resetIntegrationForm = () => {
    setShowIntegrationForm(false);
    setEditingIntegration(null);
    setIntFormType("telegram");
    setIntFormName("");
    setIntFormSecrets({});
  };

  const handleIntegrationSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanedSecrets: Record<string, string> = {};
    Object.entries(intFormSecrets).forEach(([k, v]) => {
      if (v !== "" && v != null) cleanedSecrets[k] = v;
    });
    if (editingIntegration) {
      updateIntegration.mutate({
        id: editingIntegration.id,
        data: { name: intFormName, secrets_json: cleanedSecrets },
      });
    } else {
      createIntegration.mutate({
        type: intFormType,
        name: intFormName,
        secrets_json: cleanedSecrets,
      });
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-sm h-8 w-8 border-b-2 border-ring" />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Settings</h1>
          <p className="text-muted-foreground mt-1">
            Application configuration
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="flex items-center space-x-2 px-4 py-2 bg-cisco-blue text-white rounded-sm hover:bg-cisco-blue-hover disabled:opacity-50"
        >
          {isSaving ? (
            <Check className="h-4 w-4" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          <span>{isSaving ? "Saving..." : "Save All"}</span>
        </button>
      </div>

      <div className="space-y-6">
        <div className="bg-card rounded-sm shadow-sm border border-border p-6">
          <h2 className="text-xs font-semibold text-foreground mb-4">
            Appearance
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">
                Theme Mode
              </label>
              <div className="grid grid-cols-3 gap-3">
                {(["light", "dark", "system"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => handleThemeChange(t)}
                    className={`flex items-center justify-center space-x-2 px-4 py-3 rounded-sm border transition-all ${
                      localTheme === t
                        ? "border-ring bg-surface-subtle text-foreground"
                        : "border-border text-foreground hover:bg-surface-hover"
                    }`}
                  >
                    {t === "light" && <Sun className="h-4 w-4" />}
                    {t === "dark" && <Moon className="h-4 w-4" />}
                    {t === "system" && <Monitor className="h-4 w-4" />}
                    <span className="capitalize">{t}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-sm shadow-sm border border-border p-6">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2 className="text-xs font-semibold text-foreground">
                Integrations
              </h2>
              <p className="text-xs text-muted-foreground mt-1">
                Global notification credentials (Telegram bot, Slack webhook,
                Email, WhatsApp).
              </p>
            </div>
            <button
              onClick={() => {
                resetIntegrationForm();
                setShowIntegrationForm(true);
              }}
              className="flex items-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252]"
            >
              <Plus className="h-4 w-4" />
              <span>Add Integration</span>
            </button>
          </div>

          {showIntegrationForm && (
            <form
              onSubmit={handleIntegrationSubmit}
              className="mb-6 bg-surface-subtle rounded-sm border border-border p-4 space-y-3"
            >
              <div className="flex justify-between items-center">
                <h3 className="text-xs font-semibold text-foreground">
                  {editingIntegration ? "Edit Integration" : "New Integration"}
                </h3>
                <button
                  type="button"
                  onClick={resetIntegrationForm}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="Close form"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">
                    Type
                  </label>
                  <select
                    value={intFormType}
                    onChange={(e) => {
                      const t = e.target.value as IntegrationType;
                      setIntFormType(t);
                      setIntFormSecrets({});
                    }}
                    disabled={!!editingIntegration}
                    className="w-full px-3 py-2 border border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-[#da1e28] disabled:opacity-60"
                  >
                    {INTEGRATION_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">
                    Name *
                  </label>
                  <input
                    type="text"
                    value={intFormName}
                    onChange={(e) => setIntFormName(e.target.value)}
                    required
                    placeholder="Ops Bot"
                    className="w-full px-3 py-2 border border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                  />
                </div>
              </div>
              {getFieldsForType(intFormType).map((field) => {
                const hint = HINTS[intFormType]?.[field.key];
                return (
                  <div key={field.key}>
                    <div className="flex items-center gap-1.5 mb-1">
                      <label className="block text-xs font-medium text-muted-foreground">
                        {field.label}
                      </label>
                      {hint && (
                        <HintPopover
                          title={hint.title}
                          triggerLabel={`Help: ${field.label}`}
                          width={340}
                        >
                          {hint.body}
                        </HintPopover>
                      )}
                    </div>
                    <input
                      type={field.secret ? "password" : "text"}
                      value={intFormSecrets[field.key] ?? ""}
                      onChange={(e) =>
                        setIntFormSecrets({
                          ...intFormSecrets,
                          [field.key]: e.target.value,
                        })
                      }
                      placeholder={field.placeholder}
                      className="w-full px-3 py-2 border border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                    />
                  </div>
                );
              })}
              <div className="flex justify-end space-x-2">
                <button
                  type="button"
                  onClick={resetIntegrationForm}
                  className="px-3 py-1.5 bg-secondary text-secondary-foreground rounded-sm text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={
                    createIntegration.isPending || updateIntegration.isPending
                  }
                  className="px-3 py-1.5 bg-[#161616] text-white rounded-sm text-xs hover:bg-[#525252] disabled:opacity-50"
                >
                  {editingIntegration ? "Save" : "Create"}
                </button>
              </div>
            </form>
          )}

          {integrationsLoading ? (
            <p className="text-xs text-muted-foreground">
              Loading integrations…
            </p>
          ) : integrations.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No communication channel established yet. Add one above then
              create new alert rules.{" "}
              <Link
                to="/alerts?tab=integrations"
                className="text-cisco-blue hover:underline"
              >
                Manage in Alerts →
              </Link>
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              {integrations.length} integration
              {integrations.length > 1 ? "s" : ""} configured.{" "}
              <Link
                to="/alerts?tab=integrations"
                className="text-cisco-blue hover:underline"
              >
                Manage in Alerts →
              </Link>
            </p>
          )}
        </div>

        <div className="bg-card rounded-sm shadow-sm border border-border p-6">
          <h2 className="text-xs font-semibold text-foreground mb-4">
            SNMP Configuration
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">
                Default Community
              </label>
              <select
                value={snmpConfig.community}
                onChange={(e) =>
                  setSnmpConfig({ ...snmpConfig, community: e.target.value })
                }
                className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-ring"
              >
                <option value="public">public</option>
                <option value="private">private</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">
                  Timeout (seconds)
                </label>
                <div className="flex items-stretch">
                  <input
                    type="number"
                    value={snmpConfig.timeout}
                    onChange={(e) =>
                      setSnmpConfig({
                        ...snmpConfig,
                        timeout: parseInt(e.target.value) || 5,
                      })
                    }
                    min="1"
                    max="30"
                    className="w-16 px-2 py-2 bg-card text-foreground text-center border border-input dark:border-input rounded-sm"
                    style={{ appearance: "textfield" }}
                  />
                  <div className="flex flex-col ml-1">
                    <button
                      type="button"
                      onClick={() =>
                        setSnmpConfig({
                          ...snmpConfig,
                          timeout: Math.min(snmpConfig.timeout + 1, 30),
                        })
                      }
                      className="flex-1 px-2 py-1 bg-card text-foreground border border-input dark:border-input rounded-t-sm hover:bg-muted dark:hover:bg-muted"
                      aria-label="Increase timeout"
                    >
                      <Plus className="h-3 w-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setSnmpConfig({
                          ...snmpConfig,
                          timeout: Math.max(snmpConfig.timeout - 1, 1),
                        })
                      }
                      className="flex-1 px-2 py-1 bg-card text-foreground border border-t-0 border-input dark:border-input rounded-b-sm hover:bg-muted dark:hover:bg-muted"
                      aria-label="Decrease timeout"
                    >
                      <Minus className="h-3 w-3" />
                    </button>
                  </div>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">
                  Retries
                </label>
                <div className="flex items-stretch">
                  <input
                    type="number"
                    value={snmpConfig.retries}
                    onChange={(e) =>
                      setSnmpConfig({
                        ...snmpConfig,
                        retries: parseInt(e.target.value) || 3,
                      })
                    }
                    min="0"
                    max="10"
                    className="w-16 px-2 py-2 bg-card text-foreground text-center border border-input dark:border-input rounded-sm"
                    style={{ appearance: "textfield" }}
                  />
                  <div className="flex flex-col ml-1">
                    <button
                      type="button"
                      onClick={() =>
                        setSnmpConfig({
                          ...snmpConfig,
                          retries: Math.min(snmpConfig.retries + 1, 10),
                        })
                      }
                      className="flex-1 px-2 py-1 bg-card text-foreground border border-input dark:border-input rounded-t-sm hover:bg-muted dark:hover:bg-muted"
                      aria-label="Increase retries"
                    >
                      <Plus className="h-3 w-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setSnmpConfig({
                          ...snmpConfig,
                          retries: Math.max(snmpConfig.retries - 1, 0),
                        })
                      }
                      className="flex-1 px-2 py-1 bg-card text-foreground border border-t-0 border-input dark:border-input rounded-b-sm hover:bg-muted dark:hover:bg-muted"
                      aria-label="Decrease retries"
                    >
                      <Minus className="h-3 w-3" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-sm shadow-sm border border-border p-6">
          <h2 className="text-xs font-semibold text-foreground mb-4">
            Polling Settings
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">
                Topology Polling Interval (seconds)
              </label>
              <div className="flex items-stretch">
                <input
                  type="number"
                  value={pollingConfig.topology_interval}
                  onChange={(e) =>
                    setPollingConfig({
                      ...pollingConfig,
                      topology_interval: parseInt(e.target.value) || 30,
                    })
                  }
                  min="5"
                  max="300"
                  className="w-16 px-2 py-2 bg-card text-foreground text-center border border-input dark:border-input rounded-sm"
                  style={{ appearance: "textfield" }}
                />
                <div className="flex flex-col ml-1">
                  <button
                    type="button"
                    onClick={() =>
                      setPollingConfig({
                        ...pollingConfig,
                        topology_interval: Math.min(
                          pollingConfig.topology_interval + 5,
                          300,
                        ),
                      })
                    }
                    className="flex-1 px-2 py-1 bg-card text-foreground border border-input dark:border-input rounded-t-sm hover:bg-muted dark:hover:bg-muted"
                    aria-label="Increase interval"
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setPollingConfig({
                        ...pollingConfig,
                        topology_interval: Math.max(
                          pollingConfig.topology_interval - 5,
                          5,
                        ),
                      })
                    }
                    className="flex-1 px-2 py-1 bg-card text-foreground border border-t-0 border-input dark:border-input rounded-b-sm hover:bg-muted dark:hover:bg-muted"
                    aria-label="Decrease interval"
                  >
                    <Minus className="h-3 w-3" />
                  </button>
                </div>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">
                Service Check Default Interval (seconds)
              </label>
              <div className="flex items-stretch">
                <input
                  type="number"
                  value={pollingConfig.check_interval}
                  onChange={(e) =>
                    setPollingConfig({
                      ...pollingConfig,
                      check_interval: parseInt(e.target.value) || 60,
                    })
                  }
                  min="10"
                  max="3600"
                  className="w-16 px-2 py-2 bg-card text-foreground text-center border border-input dark:border-input rounded-sm"
                  style={{ appearance: "textfield" }}
                />
                <div className="flex flex-col ml-1">
                  <button
                    type="button"
                    onClick={() =>
                      setPollingConfig({
                        ...pollingConfig,
                        check_interval: Math.min(
                          pollingConfig.check_interval + 10,
                          3600,
                        ),
                      })
                    }
                    className="flex-1 px-2 py-1 bg-card text-foreground border border-input dark:border-input rounded-t-sm hover:bg-muted dark:hover:bg-muted"
                    aria-label="Increase check interval"
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setPollingConfig({
                        ...pollingConfig,
                        check_interval: Math.max(
                          pollingConfig.check_interval - 10,
                          10,
                        ),
                      })
                    }
                    className="flex-1 px-2 py-1 bg-card text-foreground border border-t-0 border-input dark:border-input rounded-b-sm hover:bg-muted dark:hover:bg-muted"
                    aria-label="Decrease check interval"
                  >
                    <Minus className="h-3 w-3" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-sm shadow-sm border border-border p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xs font-semibold text-foreground">
              API Connection
            </h2>
            <button
              onClick={handleSaveApiUrl}
              className="flex items-center space-x-2 px-4 py-2 bg-cisco-blue text-white rounded-sm hover:bg-cisco-blue-hover"
            >
              <Save className="h-4 w-4" />
              <span>Save</span>
            </button>
          </div>
          <div>
            <label className="block text-xs font-medium text-foreground mb-1">
              Backend API URL
            </label>
            <input
              type="text"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-ring"
            />
            <p className="text-xs text-muted-foreground mt-1">
              Changes require a page reload
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Settings;
