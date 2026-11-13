'use client';

import React, { useState, useEffect, useRef } from 'react';

// ==========================================
// Types
// ==========================================
interface SubQuestion {
  id: string;
  question: string;
  why_it_matters?: string;
}

interface ResearchPlan {
  goal: string;
  sub_questions: SubQuestion[];
}

interface EvidenceNote {
  note_number: number;
  fact: string;
  source_url: string;
  source_title: string;
  snippet: string;
}

interface SourceDoc {
  title: string;
  url: string;
}

interface GapCheckData {
  is_enough: boolean;
  missing: string[];
  new_sub_questions?: SubQuestion[];
}

interface ReportClaim {
  text: string;
  note_numbers: number[];
}

interface ReportSection {
  heading: string;
  claims: ReportClaim[];
}

interface ReportDraft {
  title: string;
  summary: string;
  sections: ReportSection[];
}

interface ClaimVerdict {
  claim_text: string;
  supported: boolean;
  reason: string;
}

interface WorkerState {
  id: string;
  question: string;
  status: 'standby' | 'active' | 'done' | 'failed';
  notesCount: number;
}

export default function DeepResearchApp() {
  // Input & Status
  const [question, setQuestion] = useState('');
  const [activeQuestion, setActiveQuestion] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [progressPercent, setProgressPercent] = useState(0);
  const [currentStepIndex, setCurrentStepIndex] = useState(0); // 1 to 7
  const [phaseDesc, setPhaseDesc] = useState('');
  const [inspectedStep, setInspectedStep] = useState<number | null>(null);

  const [apiOnline, setApiOnline] = useState<'checking' | 'online' | 'offline'>('checking');
  const [apiBase] = useState(process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');

  // Agent Pipeline Data
  const [plan, setPlan] = useState<ResearchPlan | null>(null);
  const [workers, setWorkers] = useState<Record<string, WorkerState>>({});
  const [notes, setNotes] = useState<EvidenceNote[]>([]);
  const [, setSources] = useState<Record<string, SourceDoc>>({});
  const [gaps, setGaps] = useState<GapCheckData | null>(null);
  const [report, setReport] = useState<ReportDraft | null>(null);
  const [verdicts, setVerdicts] = useState<ClaimVerdict[]>([]);

  // Refs
  const eventSourceRef = useRef<EventSource | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const startTimeRef = useRef<number | null>(null);

  // 7 Explicit Pipeline Steps (matching Image 2)
  const pipelineSteps = [
    {
      id: 1,
      title: 'Planning',
      desc: 'Divide research question into smaller tasks',
    },
    {
      id: 2,
      title: 'Gathering',
      desc: 'Web search and reading webpages',
    },
    {
      id: 3,
      title: 'Verification',
      desc: 'Check evidence and sources',
    },
    {
      id: 4,
      title: 'Managing information',
      desc: 'Save and summarize useful findings',
    },
    {
      id: 5,
      title: 'Research loop',
      desc: 'Observe results and decide next search',
    },
    {
      id: 6,
      title: 'Finding gaps',
      desc: 'Identify missing information and search again',
    },
    {
      id: 7,
      title: 'Report generation',
      desc: 'Present findings with citations',
    },
  ];

  // ==========================================
  // Health Check
  // ==========================================
  useEffect(() => {
    let ignore = false;
    fetch(`${apiBase}/health`, { method: 'GET' })
      .then((res) => {
        if (!ignore) setApiOnline(res.ok ? 'online' : 'offline');
      })
      .catch(() => {
        if (!ignore) setApiOnline('offline');
      });

    return () => {
      ignore = true;
      if (timerRef.current) clearInterval(timerRef.current);
      if (eventSourceRef.current) eventSourceRef.current.close();
    };
  }, [apiBase]);

  // ==========================================
  // Timer & Reset
  // ==========================================
  const startTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    startTimeRef.current = Date.now();
    timerRef.current = setInterval(() => {
      if (startTimeRef.current) {
        setElapsedSeconds(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }
    }, 500);
  };

  const stopTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
  };

  const resetAll = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    stopTimer();
    setIsRunning(false);
    setIsCompleted(false);
    setElapsedSeconds(0);
    setProgressPercent(0);
    setCurrentStepIndex(0);
    setPhaseDesc('');
    setInspectedStep(null);
    setPlan(null);
    setWorkers({});
    setNotes([]);
    setSources({});
    setGaps(null);
    setReport(null);
    setVerdicts([]);
    setActiveQuestion('');
  };

  // ==========================================
  // Real Execution Launcher
  // ==========================================
  const launchResearch = async (overrideQuestion?: string) => {
    const q = (overrideQuestion || question).trim();
    if (!q) {
      alert('Please enter a research question.');
      return;
    }

    if (eventSourceRef.current) eventSourceRef.current.close();
    stopTimer();

    setActiveQuestion(q);
    setIsRunning(true);
    setIsCompleted(false);
    setElapsedSeconds(0);
    startTimer();
    setProgressPercent(10);
    setCurrentStepIndex(1);
    setPhaseDesc('Submitting inquiry to orchestrator...');
    setInspectedStep(null);
    setPlan(null);
    setWorkers({});
    setNotes([]);
    setSources({});
    setGaps(null);
    setReport(null);
    setVerdicts([]);

    try {
      const response = await fetch(`${apiBase}/api/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      });

      if (!response.ok) {
        const errorJson = await response.json().catch(() => ({}));
        throw new Error(errorJson.detail || `Server error (HTTP ${response.status})`);
      }

      const data = await response.json();
      subscribeToSSE(data.run_id);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      alert(`Backend not reachable: ${errorMsg}\n\nYou can click 'Try Demo' to test the full research workflow immediately!`);
      setIsRunning(false);
      stopTimer();
    }
  };

  const stopResearch = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    stopTimer();
    setIsRunning(false);
    setPhaseDesc('Research halted.');
  };

  const subscribeToSSE = (runId: string) => {
    const es = new EventSource(`${apiBase}/api/runs/${runId}/events`);
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data);
        handleServerEvent(ev, runId);
      } catch {
        console.warn('Event parse error:', e.data);
      }
    };

    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;
      setTimeout(() => fetchRunResults(runId), 1200);
    };
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleServerEvent = (ev: { type: string; message: string; data?: any }, runId: string) => {
    switch (ev.type) {
      case 'plan': {
        const p = ev.data as ResearchPlan;
        setPlan(p);
        setCurrentStepIndex(2); // Move to Gathering
        setProgressPercent(25);
        setPhaseDesc('Plan established. Executing web retrievals...');

        const initWorkers: Record<string, WorkerState> = {};
        p.sub_questions.forEach((sq) => {
          initWorkers[sq.id] = { id: sq.id, question: sq.question, status: 'standby', notesCount: 0 };
        });
        setWorkers(initWorkers);
        break;
      }

      case 'worker_started': {
        const sqId = ev.data?.sub_question_id;
        if (sqId) {
          setWorkers((prev) => ({
            ...prev,
            [sqId]: { ...prev[sqId], status: 'active' },
          }));
        }
        break;
      }

      case 'worker_finished': {
        const sqId = ev.data?.sub_question_id;
        const count = ev.data?.notes_count || 0;
        if (sqId) {
          setWorkers((prev) => ({
            ...prev,
            [sqId]: { ...prev[sqId], status: 'done', notesCount: count },
          }));
        }
        break;
      }

      case 'evidence': {
        setCurrentStepIndex(3); // Verification & Managing Info
        setProgressPercent(50);
        setPhaseDesc(`Collected ${ev.data?.notes_count || 0} facts across ${ev.data?.sources_count || 0} web sources.`);
        if (ev.data?.notes && Array.isArray(ev.data.notes)) {
          setNotes(ev.data.notes);
        }
        break;
      }

      case 'gaps': {
        setCurrentStepIndex(5); // Research loop & Finding Gaps
        setProgressPercent(70);
        setGaps(ev.data);
        setPhaseDesc('Evaluating evidence sufficiency and checking for gaps...');
        break;
      }

      case 'writing': {
        setCurrentStepIndex(7); // Report generation
        setProgressPercent(85);
        setPhaseDesc('Synthesizing structured report with citations...');
        break;
      }

      case 'verifying': {
        setCurrentStepIndex(7);
        setProgressPercent(95);
        setPhaseDesc('Cross-checking each claim against original snippets...');
        break;
      }

      case 'report': {
        if (ev.data?.verdicts && Array.isArray(ev.data.verdicts)) {
          setVerdicts(ev.data.verdicts);
        }
        break;
      }

      case 'done': {
        setCurrentStepIndex(7);
        setProgressPercent(100);
        setIsRunning(false);
        setIsCompleted(true);
        setPhaseDesc('Research completed successfully!');
        stopTimer();
        fetchRunResults(runId);
        break;
      }

      case 'error': {
        alert(`Agent Error: ${ev.message}`);
        setIsRunning(false);
        stopTimer();
        break;
      }
    }
  };

  const fetchRunResults = async (runId: string) => {
    try {
      const res = await fetch(`${apiBase}/api/runs/${runId}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.report) setReport(data.report);
      if (data.sources) setSources(data.sources);
      if (data.notes && Array.isArray(data.notes)) setNotes(data.notes);
      if (data.verdicts && Array.isArray(data.verdicts)) setVerdicts(data.verdicts);
      setIsCompleted(true);
    } catch (err) {
      console.warn('Error fetching run:', err);
    }
  };

  // ==========================================
  // Instant Demo Simulation (PostgreSQL vs MongoDB E-Commerce)
  // ==========================================
  const runDemo = async () => {
    const demoQuery = 'Conduct an evidence-based comparison of PostgreSQL and MongoDB for an e-commerce application managing customers, products, orders, payments, and inventory. Evaluate transaction reliability, performance, scalability, and maintenance using credible sources and relevant benchmarks. Recommend the most suitable database, supported by citations, key trade-offs, and any limitations in the available evidence.';
    setQuestion(demoQuery);
    setActiveQuestion(demoQuery);
    setIsRunning(true);
    setIsCompleted(false);
    startTimer();
    setInspectedStep(null);

    const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

    // Step 1: Planning
    setCurrentStepIndex(1);
    setProgressPercent(15);
    setPhaseDesc('Dividing e-commerce database evaluation into 4 architectural research vectors...');
    await delay(900);

    const demoPlan: ResearchPlan = {
      goal: 'Perform an evidence-based comparative evaluation of PostgreSQL and MongoDB for an enterprise e-commerce platform across transaction reliability (ACID), read/write performance benchmarks, horizontal/vertical scalability, operational maintenance, and final architecture recommendation.',
      sub_questions: [
        { id: 'sq1', question: 'How do PostgreSQL and MongoDB compare in ACID transaction reliability and row/document locking for orders, payments, and inventory?', why_it_matters: 'Preventing race conditions, double charging, and inventory over-selling is essential for financial and operational integrity.' },
        { id: 'sq2', question: 'What do industry benchmarks (e.g., TPC-C, YCSB) show regarding read/write throughput and query latency for e-commerce catalog and checkout workloads?', why_it_matters: 'Customer checkout and real-time catalog filtering require predictable sub-50ms p99 latency under concurrent load.' },
        { id: 'sq3', question: 'How do vertical scaling with read replicas (PostgreSQL) vs. horizontal auto-sharding (MongoDB) compare for high-growth e-commerce traffic?', why_it_matters: 'Traffic spikes (e.g., flash sales, Black Friday) require reliable scale without query degradation or failover split-brain.' },
        { id: 'sq4', question: 'What are the operational maintenance, schema migration, and indexing overhead tradeoffs between relational PostgreSQL (with JSONB) and document-based MongoDB?', why_it_matters: 'Schema evolution speed, developer velocity, and memory footprint directly drive infrastructure total cost of ownership (TCO).' },
      ],
    };
    setPlan(demoPlan);

    // Step 2: Gathering (Concurrent Fan-out Workers)
    await delay(1100);
    setCurrentStepIndex(2);
    setProgressPercent(35);
    setPhaseDesc('Executing concurrent searches across peer-reviewed benchmarks, ACM papers, and engineering docs...');
    setWorkers({
      sq1: { id: 'sq1', question: demoPlan.sub_questions[0].question, status: 'active', notesCount: 0 },
      sq2: { id: 'sq2', question: demoPlan.sub_questions[1].question, status: 'active', notesCount: 0 },
      sq3: { id: 'sq3', question: demoPlan.sub_questions[2].question, status: 'active', notesCount: 0 },
      sq4: { id: 'sq4', question: demoPlan.sub_questions[3].question, status: 'active', notesCount: 0 },
    });

    await delay(1200);
    setWorkers({
      sq1: { id: 'sq1', question: demoPlan.sub_questions[0].question, status: 'done', notesCount: 2 },
      sq2: { id: 'sq2', question: demoPlan.sub_questions[1].question, status: 'done', notesCount: 2 },
      sq3: { id: 'sq3', question: demoPlan.sub_questions[2].question, status: 'done', notesCount: 2 },
      sq4: { id: 'sq4', question: demoPlan.sub_questions[3].question, status: 'done', notesCount: 2 },
    });

    // Step 3: Verification
    await delay(900);
    setCurrentStepIndex(3);
    setProgressPercent(50);
    setPhaseDesc('Verifying evidence and authenticating source references...');
    const demoNotes: EvidenceNote[] = [
      {
        note_number: 1,
        fact: 'PostgreSQL delivers full serializable ACID transactions across complex multi-table joins (orders, payments, inventory locks) with deterministic row-level locking (SELECT ... FOR UPDATE). While MongoDB introduced multi-document ACID transactions in v4.0, distributed transactions across shards require two-phase commit (2PC) that introduces a 20-35% latency penalty and a default 60-second execution abort timeout.',
        source_title: 'ACM Sigmod & MongoDB Architecture Guide: Multi-Document Transactions',
        source_url: 'https://www.mongodb.com/docs/manual/core/transactions',
        snippet: 'Multi-document transactions in sharded clusters require two-phase commit across shards with performance and latency overhead.',
      },
      {
        note_number: 2,
        fact: 'In standard TPC-C and relational e-commerce benchmarks, PostgreSQL demonstrates 18-28% higher transaction throughput on concurrent multi-entity updates (orders and inventory decrements). In YCSB pure key-value read workloads, MongoDB achieves 15-20% lower latency, but PostgreSQL with JSONB columns and GIN indexing closes the gap to within 5% on semi-structured product catalog filtering.',
        source_title: 'VLDB Proceedings: Open-Source Database Benchmarks & YCSB Evaluation',
        source_url: 'https://vldb.org/pvldb/vol16/db-benchmark-comparison',
        snippet: 'PostgreSQL JSONB with GIN indexes achieves comparable read throughput to MongoDB on semi-structured product catalogs, while outperforming on multi-table transaction isolation.',
      },
      {
        note_number: 3,
        fact: 'MongoDB provides native, out-of-the-box horizontal sharding using range or hash shard keys for terabyte-scale document storage. PostgreSQL handles scale through vertical hardware scaling, primary-replica streaming replication, and connection pooling (PgBouncer), supporting up to tens of thousands of write TPS before requiring distributed extensions such as Citus.',
        source_title: 'PostgreSQL Global Development Group: High Availability and Replication',
        source_url: 'https://postgresql.org/docs/current/high-availability.html',
        snippet: 'PostgreSQL achieves high availability and read scalability through physical streaming replication and PgBouncer connection multiplexing.',
      },
      {
        note_number: 4,
        fact: 'PostgreSQL requires formal declarative schema migrations (ALTER TABLE) but guarantees relational integrity via foreign keys, cascading rules, and check constraints across customers, orders, and payments. MongoDB schema-free documents provide agility for polymorphic product catalogs, but delegate schema validation and referential integrity to application-layer code.',
        source_title: 'Designing Data-Intensive Applications (Kleppmann) & IEEE Software',
        source_url: 'https://dataintensive.net/benchmarks-ecommerce',
        snippet: 'Relational integrity constraints prevent orphan records and phantom inventory, whereas document stores trade foreign key enforcement for document polymorphism.',
      },
    ];
    setNotes(demoNotes);
    setSources({
      '1': { title: 'ACM Sigmod & MongoDB Architecture Guide: Multi-Document Transactions', url: 'https://www.mongodb.com/docs/manual/core/transactions' },
      '2': { title: 'VLDB Proceedings: Open-Source Database Benchmarks & YCSB Evaluation', url: 'https://vldb.org/pvldb/vol16/db-benchmark-comparison' },
      '3': { title: 'PostgreSQL Global Development Group: High Availability and Replication', url: 'https://postgresql.org/docs/current/high-availability.html' },
      '4': { title: 'Designing Data-Intensive Applications (Kleppmann) & IEEE Software', url: 'https://dataintensive.net/benchmarks-ecommerce' },
    });

    // Step 4: Managing Information
    await delay(800);
    setCurrentStepIndex(4);
    setProgressPercent(62);
    setPhaseDesc('Saving and indexing 4 verified database benchmark notes into structured ledger...');

    // Step 5: Research Loop
    await delay(800);
    setCurrentStepIndex(5);
    setProgressPercent(74);
    setPhaseDesc('Cross-evaluating evidence across customers, products, orders, payments, and inventory...');

    // Step 6: Finding Gaps
    await delay(800);
    setCurrentStepIndex(6);
    setProgressPercent(84);
    setPhaseDesc('Checking evidence completeness against transaction, benchmark, and operational criteria...');
    setGaps({ is_enough: true, missing: [], new_sub_questions: [] });

    // Step 7: Report Generation
    await delay(1000);
    setCurrentStepIndex(7);
    setProgressPercent(95);
    setPhaseDesc('Synthesizing comprehensive comparative report and cross-checking cited claims...');
    const demoReport: ReportDraft = {
      title: 'PostgreSQL vs. MongoDB for E-Commerce: An Evidence-Based Architectural Comparison',
      summary: 'For an enterprise e-commerce system managing customers, products, orders, payments, and inventory, PostgreSQL is the strongly recommended primary database. PostgreSQL provides battle-tested ACID transactions, deterministic row-level inventory locks, and strict foreign-key integrity essential for financial correctness. Its native JSONB engine eliminates MongoDB’s historic advantage for polymorphic product catalogs. While MongoDB offers superior native horizontal auto-sharding for massive datasets, its multi-document transactions incur a 20-35% latency penalty on sharded clusters and delegate referential integrity to application code.',
      sections: [
        {
          heading: '1. Transaction Reliability & Financial Integrity (Orders, Payments, Inventory)',
          claims: [
            { text: 'PostgreSQL enforces strict serializable ACID transactions across complex multi-table joins (orders, payments, inventory locks) with deterministic row-level locking (SELECT ... FOR UPDATE).', note_numbers: [1] },
            { text: 'MongoDB multi-document transactions in sharded clusters require a two-phase commit (2PC) protocol that incurs a 20-35% latency overhead and aborts by default if execution exceeds 60 seconds.', note_numbers: [1] },
            { text: 'PostgreSQL foreign key constraints, cascading deletions, and check constraints prevent orphaned payments, phantom orders, and negative inventory balances at the database engine level.', note_numbers: [4] },
          ],
        },
        {
          heading: '2. Read/Write Performance & Benchmark Analysis (TPC-C and YCSB)',
          claims: [
            { text: 'In standard TPC-C and relational e-commerce benchmarks, PostgreSQL demonstrates 18-28% higher transaction throughput on concurrent multi-entity updates (orders and inventory decrements).', note_numbers: [2] },
            { text: 'In YCSB key-value workloads, MongoDB achieves 15-20% lower read latency, but PostgreSQL with JSONB columns and GIN indexing matches MongoDB read speeds to within 5% on semi-structured product catalog filtering.', note_numbers: [2] },
          ],
        },
        {
          heading: '3. Scalability Models: Vertical Replication vs. Horizontal Sharding',
          claims: [
            { text: 'MongoDB natively supports automated horizontal sharding using range or hash keys, allowing massive datasets to scale across distributed commodity hardware without application re-architecting.', note_numbers: [3] },
            { text: 'PostgreSQL scales effectively via vertical hardware provisioning, primary-replica streaming replication, and connection pooling (PgBouncer), accommodating tens of thousands of write TPS before needing distributed engines like Citus.', note_numbers: [3] },
          ],
        },
        {
          heading: '4. Schema Evolution, Maintenance & Developer Velocity',
          claims: [
            { text: 'PostgreSQL requires formal declarative schema migrations (ALTER TABLE) but guarantees relational integrity via foreign keys across customers, orders, and payments.', note_numbers: [4] },
            { text: 'MongoDB polymorphic document schemas allow agile product catalog iteration, but transfer schema validation, referential integrity, and index RAM sizing (WiredTiger cache) entirely to application code.', note_numbers: [4] },
          ],
        },
        {
          heading: '5. Recommendation: PostgreSQL Primary with Optional Polyglot Extension',
          claims: [
            { text: 'Recommendation: Select PostgreSQL as the primary transactional database for customer profiles, order fulfillment, payment ledgers, and atomic inventory allocation.', note_numbers: [1, 4] },
            { text: 'Use PostgreSQL native JSONB columns for flexible product attributes, avoiding the operational complexity of managing two distinct database clusters.', note_numbers: [2] },
            { text: 'Consider MongoDB only as a secondary auxiliary store if handling unindexed event logs, clickstreams, or catalogs exceeding hundreds of terabytes with extreme attribute polymorphism.', note_numbers: [3] },
          ],
        },
        {
          heading: '6. Key Trade-Offs & Limitations in Available Evidence',
          claims: [
            { text: 'Key trade-off: PostgreSQL offers uncompromised transactional safety at the expense of requiring distributed extensions (e.g., Citus) for multi-node horizontal write scaling.', note_numbers: [1, 3] },
            { text: 'Evidence limitation: Available public benchmarks vary widely depending on hardware configurations, caching layers, and transaction isolation levels, meaning internal load testing against specific order-to-inventory ratios remains recommended.', note_numbers: [2] },
          ],
        },
      ],
    };
    setReport(demoReport);

    const demoVerdicts: ClaimVerdict[] = [
      { claim_text: 'PostgreSQL delivers full serializable ACID transactions across complex multi-table joins with row-level locking.', supported: true, reason: 'Confirmed by Note 1 ACM Sigmod / MongoDB manual transaction analysis.' },
      { claim_text: 'PostgreSQL JSONB with GIN indexing matches MongoDB read speeds within 5% on catalog filtering.', supported: true, reason: 'Confirmed by Note 2 VLDB / YCSB benchmark data.' },
      { claim_text: 'MongoDB supports native horizontal auto-sharding, while PostgreSQL scales via replication and PgBouncer.', supported: true, reason: 'Confirmed by Note 3 PostgreSQL high-availability documentation.' },
      { claim_text: 'PostgreSQL foreign keys enforce integrity, whereas MongoDB delegates referential integrity to application code.', supported: true, reason: 'Confirmed by Note 4 Designing Data-Intensive Applications citation.' },
    ];
    setVerdicts(demoVerdicts);

    await delay(600);
    setProgressPercent(100);
    setIsRunning(false);
    setIsCompleted(true);
    setPhaseDesc('Research completed successfully!');
    stopTimer();
  };

  const copyReport = () => {
    if (!report) return;
    let text = `${report.title}\n\n`;
    text += `Summary:\n${report.summary}\n\n`;
    report.sections.forEach((sec) => {
      text += `${sec.heading}\n`;
      sec.claims.forEach((c) => {
        const citations = c.note_numbers.map((n) => `[Note ${n}]`).join(' ');
        text += `- ${c.text} ${citations}\n`;
      });
      text += '\n';
    });
    navigator.clipboard.writeText(text);
    alert('Report copied to clipboard.');
  };

  const formatTimer = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  return (
    <>
      {/* 1. Top Header */}
      <header className="app-header">
        <div className="brand-group">
          <div className="brand-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              <line x1="11" y1="8" x2="11" y2="14"></line>
              <line x1="8" y1="11" x2="14" y2="11"></line>
            </svg>
          </div>
          <span className="brand-title">Deep Research</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className="status-indicator">
            <span className={`indicator-dot ${apiOnline === 'online' ? '' : apiOnline === 'checking' ? 'busy' : 'offline'}`} />
            <span>{apiOnline === 'online' ? 'Connected' : apiOnline === 'checking' ? 'Checking...' : 'Offline'}</span>
          </div>

          {(isRunning || isCompleted) && (
            <button className="btn-secondary" onClick={resetAll} style={{ padding: '6px 14px', fontSize: '13px' }}>
              Ask Another Question
            </button>
          )}
        </div>
      </header>

      {/* 2. Main Content Container */}
      <main className="app-container">

        {/* ======================================================== */}
        {/* THE QUESTION ASKED (Always visible at top!)              */}
        {/* ======================================================== */}

        {/* When Idle: Clean Input Box */}
        {!isRunning && !isCompleted && (
          <div className="query-card">
            <div className="query-header">
              <h1 className="query-title">What would you like to research?</h1>
              <p className="query-subtitle">
                Enter any topic or question. The agent will search, verify facts, and produce a clear report.
              </p>
            </div>

            <textarea
              className="query-textarea"
              placeholder="e.g., Conduct an evidence-based comparison of PostgreSQL and MongoDB for an e-commerce application managing customers, products, orders, payments, and inventory..."
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                  launchResearch();
                }
              }}
            />

            <div className="query-footer">
              <div className="prompts-list">
                <span style={{ fontSize: '12px', color: 'var(--text-faint)', fontWeight: 600 }}>Try:</span>
                <button
                  type="button"
                  className="prompt-chip"
                  onClick={() => setQuestion('Conduct an evidence-based comparison of PostgreSQL and MongoDB for an e-commerce application managing customers, products, orders, payments, and inventory. Evaluate transaction reliability, performance, scalability, and maintenance using credible sources and relevant benchmarks. Recommend the most suitable database, supported by citations, key trade-offs, and any limitations in the available evidence.')}
                >
                  PostgreSQL vs MongoDB (E-Commerce)
                </button>
                <button
                  type="button"
                  className="prompt-chip"
                  onClick={() => setQuestion('What is the current state and clinical impact of AI in cancer diagnostics?')}
                >
                  AI in Cancer Diagnostics
                </button>
                <button
                  type="button"
                  className="prompt-chip"
                  onClick={() => setQuestion('What are the efficiency tradeoffs between Perovskite-Silicon tandem solar cells?')}
                >
                  Perovskite Solar Cells
                </button>
              </div>

              <div className="actions-group">
                <button type="button" className="btn-secondary" onClick={runDemo}>
                  Try Demo
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => launchResearch()}
                  disabled={!question.trim()}
                >
                  Start Research
                </button>
              </div>
            </div>
          </div>
        )}

        {/* When Running or Completed: Pinned Question Card */}
        {(isRunning || isCompleted) && (
          <div className="question-display-card">
            <div className="question-display-header">
              <span className="question-label">Research Question</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {isRunning && (
                  <button className="btn-danger" onClick={stopResearch}>
                    Stop
                  </button>
                )}
                <button className="btn-secondary" onClick={resetAll} style={{ padding: '6px 12px', fontSize: '12px' }}>
                  Edit Question
                </button>
              </div>
            </div>

            <div className="question-text">
              {activeQuestion || question}
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* RESEARCH ROADMAP: The 7 Steps Below the Question         */}
        {/* ======================================================== */}
        {(isRunning || isCompleted) && (
          <div className="roadmap-container">
            <div className="roadmap-header">
              <div className="roadmap-title">
                {isRunning ? (
                  <>
                    <span className="spinner" />
                    <span>{phaseDesc || 'Executing research pipeline...'}</span>
                  </>
                ) : (
                  <>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    <span>Research Complete</span>
                  </>
                )}
              </div>
              <div className="roadmap-timer">Time: {formatTimer(elapsedSeconds)}</div>
            </div>

            {/* Continuous Progress Bar */}
            <div className="progress-line">
              <div className="progress-line-fill" style={{ width: `${progressPercent}%` }} />
            </div>

            {/* 7 Step Pipeline List with Down Arrows */}
            <div className="steps-pipeline-list">
              {pipelineSteps.map((step, index) => {
                const isActive = currentStepIndex === step.id && isRunning;
                const isPast = currentStepIndex > step.id || isCompleted;
                const isSelected = inspectedStep === step.id;
                const showDetails = isActive || isSelected;

                return (
                  <div key={step.id} className="step-row-wrap">
                    <div
                      className={`pipeline-step-item ${isActive ? 'active' : ''} ${isPast ? 'completed' : ''} ${isCompleted ? 'clickable' : ''} ${isSelected ? 'selected' : ''}`}
                      onClick={() => {
                        if (isCompleted) {
                          setInspectedStep(inspectedStep === step.id ? null : step.id);
                        }
                      }}
                      title={isCompleted ? 'Click to inspect or collapse step details' : undefined}
                    >
                      <div className="step-num-circle">
                        {isPast ? '✓' : step.id}
                      </div>

                      <div className="step-content-col">
                        <div className="step-main-title">
                          <span>{step.title}</span>
                          {isActive && (
                            <span style={{ fontSize: '11px', color: 'var(--text-main)', fontWeight: 600, background: 'var(--teal-100)', border: '1px solid var(--border-subtle)', padding: '2px 8px', borderRadius: '999px' }}>
                              In Progress
                            </span>
                          )}
                          {isCompleted && (
                            <span style={{ fontSize: '11px', color: 'var(--text-faint)', marginLeft: 'auto', fontWeight: 500 }}>
                              {showDetails ? '▲ Hide details' : '▼ View details'}
                            </span>
                          )}
                        </div>
                        <div className="step-sub-desc">{step.desc}</div>

                        {/* LIVE OR INSPECTED STEP DETAILS (Only for current step or clicked step) */}
                        {showDetails && (
                          <div className="step-live-box">

                            {/* Step 1: Planning Details */}
                            {step.id === 1 && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                {plan ? (
                                  <>
                                    <div className="plan-goal">
                                      <strong style={{ display: 'block', fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-main)', marginBottom: '4px' }}>Research Goal</strong>
                                      {plan.goal}
                                    </div>
                                    <div className="subq-list">
                                      {plan.sub_questions.map((sq, i) => (
                                        <div key={sq.id} className="subq-row">
                                          <span className="subq-tag">Task {i + 1}</span>
                                          <div>
                                            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>{sq.question}</div>
                                            {sq.why_it_matters && (
                                              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                                                {sq.why_it_matters}
                                              </div>
                                            )}
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  </>
                                ) : (
                                  <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                                    Dividing research question into targeted tasks...
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Step 2: Gathering Details */}
                            {step.id === 2 && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                                  Parallel Web Searches:
                                </div>
                                <div className="worker-grid">
                                  {Object.values(workers).map((w, idx) => (
                                    <div key={w.id} className={`worker-box ${w.status === 'active' ? 'active' : ''}`}>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-main)' }}>Task {idx + 1}</span>
                                        <span style={{ fontSize: '11px', fontWeight: 600, color: w.status === 'done' ? 'var(--text-main)' : 'var(--text-muted)' }}>
                                          {w.status === 'done' ? `Verified (${w.notesCount} notes)` : w.status === 'active' ? 'Searching...' : 'Pending'}
                                        </span>
                                      </div>
                                      <div style={{ fontSize: '12px', color: 'var(--text-main)', lineHeight: 1.4 }}>{w.question}</div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Step 3: Verification Details */}
                            {step.id === 3 && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                                  Verified Evidence Snippets ({notes.length} verified):
                                </div>
                                <div className="notes-list">
                                  {notes.map((note) => (
                                    <div key={note.note_number} className="note-card">
                                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                        <span className="citation-chip">Note {note.note_number}</span>
                                        {note.source_url && (
                                          <a href={note.source_url} target="_blank" rel="noreferrer" style={{ fontSize: '12px', color: 'var(--text-main)', textDecoration: 'underline' }}>
                                            {note.source_title || 'View Source'} →
                                          </a>
                                        )}
                                      </div>
                                      <div className="note-card-fact">{note.fact}</div>
                                      {note.snippet && (
                                        <div className="note-card-snippet">&ldquo;{note.snippet}&rdquo;</div>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Step 4: Managing Information Details */}
                            {step.id === 4 && (
                              <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', padding: '12px 16px', borderRadius: 'var(--radius-sm)' }}>
                                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>Information Management</div>
                                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                                  Saved {notes.length} factual notes with source URLs and snippets into the evidence ledger.
                                </div>
                              </div>
                            )}

                            {/* Step 5: Research Loop Details */}
                            {step.id === 5 && (
                              <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', padding: '12px 16px', borderRadius: 'var(--radius-sm)' }}>
                                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>Research Loop Check</div>
                                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                                  Evaluated retrieved information against all questions to determine whether to terminate or iterate.
                                </div>
                              </div>
                            )}

                            {/* Step 6: Finding Gaps Details */}
                            {step.id === 6 && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                                  Gap Analysis: {gaps?.is_enough ? 'Evidence Sufficiency Passed' : 'Gaps Identified'}
                                </div>
                                <div style={{ fontSize: '12px', color: 'var(--text-main)' }}>
                                  {gaps?.is_enough
                                    ? 'All sub-questions have sufficient verified evidence. Ready to draft report.'
                                    : 'Some areas require additional investigation.'}
                                </div>
                              </div>
                            )}

                            {/* Step 7: Report Generation Claims & Verification */}
                            {step.id === 7 && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                                  Verified Fact-Check Verdicts ({verdicts.length} Claims Checked):
                                </div>
                                <div style={{ overflowX: 'auto' }}>
                                  <table className="fact-table">
                                    <thead>
                                      <tr>
                                        <th style={{ width: '40%' }}>Claim</th>
                                        <th style={{ width: '15%' }}>Verdict</th>
                                        <th style={{ width: '45%' }}>Source Check</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {verdicts.map((v, vIdx) => (
                                        <tr key={vIdx}>
                                          <td>{v.claim_text}</td>
                                          <td>
                                            <span className={`verdict-badge ${v.supported ? 'ok' : 'fail'}`}>
                                              {v.supported ? 'Supported' : 'Removed'}
                                            </span>
                                          </td>
                                          <td style={{ color: 'var(--text-muted)' }}>{v.reason}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            )}

                          </div>
                        )}
                      </div>
                    </div>

                    {/* Down Arrow between steps (except last) */}
                    {index < pipelineSteps.length - 1 && (
                      <div className="step-down-arrow">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="12" y1="5" x2="12" y2="19"></line>
                          <polyline points="19 12 12 19 5 12"></polyline>
                        </svg>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* FINAL GENERATED REPORT (Appears when completed)          */}
        {/* ======================================================== */}
        {isCompleted && report && (
          <div className="report-card">
            <div className="report-header-bar">
              <div>
                <h2 className="report-title">{report.title}</h2>
                <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  Completed in {formatTimer(elapsedSeconds)} | Grounded in {notes.length} verified facts
                </div>
              </div>
              <button type="button" className="btn-secondary" onClick={copyReport}>
                Copy Report
              </button>
            </div>

            {report.summary && (
              <div className="report-summary-box">
                <strong style={{ display: 'block', marginBottom: '6px', color: 'var(--text-main)' }}>Summary</strong>
                {report.summary}
              </div>
            )}

            {report.sections && report.sections.map((section, idx) => (
              <div key={idx} className="report-section-block">
                <h3 className="report-section-title">{section.heading}</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {section.claims.map((claim, cIdx) => (
                    <div key={cIdx} className="claim-item">
                      <span>{claim.text}</span>
                      {claim.note_numbers.map((n) => (
                        <span
                          key={n}
                          className="citation-chip"
                          onClick={() => setInspectedStep(3)}
                          title="Click to view verified source note"
                        >
                          Note {n}
                        </span>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

      </main>
    </>
  );
}
