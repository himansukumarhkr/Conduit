# Conduit — Complete Project Handover & Context

> **Instructions for the New Agent:**  
> This file contains the complete, 100% coverage context, technical design, architecture, and roadmap for **Conduit**. Read this document to understand the entire background, requirements, and next steps without needing any past chat history.

---

## 1. Project Genesis & Vision

* **Project Name:** Conduit
* **Workspace Path:** `c:\Users\himan\.gemini\antigravity\scratch\TestFlowStudio`
* **Target Audience:** Bridging Functional / Manual Testers and Automation Engineers.
* **Why This Exists:**
  * In enterprise software testing, functional testers possess deep business domain expertise but lack automation coding skills.
  * Automation engineers spend up to 70% of their time writing repetitive locator boilerplate and translating manual test cases into code.
  * Traditional codegen tools (like raw `playwright codegen` or Cypress Studio) generate unmaintainable, brittle "spaghetti code" (hardcoded absolute XPaths, raw strings, zero assertions, no Page Object Model).
  * Commercial low-code tools (Katalon, Tosca, TestComplete) lock teams into proprietary, closed-source databases and costly licensing.
* **The Solution:**  
  A **Code-First Low-Code Desktop Application** that allows functional testers to record and run end-to-end browser tests via an intuitive UI, while an underlying AST engine synthesizes clean, production-grade **Page Object Model (POM)** Python/Playwright scripts that automation engineers can commit to Git and run in CI/CD without vendor lock-in.

---

## 2. Core Architectural Pillars

```
┌─────────────────────────────────────────────────────────────┐
│                 Conduit.exe (Single .exe)                   │
├─────────────────────────────────────────────────────────────┤

│ 1. Desktop UI Layer      → High-performance GUI window      │
│ 2. Embedded Runtime       → Bundled Python engine (No setup) │
│ 3. Core Automation Hub   → Playwright & Pytest Engine        │
│ 4. Native Browser Bridge → Uses system Edge / Chrome        │
└─────────────────────────────────────────────────────────────┘
```

### Pillar 1: Smart Ingestion & Selector Ranking
* Intercepts browser actions (via Playwright / Chrome DevTools Protocol).
* Ranks locators automatically by durability:
  1. `data-testid` / `data-qa`
  2. Semantic Role + Accessible Name (`page.get_by_role("button", name="Submit")`)
  3. Label / Text (`page.get_by_label(...)`, `page.get_by_text(...)`)
  4. Stable relative CSS (never deep absolute XPaths).
* **Assertion Injection Overlay:** During recording, manual testers can right-click / Alt+Click any element to inject expectations:
  * `Assert Visible`
  * `Assert Text Equals`
  * `Assert Value`

### Pillar 2: AST Normalizer & POM Synthesizer (The Core Differentiator)
* A Python AST (Abstract Syntax Tree) engine transforms raw recorded browser actions into clean Page Object Model architecture:
  * Groups locators by page URL into dedicated classes (`LoginPage.py`, `CheckoutPage.py`).
  * Deduplicates locators and methods across tests.
  * Auto-extracts hardcoded test data (usernames, search terms) into external JSON fixtures or datasets.

### Pillar 3: Desktop UI Layout (Mockup in `docs/desktop_ui_mockup.jpg`)
* **Top Control Bar:** Environment switcher (`QA` / `Staging` / `Prod`), 1-click `[Record New Flow]`, `[Run Selected]`, Browser toggles (Chrome, Edge, Headless mode).
* **Left Sidebar:** Navigation between Test Catalog, Recorder, Suites & Tags, Execution History, Settings.
* **Central Table:** Test scenarios with tag badges (`@smoke`, `@regression`, `@checkout`), pass/fail status, duration, and 1-click run/edit icons.
* **Dual-View Test Inspector (Right Panel):**
  * *Functional View:* Plain English steps (e.g., `1. Navigate to /login`, `2. Fill email input`, `3. Click Submit`, `4. Assert success message visible`).
  * *Engineer View:* "Show Code" toggle revealing the auto-generated clean Python POM code.
* **Bottom Console:** Live execution progress bar, real-time log streaming, and links to Playwright Trace Viewer and video replays.

### Pillar 4: Bidirectional Import & Export (Zero Vendor Lock-in)
* **Export:**
  * Standard Pytest-Playwright or TypeScript-Playwright code files.
  * CI/CD pipelines (`.github/workflows/e2e.yml`, GitLab CI, Jenkinsfile).
  * Portable `.zip` test suite bundles and Allure/Playwright HTML executive reports.
* **Import:**
  * Existing Playwright `.py` / `.ts` scripts (reverse-parsed into visual UI steps via AST).
  * Datasets (`.csv`, `.xlsx`, `.json`) for data-driven testing.
  * BDD Feature files (`.feature` Gherkin format).
  * Direct Git clone & pull.

### Pillar 5: Windows Single Executable Packaging
* Packaged as a **single standalone executable (`Conduit.exe`)** with zero installation steps.
* Bundles an embedded Python runtime.
* Hooks natively into pre-installed **Microsoft Edge** or **Google Chrome** (`channel="msedge"` / `channel="chrome"`), avoiding heavy 400MB browser downloads.
* Runs without Windows UAC administrator privileges.

---

## 3. Files Already Initialized on Disk

Inside `c:\Users\himan\.gemini\antigravity\scratch\TestFlowStudio`:
1. `README.md` — Project overview and architecture.
2. `docs/desktop_ui_mockup.jpg` — High-resolution visual mockup of the desktop UI.
3. `.agents/AGENTS.md` — Agent rules:
   * Work strictly on `main` branch.
   * Dedicated exclusively to Conduit (zero references/cross-work on Click or GhostKey).
4. `HANDOVER_CONTEXT.md` — This file.

---

## 4. Immediate Next Decisions & Roadmap

When starting the new conversation inside `TestFlowStudio`:

1. **Tech Stack Selection:**
   * **Option A (Pure Python - Fastest Build):** `PyQt6` / `PySide6` or `CustomTkinter` UI + `pytest-playwright` runner $\rightarrow$ compiles to single `.exe` via `PyInstaller`.
   * **Option B (Web UI + Desktop Shell - Most Modern Look):** `Tauri` (Rust/Webview2) or `Electron` + `React / Tailwind` UI + Python automation sidecar.
2. **Phase 1 Implementation Steps:**
   * Step 1: Build the Smart Recorder script wrapping Playwright.
   * Step 2: Build the AST Normalizer that generates POM classes and Pytest specs.
   * Step 3: Implement the Desktop UI shell matching the mockup layout in `docs/desktop_ui_mockup.jpg`.
   * Step 4: Integrate the live test runner with WebSocket/IPC log streaming.
