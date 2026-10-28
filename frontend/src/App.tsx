import { useState, useEffect } from 'react';
import {
  FileText, ShieldAlert, CheckCircle2, AlertTriangle, RefreshCw, Download,
  Search, BarChart3, Database, Layers, Check, X, CreditCard,
  Truck, Scale, ShieldCheck, DollarSign
} from 'lucide-react';

const API_BASE = "http://127.0.0.1:8000/api";

interface KPIs {
  total_invoices: number;
  validated_match_count: number;
  exception_disputed_count: number;
  paid_count: number;
  match_rate_pct: number;
  total_billed_usd: number;
  total_expected_usd: number;
  total_variance_recovered_usd: number;
  exceptions_by_category: Record<string, number>;
  invoices_by_status: Record<string, number>;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'overview' | 'invoices' | 'exceptions' | 'credits' | 'eval' | 'audit'>('overview');
  const [kpis, setKpis] = useState<KPIs | null>(null);
  const [invoices, setInvoices] = useState<any[]>([]);
  const [exceptions, setExceptions] = useState<any[]>([]);
  const [creditNotes, setCreditNotes] = useState<any[]>([]);
  const [evalData, setEvalData] = useState<any>(null);
  const [auditEvents, setAuditEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<any | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const showNotification = (msg: string) => {
    setActionMessage(msg);
    setTimeout(() => setActionMessage(null), 4000);
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const [kpiRes, invRes, excRes, cnRes, evalRes, auditRes] = await Promise.all([
        fetch(`${API_BASE}/dashboard/kpis`),
        fetch(`${API_BASE}/invoices?limit=100`),
        fetch(`${API_BASE}/exceptions?limit=100`),
        fetch(`${API_BASE}/credit-notes`),
        fetch(`${API_BASE}/evaluation`),
        fetch(`${API_BASE}/audit-events?limit=50`),
      ]);

      if (kpiRes.ok) setKpis(await kpiRes.json());
      if (invRes.ok) {
        const invData = await invRes.json();
        setInvoices(invData.items || []);
      }
      if (excRes.ok) setExceptions(await excRes.json());
      if (cnRes.ok) setCreditNotes(await cnRes.json());
      if (evalRes.ok) setEvalData(await evalRes.json());
      if (auditRes.ok) setAuditEvents(await auditRes.json());
    } catch (err) {
      console.error("API connection error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleRunBatchAudit = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/invoices/validate-all`, { method: 'POST' });
      const data = await res.json();
      showNotification(`Batch audit completed! Audited: ${data.total_audited}, Passed: ${data.passed}, Discrepancies: ${data.discrepancies_raised}`);
      await loadData();
    } catch {
      showNotification("Failed to trigger batch audit.");
    } finally {
      setLoading(false);
    }
  };

  const handleSeedData = async (scale: string) => {
    if (!confirm(`Generate synthetic freight data with scale: ${scale.toUpperCase()}?`)) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/dataset/seed?scale=${scale}&reset=true`, { method: 'POST' });
      const data = await res.json();
      showNotification(`Seed complete! Generated ${data.counts?.invoices} invoices across ${data.counts?.carriers} carriers.`);
      await loadData();
    } catch {
      showNotification("Failed to generate seed data.");
    } finally {
      setLoading(false);
    }
  };

  const handleInspectInvoice = async (id: number) => {
    try {
      const res = await fetch(`${API_BASE}/invoices/${id}`);
      if (res.ok) {
        setSelectedInvoice(await res.json());
      }
    } catch {
      showNotification("Failed to fetch invoice details.");
    }
  };

  const handleValidateSingle = async (id: number) => {
    try {
      const res = await fetch(`${API_BASE}/invoices/${id}/validate`, { method: 'POST' });
      if (res.ok) {
        showNotification(`Invoice #${id} re-validated successfully.`);
        await handleInspectInvoice(id);
        await loadData();
      }
    } catch {
      showNotification("Failed to validate invoice.");
    }
  };

  const handleResolveException = async (id: number, status: string) => {
    try {
      const res = await fetch(`${API_BASE}/exceptions/${id}?status=${status}`, { method: 'PATCH' });
      if (res.ok) {
        showNotification(`Exception marked as ${status}.`);
        await loadData();
      }
    } catch {
      showNotification("Failed to update exception.");
    }
  };

  const handleReconcileCredit = async (id: number) => {
    try {
      const res = await fetch(`${API_BASE}/credit-notes/${id}/reconcile`, { method: 'POST' });
      const data = await res.json();
      showNotification(`Credit note processed. Status: ${data.status}`);
      await loadData();
    } catch {
      showNotification("Failed to reconcile credit note.");
    }
  };

  const handleExportChecksums = async () => {
    try {
      const res = await fetch(`${API_BASE}/dataset/export`);
      const data = await res.json();
      showNotification(`Datasets exported to: ${data.output_directory}. Checksums manifest generated!`);
      await loadData();
    } catch {
      showNotification("Export failed.");
    }
  };

  const filteredInvoices = invoices.filter(inv => {
    const matchesSearch = !searchTerm || 
      inv.invoice_number.toLowerCase().includes(searchTerm.toLowerCase()) ||
      inv.bol_number_billed.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (inv.carrier_code && inv.carrier_code.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesStatus = statusFilter === 'ALL' || inv.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-30 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="bg-blue-600/20 text-blue-400 p-2 rounded-lg border border-blue-500/30">
            <Truck className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
              Freight Invoice Validation System
              <span className="badge badge-success text-[10px] tracking-widest font-mono">v1.0 ONLINE</span>
            </h1>
            <p className="text-xs text-slate-400">Contractual Freight Audit • Automated Rating • Anomaly Detection</p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button onClick={handleRunBatchAudit} className="btn btn-primary text-xs" disabled={loading}>
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Run Batch Audit
          </button>
          <button onClick={() => handleSeedData('starter')} className="btn btn-secondary text-xs" disabled={loading}>
            <Database className="w-3.5 h-3.5 text-amber-400" />
            Seed Starter
          </button>
          <button onClick={handleExportChecksums} className="btn btn-secondary text-xs" disabled={loading}>
            <Download className="w-3.5 h-3.5 text-emerald-400" />
            Export & Verify
          </button>
        </div>
      </header>

      {/* Action Notification Toast */}
      {actionMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-blue-600 text-white px-4 py-2.5 rounded-lg shadow-xl text-sm font-medium flex items-center gap-2 animate-bounce">
          <CheckCircle2 className="w-4 h-4 text-emerald-300" />
          {actionMessage}
        </div>
      )}

      {/* Main Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Navigation Sidebar */}
        <aside className="w-64 border-r border-slate-800 bg-slate-900/50 p-4 flex flex-col gap-1.5 shrink-0">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider px-3 py-1">Operations Hub</div>
          <button
            onClick={() => setActiveTab('overview')}
            className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition ${activeTab === 'overview' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}
          >
            <BarChart3 className="w-4 h-4" />
            Executive Overview
          </button>
          <button
            onClick={() => setActiveTab('invoices')}
            className={`flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition ${activeTab === 'invoices' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}
          >
            <span className="flex items-center gap-3">
              <FileText className="w-4 h-4" />
              Invoices Explorer
            </span>
            <span className="text-xs bg-slate-800 px-2 py-0.5 rounded-full">{invoices.length}</span>
          </button>
          <button
            onClick={() => setActiveTab('exceptions')}
            className={`flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition ${activeTab === 'exceptions' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}
          >
            <span className="flex items-center gap-3">
              <ShieldAlert className="w-4 h-4 text-red-400" />
              Exception Queue
            </span>
            <span className="text-xs bg-red-950/60 text-red-400 border border-red-800 px-2 py-0.5 rounded-full">{exceptions.filter(e => e.status === 'OPEN').length}</span>
          </button>
          <button
            onClick={() => setActiveTab('credits')}
            className={`flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition ${activeTab === 'credits' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}
          >
            <span className="flex items-center gap-3">
              <CreditCard className="w-4 h-4 text-amber-400" />
              Credit Notes
            </span>
            <span className="text-xs bg-slate-800 px-2 py-0.5 rounded-full">{creditNotes.length}</span>
          </button>

          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider px-3 py-1 mt-4">Quality & Verification</div>
          <button
            onClick={() => setActiveTab('eval')}
            className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition ${activeTab === 'eval' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}
          >
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            Ground-Truth Evaluation
          </button>
          <button
            onClick={() => setActiveTab('audit')}
            className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition ${activeTab === 'audit' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}
          >
            <Layers className="w-4 h-4 text-cyan-400" />
            Audit Trail & Exports
          </button>
        </aside>

        {/* Content Pane */}
        <main className="flex-1 overflow-y-auto p-6">
          {/* TAB 1: EXECUTIVE OVERVIEW */}
          {activeTab === 'overview' && kpis && (
            <div className="space-y-6">
              {/* Metric Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                <div className="dashboard-card">
                  <div className="text-xs text-slate-400 font-medium">Total Invoices</div>
                  <div className="text-2xl font-bold text-white mt-1">{kpis.total_invoices}</div>
                  <div className="text-xs text-slate-400 mt-2 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span>{kpis.validated_match_count} passed auto-audit</span>
                  </div>
                </div>

                <div className="dashboard-card">
                  <div className="text-xs text-slate-400 font-medium">Auto-Audit Match Rate</div>
                  <div className="text-2xl font-bold text-emerald-400 mt-1">{kpis.match_rate_pct}%</div>
                  <div className="text-xs text-slate-400 mt-2">Within contractual tolerance</div>
                </div>

                <div className="dashboard-card">
                  <div className="text-xs text-slate-400 font-medium">Total Billed Freight</div>
                  <div className="text-2xl font-bold text-white mt-1">${kpis.total_billed_usd.toLocaleString()}</div>
                  <div className="text-xs text-slate-400 mt-2">Gross invoices submitted</div>
                </div>

                <div className="dashboard-card">
                  <div className="text-xs text-slate-400 font-medium">Contractual Expected</div>
                  <div className="text-2xl font-bold text-blue-400 mt-1">${kpis.total_expected_usd.toLocaleString()}</div>
                  <div className="text-xs text-slate-400 mt-2">Calculated rate card baseline</div>
                </div>

                <div className="dashboard-card border-emerald-500/30 bg-emerald-950/10">
                  <div className="text-xs text-emerald-300 font-medium flex items-center justify-between">
                    <span>Leakage Prevented</span>
                    <DollarSign className="w-4 h-4 text-emerald-400" />
                  </div>
                  <div className="text-2xl font-bold text-emerald-400 mt-1">${kpis.total_variance_recovered_usd.toLocaleString()}</div>
                  <div className="text-xs text-emerald-400/80 mt-2">Overbilling caught & disputed</div>
                </div>
              </div>

              {/* Anomaly Category Grid */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="dashboard-card">
                  <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                    Detected Discrepancies by Category (5 Negative Scenarios)
                  </h3>
                  <div className="space-y-3">
                    {Object.entries(kpis.exceptions_by_category).map(([cat, count]) => (
                      <div key={cat} className="flex items-center justify-between bg-slate-900/60 p-3 rounded-lg border border-slate-800">
                        <div className="font-mono text-xs text-slate-200">{cat.replace(/_/g, ' ')}</div>
                        <div className="flex items-center gap-2">
                          <span className="badge badge-danger">{count} flagged</span>
                        </div>
                      </div>
                    ))}
                    {Object.keys(kpis.exceptions_by_category).length === 0 && (
                      <div className="text-xs text-slate-500 italic p-4 text-center">No open discrepancies detected.</div>
                    )}
                  </div>
                </div>

                <div className="dashboard-card">
                  <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <Layers className="w-4 h-4 text-blue-400" />
                    Invoice Reconciliation Lifecycle Distribution
                  </h3>
                  <div className="space-y-3">
                    {Object.entries(kpis.invoices_by_status).map(([st, count]) => (
                      <div key={st} className="flex items-center justify-between bg-slate-900/60 p-3 rounded-lg border border-slate-800">
                        <div className="font-mono text-xs text-slate-200">{st.replace(/_/g, ' ')}</div>
                        <span className={`badge ${st === 'VALIDATED_MATCH' ? 'badge-success' : st.includes('DISPUTED') ? 'badge-danger' : 'badge-neutral'}`}>
                          {count} invoices
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: INVOICES EXPLORER */}
          {activeTab === 'invoices' && (
            <div className="space-y-4">
              {/* Filter Bar */}
              <div className="flex items-center justify-between gap-4 bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                <div className="flex items-center gap-2 flex-1 max-w-md bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800">
                  <Search className="w-4 h-4 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search Invoice #, BOL #, Carrier Code..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="bg-transparent border-none outline-none text-xs text-white w-full"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-slate-400">Status:</label>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="bg-slate-950 text-xs text-white border border-slate-800 rounded px-2.5 py-1.5 outline-none"
                  >
                    <option value="ALL">All Statuses</option>
                    <option value="VALIDATED_MATCH">Validated Match</option>
                    <option value="EXCEPTION_DISPUTED">Exception Disputed</option>
                    <option value="PENDING_AUDIT">Pending Audit</option>
                    <option value="EXCEPTION_APPROVED">Exception Approved</option>
                  </select>
                </div>
              </div>

              {/* Table */}
              <div className="dashboard-card p-0 overflow-hidden">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Invoice #</th>
                      <th>Carrier</th>
                      <th>BOL Number</th>
                      <th>Billed ($)</th>
                      <th>Expected ($)</th>
                      <th>Variance ($)</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredInvoices.map((inv) => (
                      <tr key={inv.id}>
                        <td className="font-mono font-medium text-blue-400">
                          {inv.invoice_number}
                          {inv.is_duplicate && <span className="ml-2 badge badge-danger text-[9px]">DUP</span>}
                        </td>
                        <td>
                          <div className="font-semibold text-xs text-slate-200">{inv.carrier_code}</div>
                          <div className="text-[10px] text-slate-400 truncate max-w-[140px]">{inv.carrier_name}</div>
                        </td>
                        <td className="font-mono text-xs">{inv.bol_number_billed}</td>
                        <td className="font-medium">${inv.total_billed_amount.toFixed(2)}</td>
                        <td className="text-slate-400">${inv.calculated_expected_amount.toFixed(2)}</td>
                        <td className={`font-mono text-xs ${inv.total_variance_amount > 0 ? 'text-red-400 font-bold' : 'text-slate-400'}`}>
                          {inv.total_variance_amount > 0 ? `+${inv.total_variance_amount.toFixed(2)}` : `${inv.total_variance_amount.toFixed(2)}`}
                        </td>
                        <td>
                          <span className={`badge ${inv.status === 'VALIDATED_MATCH' ? 'badge-success' : inv.status.includes('DISPUTED') ? 'badge-danger' : 'badge-neutral'}`}>
                            {inv.status}
                          </span>
                        </td>
                        <td>
                          <button
                            onClick={() => handleInspectInvoice(inv.id)}
                            className="btn btn-secondary text-xs px-2.5 py-1"
                          >
                            Inspect Audit
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 3: EXCEPTION QUEUE */}
          {activeTab === 'exceptions' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-white">Exception Resolution Queue ({exceptions.length} Total)</h2>
              </div>

              <div className="space-y-3">
                {exceptions.map((exc) => (
                  <div key={exc.id} className="dashboard-card flex flex-col md:flex-row md:items-center justify-between gap-4 border-l-4 border-l-red-500">
                    <div className="space-y-1.5 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="badge badge-danger text-[10px]">{exc.category.replace(/_/g, ' ')}</span>
                        <span className="font-mono text-xs text-slate-400">Invoice ID: #{exc.invoice_id}</span>
                        <span className="badge badge-warning text-[10px]">{exc.severity}</span>
                        <span className="badge badge-neutral text-[10px]">{exc.status}</span>
                      </div>
                      <div className="text-sm font-medium text-slate-100">{exc.explanation}</div>
                      <div className="text-xs text-slate-400 font-mono">
                        Billed: ${exc.billed_amount.toFixed(2)} | Contractual Expected: ${exc.expected_amount.toFixed(2)} | Variance: +${exc.variance_amount.toFixed(2)}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {exc.status === 'OPEN' && (
                        <>
                          <button
                            onClick={() => handleResolveException(exc.id, 'APPROVED_OVERRIDE')}
                            className="btn btn-secondary text-xs flex items-center gap-1 text-emerald-400 border border-emerald-500/30"
                          >
                            <Check className="w-3.5 h-3.5" />
                            Approve Override
                          </button>
                          <button
                            onClick={() => handleResolveException(exc.id, 'DISPUTED')}
                            className="btn btn-danger text-xs flex items-center gap-1"
                          >
                            <X className="w-3.5 h-3.5" />
                            Dispute Carrier
                          </button>
                        </>
                      )}
                      {exc.status !== 'OPEN' && (
                        <span className="text-xs text-slate-400 italic font-mono">Resolved: {exc.status}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 4: CREDIT NOTES */}
          {activeTab === 'credits' && (
            <div className="space-y-4">
              <h2 className="text-base font-semibold text-white">Credit-Note Reconciliation & Verification (Scenario 5)</h2>
              <div className="dashboard-card p-0 overflow-hidden">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Credit Note #</th>
                      <th>Carrier</th>
                      <th>Parent Invoice</th>
                      <th>Credit Amount ($)</th>
                      <th>Applied ($)</th>
                      <th>Status</th>
                      <th>Reason Code & Notes</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {creditNotes.map((cn) => (
                      <tr key={cn.id}>
                        <td className="font-mono font-medium text-amber-400">{cn.credit_note_number}</td>
                        <td className="font-mono text-xs">{cn.carrier_code}</td>
                        <td className="font-mono text-xs text-blue-400">{cn.original_invoice_number}</td>
                        <td className="font-bold">${cn.credit_amount.toFixed(2)}</td>
                        <td className="text-emerald-400">${cn.applied_amount.toFixed(2)}</td>
                        <td>
                          <span className={`badge ${cn.status === 'FULLY_APPLIED' ? 'badge-success' : cn.status === 'REJECTED' ? 'badge-danger' : 'badge-warning'}`}>
                            {cn.status}
                          </span>
                        </td>
                        <td className="text-xs">
                          <div>{cn.reason_code}</div>
                          {cn.rejection_reason && <div className="text-red-400 text-[11px] mt-0.5">{cn.rejection_reason}</div>}
                        </td>
                        <td>
                          {cn.status === 'UNAPPLIED' && (
                            <button
                              onClick={() => handleReconcileCredit(cn.id)}
                              className="btn btn-primary text-xs px-2.5 py-1"
                            >
                              Reconcile
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 5: GROUND TRUTH EVALUATION */}
          {activeTab === 'eval' && evalData && (
            <div className="space-y-6">
              <div className="dashboard-card bg-slate-900 border-blue-500/30">
                <h3 className="text-base font-bold text-white mb-1 flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                  Independent Ground-Truth Evaluation Matrix
                </h3>
                <p className="text-xs text-slate-400">
                  Validation Engine detection accuracy compared against independently stored ground-truth anomaly labels.
                </p>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                  <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 text-center">
                    <div className="text-xs text-slate-400">Accuracy</div>
                    <div className="text-3xl font-extrabold text-white mt-1">{(evalData.metrics.accuracy * 100).toFixed(1)}%</div>
                  </div>
                  <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 text-center">
                    <div className="text-xs text-slate-400">Precision</div>
                    <div className="text-3xl font-extrabold text-blue-400 mt-1">{(evalData.metrics.precision * 100).toFixed(1)}%</div>
                  </div>
                  <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 text-center">
                    <div className="text-xs text-slate-400">Recall (Sensitivity)</div>
                    <div className="text-3xl font-extrabold text-emerald-400 mt-1">{(evalData.metrics.recall * 100).toFixed(1)}%</div>
                  </div>
                  <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 text-center">
                    <div className="text-xs text-slate-400">F1-Score</div>
                    <div className="text-3xl font-extrabold text-purple-400 mt-1">{(evalData.metrics.f1_score * 100).toFixed(1)}%</div>
                  </div>
                </div>

                {/* Confusion Matrix Table */}
                <div className="mt-6">
                  <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">Confusion Matrix</h4>
                  <div className="grid grid-cols-2 gap-3 max-w-md">
                    <div className="bg-emerald-950/20 border border-emerald-500/40 p-3 rounded text-center">
                      <div className="text-[11px] text-emerald-400 font-semibold">True Positives (TP)</div>
                      <div className="text-xl font-bold text-white mt-1">{evalData.summary.true_positives}</div>
                      <div className="text-[10px] text-slate-400">Anomalies caught</div>
                    </div>
                    <div className="bg-amber-950/20 border border-amber-500/40 p-3 rounded text-center">
                      <div className="text-[11px] text-amber-400 font-semibold">False Positives (FP)</div>
                      <div className="text-xl font-bold text-white mt-1">{evalData.summary.false_positives}</div>
                      <div className="text-[10px] text-slate-400">False alarms</div>
                    </div>
                    <div className="bg-red-950/20 border border-red-500/40 p-3 rounded text-center">
                      <div className="text-[11px] text-red-400 font-semibold">False Negatives (FN)</div>
                      <div className="text-xl font-bold text-white mt-1">{evalData.summary.false_negatives}</div>
                      <div className="text-[10px] text-slate-400">Missed anomalies</div>
                    </div>
                    <div className="bg-blue-950/20 border border-blue-500/40 p-3 rounded text-center">
                      <div className="text-[11px] text-blue-400 font-semibold">True Negatives (TN)</div>
                      <div className="text-xl font-bold text-white mt-1">{evalData.summary.true_negatives}</div>
                      <div className="text-[10px] text-slate-400">Clean invoices passed</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Breakdown Table */}
              <div className="dashboard-card p-0 overflow-hidden">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Scenario Category</th>
                      <th>Total Injected</th>
                      <th>Detected (TP)</th>
                      <th>Missed (FN)</th>
                      <th>Detection Rate (%)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(evalData.scenario_breakdown || {}).map(([scen, counts]: any) => (
                      <tr key={scen}>
                        <td className="font-mono font-medium text-xs text-white">{scen.replace(/_/g, ' ')}</td>
                        <td>{counts.total_injected}</td>
                        <td className="text-emerald-400 font-semibold">{counts.detected}</td>
                        <td className="text-red-400">{counts.missed}</td>
                        <td>
                          <span className="badge badge-success font-mono">{counts.detection_rate_pct}%</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 6: AUDIT TRAIL & EXPORTS */}
          {activeTab === 'audit' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-white">Immutable Audit Trail & Lifecycle History</h2>
                <button onClick={handleExportChecksums} className="btn btn-primary text-xs">
                  <Download className="w-3.5 h-3.5" />
                  Generate Checksums Manifest
                </button>
              </div>

              <div className="dashboard-card p-0 overflow-hidden">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Entity</th>
                      <th>Entity ID</th>
                      <th>Event Type</th>
                      <th>Actor</th>
                      <th>Notes & Snapshot</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditEvents.map((ev) => (
                      <tr key={ev.id}>
                        <td className="font-mono text-xs text-slate-400">{new Date(ev.timestamp).toLocaleString()}</td>
                        <td className="font-mono text-xs text-blue-400">{ev.entity_type}</td>
                        <td className="font-mono text-xs">#{ev.entity_id}</td>
                        <td><span className="badge badge-neutral text-[10px]">{ev.event_type}</span></td>
                        <td className="text-xs font-semibold text-slate-300">{ev.actor}</td>
                        <td className="text-xs text-slate-300 truncate max-w-[280px]">{ev.notes || ev.payload_json}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Invoice Detail Slide-out Drawer */}
      {selectedInvoice && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-2xl bg-slate-900 border-l border-slate-800 h-full overflow-y-auto p-6 space-y-6 shadow-2xl flex flex-col justify-between">
            <div className="space-y-6">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <h3 className="text-lg font-bold text-white flex items-center gap-2">
                    Invoice Audit Details
                    <span className="font-mono text-blue-400">{selectedInvoice.invoice_number}</span>
                  </h3>
                  <p className="text-xs text-slate-400">Carrier: {selectedInvoice.carrier_code} • BOL: {selectedInvoice.bol_number_billed}</p>
                </div>
                <button
                  onClick={() => setSelectedInvoice(null)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Status Header */}
              <div className="grid grid-cols-3 gap-3 bg-slate-950 p-4 rounded-lg border border-slate-800">
                <div>
                  <div className="text-[10px] text-slate-400 uppercase">Total Billed</div>
                  <div className="text-lg font-bold text-white">${selectedInvoice.total_billed_amount.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-400 uppercase">Expected Rate</div>
                  <div className="text-lg font-bold text-blue-400">${selectedInvoice.calculated_expected_amount.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-400 uppercase">Variance</div>
                  <div className={`text-lg font-bold ${selectedInvoice.total_variance_amount > 0 ? 'text-red-400' : 'text-slate-300'}`}>
                    ${selectedInvoice.total_variance_amount.toFixed(2)}
                  </div>
                </div>
              </div>

              {/* Operational Proof & Shipment Info */}
              {selectedInvoice.shipment && (
                <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800 space-y-2 text-xs">
                  <div className="font-semibold text-slate-300 flex items-center gap-1.5">
                    <Scale className="w-4 h-4 text-amber-400" />
                    Shipment & Delivery Proof Records
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-slate-400">
                    <div>Origin: <span className="text-white">{selectedInvoice.shipment.origin}</span></div>
                    <div>Destination: <span className="text-white">{selectedInvoice.shipment.destination}</span></div>
                    <div>Certified Scale Weight: <span className="text-white">{selectedInvoice.shipment.gross_weight_lbs} lbs</span></div>
                    <div>Billable Weight: <span className="text-white">{selectedInvoice.shipment.billable_weight_lbs} lbs</span></div>
                    <div>Dock Type: <span className="text-white">{selectedInvoice.shipment.dock_type}</span></div>
                    <div>Liftgate Used: <span className={selectedInvoice.shipment.liftgate_actually_used ? 'text-emerald-400 font-bold' : 'text-slate-400'}>{selectedInvoice.shipment.liftgate_actually_used ? 'YES' : 'NO'}</span></div>
                    <div>Facility Dwell Time: <span className="text-white">{selectedInvoice.shipment.dwell_minutes_recorded} mins</span></div>
                  </div>
                </div>
              )}

              {/* Line items table */}
              <div>
                <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">Reconciled Line Items</h4>
                <div className="border border-slate-800 rounded-lg overflow-hidden">
                  <table className="custom-table text-xs">
                    <thead>
                      <tr>
                        <th>Line #</th>
                        <th>Type</th>
                        <th>Description</th>
                        <th>Billed</th>
                        <th>Expected</th>
                        <th>Variance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedInvoice.lines.map((l: any) => (
                        <tr key={l.id}>
                          <td>{l.line_number}</td>
                          <td><span className="badge badge-neutral text-[9px]">{l.charge_type}</span></td>
                          <td>{l.description}</td>
                          <td className="font-semibold">${l.billed_amount.toFixed(2)}</td>
                          <td className="text-slate-400">${l.expected_amount.toFixed(2)}</td>
                          <td className={`font-mono ${l.variance_amount > 0 ? 'text-red-400 font-bold' : 'text-slate-300'}`}>
                            ${l.variance_amount.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-slate-800 flex justify-end gap-2">
              <button
                onClick={() => handleValidateSingle(selectedInvoice.id)}
                className="btn btn-primary text-xs"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Re-Validate Invoice
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
