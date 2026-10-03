let appState = {
  currentEnv: "QA",
  selectedBrowser: "msedge",
  headless: true,
  scenarios: [],
  selectedScenarioId: "sc_001",
  selectedCheckboxIds: new Set(["sc_001", "sc_002", "sc_003"]),
  isExecuting: false
};

document.addEventListener("DOMContentLoaded", () => {
  if (window.pywebview && window.pywebview.api) {
    loadScenariosFromBackend();
  } else {
    window.addEventListener("pywebviewready", () => {
      loadScenariosFromBackend();
    });
  }

  setTimeout(() => {
    if (appState.scenarios.length === 0) {
      loadInitialSeedData();
    }
  }, 100);
});

async function loadScenariosFromBackend() {
  try {
    const list = await window.pywebview.api.get_scenarios();
    if (list && list.length > 0) {
      appState.scenarios = list;
      renderTable();
      selectScenario(appState.selectedScenarioId || list[0].id);
    }
  } catch (err) {
    console.error("Backend fetch error:", err);
  }
}

function loadInitialSeedData() {
  appState.scenarios = [
    {
      id: "sc_001",
      name: "User Login Flow",
      tags: ["@smoke", "@regression"],
      last_execution: "5 min ago",
      status: "Passed",
      duration: "1min 20s",
      file_name: "test_user_login_flow.py",
      steps: [
        { human_description: "1. Navigate to /login" },
        { human_description: "2. Fill 'email' input" },
        { human_description: "3. Fill 'password' input" },
        { human_description: "4. Click 'Submit' button" },
        { human_description: "5. Assert success message visible" }
      ],
      code: `class LoginPage:
    def fill_email(self, email):
        self.find_element(By.ID, 'email').fill(email)

    def fill_password(self, password):
        self.find_element(By.ID, 'password').fill(password)

    def click_submit(self):
        self.find_element(By.ID, 'submit').click()

    def assert_success_message_visible(self):
        expect(self.success_msg).to_be_visible()`
    },
    {
      id: "sc_002",
      name: "Add Item to Cart",
      tags: ["@smoke", "@checkout"],
      last_execution: "5 min ago",
      status: "Failed",
      duration: "45s",
      file_name: "test_add_item_checkout.py",
      steps: [
        { human_description: "1. Navigate to /catalog" },
        { human_description: "2. Click 'Add to Cart' button" },
        { human_description: "3. Assert cart counter equals '1'" }
      ],
      code: `class CatalogPage:
    def add_to_cart(self):
        self.page.get_by_role("button", name="Add to Cart").click()

    def assert_cart_count(self, expected):
        expect(self.page.locator(".cart-badge")).to_have_text(expected)`
    },
    {
      id: "sc_003",
      name: "Add Item to Cart",
      tags: ["@smoke", "@regression"],
      last_execution: "3 min ago",
      status: "Passed",
      duration: "45s",
      file_name: "test_add_item_regression.py",
      steps: [
        { human_description: "1. Navigate to /catalog" },
        { human_description: "2. Select quantity '2'" },
        { human_description: "3. Click 'Add to Cart' button" },
        { human_description: "4. Assert cart badge visible" }
      ],
      code: `class CartPage:
    def verify_badge(self):
        expect(self.page.locator(".badge")).to_be_visible()`
    },
    {
      id: "sc_004",
      name: "Assert Item Management",
      tags: ["@smoke", "@checkout"],
      last_execution: "2 min ago",
      status: "Passed",
      duration: "45s",
      file_name: "test_item_mgmt.py",
      steps: [
        { human_description: "1. Navigate to /admin/items" },
        { human_description: "2. Assert items table visible" },
        { human_description: "3. Click 'Filter by Active'" }
      ],
      code: `class AdminPage:
    def filter_active(self):
        self.page.locator("#filter-active").click()`
    },
    {
      id: "sc_005",
      name: "Assert success message Flow",
      tags: ["@regression"],
      last_execution: "3 min ago",
      status: "Passed",
      duration: "1min 20s",
      file_name: "test_success_flow.py",
      steps: [
        { human_description: "1. Fill 'Feedback' form" },
        { human_description: "2. Click 'Submit Feedback'" },
        { human_description: "3. Assert toast contains 'Success'" }
      ],
      code: `class FeedbackPage:
    def submit_feedback(self, text):
        self.page.locator("textarea").fill(text)
        self.page.locator("button.submit").click()`
    },
    {
      id: "sc_006",
      name: "Assert Login Flow",
      tags: ["@checkout"],
      last_execution: "3 min ago",
      status: "Passed",
      duration: "45s",
      file_name: "test_assert_login.py",
      steps: [
        { human_description: "1. Navigate to /checkout" },
        { human_description: "2. Assert login required prompt visible" }
      ],
      code: `class CheckoutPage:
    def assert_login_prompt(self):
        expect(self.page.locator(".login-prompt")).to_be_visible()`
    },
    {
      id: "sc_007",
      name: "Assert success message",
      tags: ["@smoke", "@failed"],
      last_execution: "1 min ago",
      status: "Passed",
      duration: "1min 20s",
      file_name: "test_assert_msg.py",
      steps: [
        { human_description: "1. Trigger alert message" },
        { human_description: "2. Assert banner visible" }
      ],
      code: `class AlertPage:
    def check_banner(self):
        expect(self.page.locator(".alert-banner")).to_be_visible()`
    }
  ];

  renderTable();
  selectScenario("sc_001");
}

function renderTable() {
  const tbody = document.getElementById("test-table-body");
  tbody.innerHTML = "";

  appState.scenarios.forEach((sc) => {
    const tr = document.createElement("tr");
    tr.id = `row-${sc.id}`;
    if (sc.id === appState.selectedScenarioId) {
      tr.classList.add("selected");
    }

    const isChecked = appState.selectedCheckboxIds.has(sc.id);

    const tagsHtml = (sc.tags || []).map(t => {
      const clean = t.replace("@", "");
      let cls = "tag-smoke";
      if (clean === "regression" || clean === "checkout") cls = "tag-regression";
      if (clean === "failed") cls = "tag-failed";
      return `<span class="tag-badge ${cls}">${t}</span>`;
    }).join("");

    const isPassed = sc.status === "Passed";
    const statusHtml = isPassed 
      ? `<span class="status-badge status-passed">Passed</span>`
      : `<span class="status-badge status-failed">Failed</span>`;

    tr.innerHTML = `
      <td style="width: 32px;" onclick="event.stopPropagation()">
        <input type="checkbox" class="custom-checkbox" ${isChecked ? "checked" : ""} onchange="toggleSelectTest('${sc.id}', this.checked)">
      </td>
      <td style="font-weight: 500;">${sc.name}</td>
      <td>${tagsHtml}</td>
      <td style="color: var(--text-dim);">${sc.last_execution || 'Never'}</td>
      <td>${statusHtml}</td>
      <td style="color: var(--text-dim);">${sc.duration || '--'}</td>
      <td style="text-align: right; padding-right: 20px;" onclick="event.stopPropagation()">
        <div class="row-actions" style="justify-content: flex-end;">
          <span class="action-icon" title="Run Scenario" onclick="runSingleTest('${sc.id}')">▶</span>
          <span class="action-icon" title="Edit Scenario" onclick="editScenario('${sc.id}')">✏</span>
          <span class="action-icon" title="More Options">•••</span>
        </div>
      </td>
    `;

    tr.onclick = () => selectScenario(sc.id);
    tbody.appendChild(tr);
  });
}

function selectScenario(scenarioId) {
  appState.selectedScenarioId = scenarioId;
  const sc = appState.scenarios.find(s => s.id === scenarioId);
  if (!sc) return;

  document.querySelectorAll(".test-table tbody tr").forEach(tr => tr.classList.remove("selected"));
  const row = document.getElementById(`row-${scenarioId}`);
  if (row) row.classList.add("selected");

  document.getElementById("steps-header-title").textContent = `Flow Steps: ${sc.name}`;
  const stepsContainer = document.getElementById("steps-container");
  stepsContainer.innerHTML = "";

  (sc.steps || []).forEach((st, idx) => {
    const card = document.createElement("div");
    card.className = `step-card ${idx === 0 ? "active-step" : ""}`;
    card.textContent = st.human_description || `${idx + 1}. Step`;
    stepsContainer.appendChild(card);
  });

  const codeBox = document.getElementById("code-editor-content");
  document.getElementById("code-filename").textContent = sc.file_name || "test_spec.py";
  codeBox.textContent = sc.code || "";
}

function toggleCodeView() {
  const isChecked = document.getElementById("toggle-code-switch").checked;
  const codeContainer = document.getElementById("code-viewer-container");
  codeContainer.style.display = isChecked ? "block" : "none";
}

function toggleStepsAccordion() {
  const container = document.getElementById("steps-container");
  const chevron = document.getElementById("steps-chevron");
  if (container.style.display === "none") {
    container.style.display = "flex";
    chevron.textContent = "▲";
  } else {
    container.style.display = "none";
    chevron.textContent = "▼";
  }
}

function setEnvironment(env) {
  appState.currentEnv = env;
  document.querySelectorAll(".env-pill").forEach(p => p.classList.remove("active"));
  const btn = document.getElementById(`env-${env.toLowerCase()}`);
  if (btn) btn.classList.add("active");
  appendLog("INFO", `Switched environment context to [${env}]`);
}

function selectBrowser(browser) {
  appState.selectedBrowser = browser;
  document.querySelectorAll(".browser-icon").forEach(b => b.classList.remove("active"));
  const target = document.getElementById(`browser-${browser}`);
  if (target) target.classList.add("active");
  appendLog("INFO", `Selected target browser: [${browser === 'msedge' ? 'Microsoft Edge' : 'Google Chrome'}]`);
}

function toggleHeadless() {
  appState.headless = !appState.headless;
  const label = document.getElementById("headless-label");
  label.textContent = `Headless: ${appState.headless ? "ON" : "OFF"}`;
  appendLog("INFO", `Headless mode set to: ${appState.headless ? "ON" : "OFF"}`);
}

function toggleSelectTest(scenarioId, isChecked) {
  if (isChecked) {
    appState.selectedCheckboxIds.add(scenarioId);
  } else {
    appState.selectedCheckboxIds.delete(scenarioId);
  }
}

function toggleSelectAll() {
  const master = document.getElementById("select-all").checked;
  appState.scenarios.forEach(sc => {
    if (master) {
      appState.selectedCheckboxIds.add(sc.id);
    } else {
      appState.selectedCheckboxIds.delete(sc.id);
    }
  });
  renderTable();
}

function appendLog(level, message) {
  const feed = document.getElementById("terminal-logs-feed");
  const entry = document.createElement("div");
  let cls = "log-info";
  if (level === "ERROR") cls = "log-error";
  if (level === "SUCCESS") cls = "log-success";

  entry.className = cls;
  entry.textContent = `${level}: ${message}`;
  feed.appendChild(entry);
  feed.scrollTop = feed.scrollHeight;
}

function clearLogs() {
  document.getElementById("terminal-logs-feed").innerHTML = "";
}

window.conduit_receive_log = function(level, message) {
  appendLog(level, message);
};
window.testflow_receive_log = window.conduit_receive_log;

window.conduit_receive_progress = function(data) {
  const pbar = document.getElementById("exec-progress-bar");
  const ptext = document.getElementById("exec-status-text");
  if (pbar && data.percentage !== undefined) {
    pbar.style.width = `${data.percentage}%`;
  }
  if (ptext && data.status_text) {
    ptext.textContent = data.status_text;
  }
};
window.testflow_receive_progress = window.conduit_receive_progress;

async function runSelectedTests() {
  const selectedIds = Array.from(appState.selectedCheckboxIds);
  if (selectedIds.length === 0) {
    alert("Please select at least one test scenario to run.");
    return;
  }

  appendLog("INFO", `Triggering execution for ${selectedIds.length} scenario(s)...`);
  document.getElementById("exec-status-text").textContent = `Running ${selectedIds.length} scenarios...`;
  document.getElementById("exec-progress-bar").style.width = "10%";

  if (window.pywebview && window.pywebview.api) {
    try {
      await window.pywebview.api.run_scenarios(selectedIds, appState.selectedBrowser, appState.headless, appState.currentEnv);
    } catch (err) {
      appendLog("ERROR", `Execution launch failed: ${err}`);
    }
  } else {
    simulateExecution(selectedIds);
  }
}

async function runSingleTest(scenarioId) {
  selectScenario(scenarioId);
  appendLog("INFO", `Running single scenario [${scenarioId}]...`);
  document.getElementById("exec-status-text").textContent = `Running 1 scenario...`;
  document.getElementById("exec-progress-bar").style.width = "20%";

  if (window.pywebview && window.pywebview.api) {
    await window.pywebview.api.run_scenarios([scenarioId], appState.selectedBrowser, appState.headless, appState.currentEnv);
  } else {
    simulateExecution([scenarioId]);
  }
}

function simulateExecution(scenarioIds) {
  let progress = 10;
  const timer = setInterval(() => {
    progress += 25;
    if (progress <= 90) {
      document.getElementById("exec-progress-bar").style.width = `${progress}%`;
      appendLog("INFO", `Executing step in scenario...`);
    } else {
      clearInterval(timer);
      document.getElementById("exec-progress-bar").style.width = "100%";
      document.getElementById("exec-status-text").textContent = `Completed ${scenarioIds.length} scenario(s) — All Passed.`;
      appendLog("SUCCESS", `Flow completed in 45s with 0 errors.`);
    }
  }, 600);
}

function openRecordModal() {
  document.getElementById("record-modal").style.display = "flex";
}

function closeRecordModal() {
  document.getElementById("record-modal").style.display = "none";
}

async function launchRecording() {
  const name = document.getElementById("new-scenario-name").value.trim() || "Recorded Flow";
  const url = document.getElementById("new-scenario-url").value.trim() || "https://demo.playwright.dev/todomvc/";
  const tagsStr = document.getElementById("new-scenario-tags").value.trim();
  const tags = tagsStr.split(",").map(t => t.trim()).filter(Boolean);

  closeRecordModal();
  appendLog("INFO", `Launching browser recorder for [${name}] on ${url}...`);

  if (window.pywebview && window.pywebview.api) {
    try {
      const res = await window.pywebview.api.start_recording(name, url, tags, appState.selectedBrowser);
      appendLog("INFO", res.message || "Recorder active. Alt+Click any element in the browser to inject assertions.");
    } catch (err) {
      appendLog("ERROR", `Failed to start recorder: ${err}`);
    }
  } else {
    appendLog("INFO", "Recording simulation active. Stop recording to synthesize Page Object Model.");
  }
}

function copyGeneratedCode() {
  const code = document.getElementById("code-editor-content").textContent;
  navigator.clipboard.writeText(code);
  appendLog("INFO", "Synthesized Python POM code copied to clipboard!");
}

function closeInspector() {
  document.getElementById("inspector-panel").style.display = "none";
}
