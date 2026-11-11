"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
type User = { id: string; full_name: string; email: string; role_name: string };
type InboxItem = {
  id: string; contact_id: string; lead_id: string | null; customer_name: string;
  phone_number: string; domicile: string | null; vehicle_interest: string | null;
  temperature: string; source: string | null; is_simulated: boolean; provider: string;
  handler: string; status: string; unread_count: number; last_message_at: string | null;
};
type Message = { id: string; direction: string; sender_type: string; content: string; status: string; created_at: string; created_at_wib: string };
type Agent = { id: string; display_name: string; is_available: boolean; active_leads: number; max_active_leads: number | null };
type Lead = { id: string; full_name: string | null; domicile: string | null; vehicle_interest: string | null; temperature: string; status: string; source: string; assigned_agent_id: string | null; is_simulated: boolean };
type Contact = { id: string; display_name: string | null; phone_number: string };
type SimChat = { conversations: { messages: Message[] }[] };
type QueueItem = { conversation_id: string; customer_name: string; phone_number: string; domicile: string | null; vehicle_interest: string | null; temperature: string; handover_reason: string; unread_count: number };
type Summary = { cold_leads: number; warm_leads: number; open_conversations: number; admin_queue: number; assigned_sales_conversations: number };

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init, credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data?.error?.message || data?.detail || `Request gagal (${response.status})`);
  return data as T;
}
const fmt = (value: string | null) => value ? new Date(value).toLocaleString("id-ID", { dateStyle: "short", timeStyle: "short" }) : "—";

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [section, setSection] = useState("inbox");
  const [items, setItems] = useState<InboxItem[]>([]);
  const [selected, setSelected] = useState<InboxItem | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messageText, setMessageText] = useState("");
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [simMessages, setSimMessages] = useState<Message[]>([]);
  const [selectedContact, setSelectedContact] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const isStaff = user?.role_name === "admin" || user?.role_name === "supervisor";

  const loadInbox = useCallback(async () => {
    const data = await api<InboxItem[]>("/inbox?status=open&limit=150");
    setItems(data);
    if (selected) {
      const latest = data.find(x => x.id === selected.id);
      if (latest) setSelected(latest);
    }
  }, [selected]);

  const loadMessages = useCallback(async (id: string) => {
    const data = await api<Message[]>(`/conversations/${id}/messages`);
    setMessages(data);
  }, []);

  const loadAll = useCallback(async () => {
    if (!user) return;
    try {
      await loadInbox();
      if (isStaff) {
        const [q, l, a, s] = await Promise.all([
          api<QueueItem[]>("/admin-queue"), api<Lead[]>("/leads?limit=200"),
          api<Agent[]>("/agents?active_only=false"), api<Summary>("/dashboard/summary"),
        ]);
        setQueue(q); setLeads(l); setAgents(a); setSummary(s);
      }
    } catch (e) { setNotice(e instanceof Error ? e.message : "Gagal memuat data"); }
  }, [user, isStaff, loadInbox]);

  useEffect(() => {
    api<User>("/auth/me").then(setUser).catch(() => setUser(null));
  }, []);
  useEffect(() => { if (user) loadAll(); }, [user, loadAll]);
  useEffect(() => {
    if (!user) return;
    const timer = window.setInterval(() => { loadAll(); if (selected) loadMessages(selected.id); }, 5000);
    return () => window.clearInterval(timer);
  }, [user, selected, loadAll, loadMessages]);
  useEffect(() => { if (selected) loadMessages(selected.id).catch(e => setNotice(e.message)); }, [selected, loadMessages]);

  async function login(e: FormEvent) {
    e.preventDefault(); setLoginError(""); setBusy(true);
    try {
      const result = await api<{ user: User }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      setUser(result.user); setPassword("");
    } catch (e) { setLoginError(e instanceof Error ? e.message : "Login gagal"); }
    finally { setBusy(false); }
  }
  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setUser(null); setSelected(null); setItems([]); setMessages([]);
  }
  async function sendMessage(e: FormEvent) {
    e.preventDefault(); if (!selected || !messageText.trim()) return;
    setBusy(true);
    try {
      await api(`/conversations/${selected.id}/messages`, { method: "POST", body: JSON.stringify({ text: messageText.trim() }) });
      setMessageText(""); await loadMessages(selected.id); await loadInbox();
    } catch (e) { setNotice(e instanceof Error ? e.message : "Pesan gagal dikirim"); }
    finally { setBusy(false); }
  }
  async function claimQueue(item: QueueItem) {
    try { await api(`/admin-queue/${item.conversation_id}/claim`, { method: "POST" }); setNotice("Percakapan masuk ke Admin Inbox."); await loadAll(); }
    catch (e) { setNotice(e instanceof Error ? e.message : "Gagal mengambil antrean"); }
  }
  async function assignLead(leadId: string, agentId: string) {
    try { await api(`/leads/${leadId}/assign`, { method: "POST", body: JSON.stringify({ agent_profile_id: agentId }) }); setNotice("Lead berhasil di-assign."); await loadAll(); }
    catch (e) { setNotice(e instanceof Error ? e.message : "Assignment gagal"); }
  }
  async function loadSimulator() {
    try {
      const data = await api<Contact[]>("/simulator/contacts"); setContacts(data);
      if (!selectedContact && data[0]) { setSelectedContact(data[0].id); await loadSimChat(data[0].id); }
    } catch (e) { setNotice(e instanceof Error ? e.message : "Simulator tidak tersedia"); }
  }
  async function loadSimChat(contactId: string) {
    if (!contactId) { setSimMessages([]); return; }
    try { const chat = await api<SimChat>(`/simulator/contacts/${contactId}/chat`); setSimMessages(chat.conversations.flatMap(x => x.messages)); }
    catch (e) { setNotice(e instanceof Error ? e.message : "Gagal memuat chat simulasi"); }
  }
  async function createDummy() {
    try {
      const contact = await api<Contact>("/simulator/contacts", { method: "POST", body: JSON.stringify({ display_name: "Customer Dummy" }) });
      setContacts(old => [...old, contact]); setSelectedContact(contact.id); setSimMessages([]);
    } catch (e) { setNotice(e instanceof Error ? e.message : "Gagal membuat customer dummy"); }
  }
  async function sendAsCustomer(e: FormEvent) {
    e.preventDefault(); if (!selectedContact || !messageText.trim()) return;
    setBusy(true);
    try {
      await api(`/simulator/contacts/${selectedContact}/messages`, { method: "POST", body: JSON.stringify({ text: messageText.trim() }) });
      setMessageText(""); await loadSimChat(selectedContact); await loadAll();
    } catch (e) { setNotice(e instanceof Error ? e.message : "Pesan simulasi gagal"); }
    finally { setBusy(false); }
  }

  const visibleItems = useMemo(() => items.filter(x => section === "inbox" ? true : x.handler === section), [items, section]);
  if (!user) return <main className="login-shell"><form className="login-card" onSubmit={login}>
    <div className="brand-mark">D</div><p className="eyebrow">MITSUBISHI DIPO</p><h1>Lead Center</h1><p className="muted">Masuk ke workspace percakapan dan pengelolaan leads.</p>
    <label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} required /></label>
    <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
    {loginError && <div className="alert">{loginError}</div>}<button className="primary full" disabled={busy}>{busy ? "Memproses…" : "Masuk ke dashboard"}</button>
    <p className="tiny">Akun awal mengikuti konfigurasi seed di server. Ganti password default sebelum digunakan bersama.</p>
  </form></main>;

  return <main className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark small">D</div><div><strong>DIPO</strong><span>LEAD CENTER</span></div></div>
      <div className="mode-banner"><i /> DEVELOPMENT MODE <small>Simulasi aktif · WhatsApp asli nonaktif</small></div>
      <p className="nav-label">WORKSPACE</p>
      <button className={section === "inbox" ? "nav active" : "nav"} onClick={() => setSection("inbox")}>▤ <span>Semua Inbox</span><b>{items.length}</b></button>
      {isStaff && <button className={section === "admin_queue" ? "nav active" : "nav"} onClick={() => setSection("admin_queue")}>◷ <span>Admin Queue</span><b>{queue.length}</b></button>}
      {isStaff && <button className={section === "leads" ? "nav active" : "nav"} onClick={() => setSection("leads")}>◈ <span>Data Leads</span></button>}
      {isStaff && <button className={section === "dashboard" ? "nav active" : "nav"} onClick={() => setSection("dashboard")}>▦ <span>Dashboard</span></button>}
      {isStaff && <button className={section === "simulator" ? "nav active" : "nav"} onClick={() => { setSection("simulator"); loadSimulator(); }}>▣ <span>WhatsApp Simulator</span></button>}
      {isStaff && <button className={section === "settings" ? "nav active" : "nav"} onClick={() => setSection("settings")}>⚙ <span>Wilayah & Sales</span></button>}
      <div className="sidebar-bottom"><div className="avatar">{user.full_name.slice(0,1).toUpperCase()}</div><div className="user-meta"><strong>{user.full_name}</strong><span>{user.role_name}</span></div><button className="icon-button" onClick={logout} title="Keluar">↗</button></div>
    </aside>
    <section className="main-panel">
      <header className="topbar"><div><p className="eyebrow">DIPO MOTORS / WORKSPACE</p><h2>{({ inbox: "Inbox Percakapan", admin_queue: "Admin Queue", leads: "Database Leads", dashboard: "Dashboard Overview", simulator: "WhatsApp Simulator", settings: "Wilayah & Sales" } as Record<string,string>)[section]}</h2></div><div className="top-actions"><span className="live-dot">● Live · refresh 5 detik</span><span className="top-user">{user.full_name}</span></div></header>
      {notice && <button className="notice" onClick={() => setNotice("")}>{notice} <b>×</b></button>}
      {section === "dashboard" && isStaff && <div className="content-area">
        <div className="kpi-grid">{[
          ["Total Leads", (summary?.cold_leads || 0) + (summary?.warm_leads || 0), "Seluruh status"],
          ["Cold Leads", summary?.cold_leads || 0, "Belum di-assign ke sales"],
          ["Warm Leads", summary?.warm_leads || 0, "Sudah di-assign ke sales"],
          ["Admin Queue", summary?.admin_queue || 0, "Menunggu penanganan"],
        ].map(([label,value,sub]) => <article className="kpi" key={String(label)}><span>{label}</span><strong>{value}</strong><small>{sub}</small></article>)}</div>
        <div className="panel"><div className="panel-heading"><div><h3>Aktivitas percakapan</h3><p>Ringkasan kondisi operasional saat ini</p></div></div><div className="stats-row"><div><strong>{summary?.open_conversations || 0}</strong><span>Percakapan aktif</span></div><div><strong>{summary?.assigned_sales_conversations || 0}</strong><span>Ditangani sales</span></div><div><strong>{agents.length}</strong><span>Profil sales</span></div></div></div>
      </div>}
      {section === "leads" && isStaff && <div className="content-area"><div className="panel"><div className="panel-heading"><div><h3>Semua leads</h3><p>Cold tetap menunggu assignment; Warm sudah ditugaskan.</p></div><span className="count-pill">{leads.length} leads</span></div><div className="table-wrap"><table><thead><tr><th>Customer</th><th>Domisili</th><th>Unit</th><th>Tag</th><th>Status</th><th>Assign ke sales</th></tr></thead><tbody>{leads.map(l => <tr key={l.id}><td><b>{l.full_name || "Belum diketahui"}</b><small>{l.source}{l.is_simulated ? " · dummy" : ""}</small></td><td>{l.domicile || "—"}</td><td>{l.vehicle_interest || "—"}</td><td><span className={l.temperature === "warm" ? "tag warm" : "tag cold"}>{l.temperature}</span></td><td>{l.status}</td><td>{l.temperature === "cold" ? <select defaultValue="" onChange={e => e.target.value && assignLead(l.id,e.target.value)}><option value="">Pilih sales…</option>{agents.filter(a => a.is_available).map(a => <option key={a.id} value={a.id}>{a.display_name}</option>)}</select> : <span className="muted">Sudah ditugaskan</span>}</td></tr>)}</tbody></table></div></div></div>}
      {section === "admin_queue" && isStaff && <div className="content-area"><div className="panel"><div className="panel-heading"><div><h3>Menunggu tindakan admin</h3><p>AI sudah berhenti membalas. Pilih percakapan untuk ditangani.</p></div><span className="count-pill">{queue.length} antrean</span></div>{queue.length === 0 ? <div className="empty">Tidak ada percakapan dalam antrean.</div> : <div className="queue-list">{queue.map(q => <article className="queue-card" key={q.conversation_id}><div className="avatar">{(q.customer_name || "C").slice(0,1)}</div><div className="queue-info"><b>{q.customer_name || "Customer"}</b><span>{q.phone_number} · {q.domicile || "Domisili belum diketahui"} · {q.vehicle_interest || "Unit belum diketahui"}</span><small>Alasan: {q.handover_reason}</small></div><button className="secondary" onClick={() => claimQueue(q)}>Ambil antrean</button><button className="text-button" onClick={() => { const x=items.find(i=>i.id===q.conversation_id); if(x){setSelected(x);setSection("inbox");} else setNotice("Buka Inbox setelah data dimuat."); }}>Buka chat</button></article>)}</div>}</div></div>}
      {(section === "inbox" || section === "ai" || section === "sales" || section === "admin") && <div className="inbox-layout">
        <div className="conversation-list"><div className="list-head"><strong>Percakapan</strong><span>{visibleItems.length}</span></div>{visibleItems.map(item => <button key={item.id} className={selected?.id === item.id ? "conversation active" : "conversation"} onClick={() => setSelected(item)}><div className="avatar">{(item.customer_name || "C").slice(0,1)}</div><div className="conv-copy"><div className="conv-title"><b>{item.customer_name}</b><time>{fmt(item.last_message_at)}</time></div><p>{item.vehicle_interest || item.domicile || item.phone_number}</p><div className="conv-tags"><span className={item.temperature === "warm" ? "tag warm" : "tag cold"}>{item.temperature}</span><span className="tag neutral">{item.handler}</span>{item.is_simulated && <span className="tag neutral">dummy</span>}</div></div></button>)}</div>
        <div className="chat-panel">{selected ? <><div className="chat-head"><div className="avatar">{selected.customer_name.slice(0,1)}</div><div><b>{selected.customer_name}</b><span>{selected.phone_number} · {selected.domicile || "Domisili belum diisi"} · {selected.vehicle_interest || "Unit belum diisi"}</span></div><span className={selected.temperature === "warm" ? "tag warm" : "tag cold"}>{selected.temperature}</span></div><div className="messages">{messages.map(m => <div key={m.id} className={`bubble-row ${m.direction === "outbound" ? "outgoing" : ""}`}><div className={`bubble ${m.direction === "outbound" ? "out" : "in"}`}><small>{m.sender_type}</small><p>{m.content}</p><time>{m.created_at_wib || fmt(m.created_at)}</time></div></div>)}</div><form className="composer" onSubmit={sendMessage}><input value={messageText} onChange={e => setMessageText(e.target.value)} placeholder="Tulis balasan kepada customer…" /><button className="primary" disabled={busy || !messageText.trim()}>Kirim</button></form></> : <div className="empty">Pilih percakapan untuk melihat riwayat chat.</div>}</div>
      </div>}
      {section === "simulator" && isStaff && <div className="content-area"><div className="panel simulator-panel"><div className="panel-heading"><div><h3>Simulated WhatsApp</h3><p>Uji alur customer → AI → sales tanpa nomor WhatsApp asli.</p></div><button className="primary" onClick={createDummy}>＋ Customer dummy</button></div><div className="sim-toolbar"><select value={selectedContact} onChange={e => { setSelectedContact(e.target.value); loadSimChat(e.target.value); }}><option value="">Pilih customer dummy</option>{contacts.map(c => <option key={c.id} value={c.id}>{c.display_name} · {c.phone_number}</option>)}</select><button className="secondary" onClick={loadSimulator}>Refresh</button></div><div className="sim-note">Nomor customer dummy menggunakan prefix +62800. Tidak ada pesan yang dikirim ke WhatsApp sungguhan.</div><div className="sim-messages">{simMessages.map(m=><div key={m.id} className={`bubble-row ${m.direction === "outbound" ? "outgoing" : ""}`}><div className={`bubble ${m.direction === "outbound" ? "out" : "in"}`}><small>{m.sender_type}</small><p>{m.content}</p><time>{m.created_at_wib}</time></div></div>)}</div><form className="composer" onSubmit={sendAsCustomer}><input value={messageText} onChange={e => setMessageText(e.target.value)} placeholder="Ketik pesan sebagai customer…" /><button className="primary" disabled={busy || !selectedContact || !messageText.trim()}>Kirim sebagai customer</button></form></div></div>}
      {section === "settings" && isStaff && <div className="content-area"><div className="panel"><div className="panel-heading"><div><h3>Profil sales</h3><p>Daftar agent dan kapasitas lead saat ini.</p></div></div><div className="table-wrap"><table><thead><tr><th>Nama</th><th>Ketersediaan</th><th>Lead aktif</th><th>Kapasitas</th></tr></thead><tbody>{agents.map(a=><tr key={a.id}><td><b>{a.display_name}</b></td><td><span className={a.is_available ? "tag warm" : "tag cold"}>{a.is_available ? "Tersedia" : "Tidak tersedia"}</span></td><td>{a.active_leads}</td><td>{a.max_active_leads ?? "Tidak dibatasi"}</td></tr>)}</tbody></table></div></div><div className="panel"><div className="panel-heading"><div><h3>Wilayah & mapping</h3><p>Master wilayah dikelola melalui API; area sekitar tidak otomatis terpetakan.</p></div></div><TerritoryPanel canEdit={user.role_name === "admin"} /><WhatsAppStatusPanel /></div></div>}
    </section>
  </main>;
}

function TerritoryPanel({ canEdit }: { canEdit: boolean }) {
  const [territories,setTerritories]=useState<{id:string;name:string;aliases:string[];is_active:boolean}[]>([]);
  const [mappings,setMappings]=useState<{id:string;territory_id:string;agent_profile_id:string;priority:number}[]>([]);
  const [agents,setAgents]=useState<Agent[]>([]);
  const [name,setName]=useState("");
  const [aliases,setAliases]=useState("");
  const [territoryId,setTerritoryId]=useState("");
  const [agentId,setAgentId]=useState("");
  const [error,setError]=useState("");
  const refresh=useCallback(async()=>{const [t,m,a]=await Promise.all([api<typeof territories>("/territories"),api<typeof mappings>("/territory-mappings"),api<Agent[]>("/agents?active_only=false")]);setTerritories(t);setMappings(m);setAgents(a);},[]);
  useEffect(()=>{refresh().catch(e=>setError(e.message));},[refresh]);
  async function addTerritory(e:FormEvent){e.preventDefault();setError("");try{const t=await api<typeof territories[number]>("/territories",{method:"POST",body:JSON.stringify({name,aliases:aliases.split(",").map(x=>x.trim()).filter(Boolean),is_active:true})});setTerritories(old=>[...old,t]);setTerritoryId(t.id);setName("");setAliases("");}catch(e){setError(e instanceof Error?e.message:"Gagal menambah wilayah");}}
  async function addMapping(e:FormEvent){e.preventDefault();setError("");try{const m=await api<typeof mappings[number]>("/territory-mappings",{method:"POST",body:JSON.stringify({territory_id:territoryId,agent_profile_id:agentId,priority:1})});setMappings(old=>[...old,m]);setAgentId("");}catch(e){setError(e instanceof Error?e.message:"Gagal membuat mapping");}}
  return <div className="territory-wrap">
    {error&&<p className="alert">{error}</p>}
    <div className="territory-grid">{territories.map(t=><div className="territory" key={t.id}><b>{t.name}</b><span>{t.aliases.join(", ") || "Tanpa alias"}</span><small>{mappings.filter(m=>m.territory_id===t.id).map(m=>agents.find(a=>a.id===m.agent_profile_id)?.display_name || "Sales").join(", ") || "Belum ada mapping"}</small></div>)}</div>
    {canEdit&&<div className="management-forms">
      <form onSubmit={addTerritory} className="mini-form"><b>Tambah wilayah</b><input value={name} onChange={e=>setName(e.target.value)} placeholder="Nama wilayah, contoh: Medan Barat" required/><input value={aliases} onChange={e=>setAliases(e.target.value)} placeholder="Alias dipisahkan koma (opsional)"/><button className="secondary">Simpan wilayah</button></form>
      <form onSubmit={addMapping} className="mini-form"><b>Mapping sales</b><select value={territoryId} onChange={e=>setTerritoryId(e.target.value)} required><option value="">Pilih wilayah</option>{territories.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select><select value={agentId} onChange={e=>setAgentId(e.target.value)} required><option value="">Pilih sales</option>{agents.map(a=><option key={a.id} value={a.id}>{a.display_name}</option>)}</select><button className="secondary">Simpan mapping</button></form>
    </div>}
  </div>;
}

function WhatsAppStatusPanel() {
  const [status,setStatus]=useState<{app_env:string;provider:string;api_version:string;send_enabled:boolean;credentials_configured:Record<string,boolean>;credentials_complete:boolean;webhook_path:string;templates_supported:boolean;media_supported:boolean;production_activation_ready:boolean;note:string}|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{api<typeof status>("/integrations/whatsapp/status").then(setStatus).catch(e=>setError(e.message));},[]);
  return <div className="panel wa-status"><div className="panel-heading"><div><h3>WhatsApp Cloud API</h3><p>Readiness check — tanpa menampilkan token atau secret.</p></div><span className={status?.production_activation_ready?"tag warm":"tag cold"}>{status?.production_activation_ready?"Siap aktivasi":"Belum aktif"}</span></div>
    {error?<p className="muted">{error}</p>:status&&<><div className="wa-grid"><div><span>Environment</span><b>{status.app_env}</b></div><div><span>Provider aktif</span><b>{status.provider}</b></div><div><span>API version</span><b>{status.api_version}</b></div><div><span>Send switch</span><b>{status.send_enabled?"ON":"OFF"}</b></div></div><div className="credential-list">{Object.entries(status.credentials_configured).map(([key,value])=><span key={key}><i className={value?"ok":"missing"}/>{key.replaceAll("_"," ")}: {value?"terisi":"belum diisi"}</span>)}</div><p className="tiny">Webhook: {status.webhook_path}. Template: {status.templates_supported?"tersedia":"belum diimplementasikan"} · Media: {status.media_supported?"tersedia":"belum diimplementasikan"}.</p><p className="tiny">{status.note}</p></>}
  </div>;
}
