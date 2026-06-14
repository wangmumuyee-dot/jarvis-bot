const state = {
  options: {
    currencies: ["CNY", "USD", "HKD", "JPY", "EUR"],
    categories: [],
    accounts: [],
    books: [],
    templates: [],
  },
  dashboard: null,
};

const quickCommands = [
  "这个月餐饮还剩多少预算？",
  "本月分类统计",
  "本月账单日历",
  "有哪些欠款",
  "生成本月周期账单",
  "查看愿望清单",
  "分析本月消费",
  "导出本月账单",
  "导出脱敏账单",
  "同步状态",
];

const typeDefaults = {
  expense: { category: "餐饮", note: "" },
  income: { category: "收入", note: "工资到账" },
  refund: { category: "退款", note: "退款" },
  transfer: { category: "转账", note: "转账" },
  reimbursement: { category: "报销", note: "报销到账" },
};

const authStorageKey = "jarvisFinanceWebToken";
let pendingAuthResolve = null;
let pendingAuthPromise = null;

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  setToday();
  renderQuickActions();
  refreshAll();
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/finance-sw.js", { scope: "/" })
      .catch((error) => console.warn("Finance PWA service worker registration failed", error));
  });
}

function bindEvents() {
  document.getElementById("refreshButton").addEventListener("click", refreshAll);
  document.getElementById("authButton").addEventListener("click", () => showAuthOverlay());
  document.getElementById("authForm").addEventListener("submit", submitAuthToken);
  document.getElementById("clearAuthButton").addEventListener("click", clearAuthToken);

  document.querySelectorAll("#entryTypeGroup .segment").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("#entryTypeGroup .segment").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      const type = button.dataset.type;
      document.getElementById("entryType").value = type;
      const defaults = typeDefaults[type] || typeDefaults.expense;
      document.getElementById("categoryInput").value = defaults.category;
      const note = document.querySelector("[name='note']");
      if (!note.value) {
        note.value = defaults.note;
      }
    });
  });

  document.getElementById("entryForm").addEventListener("submit", submitEntry);
  document.getElementById("commandForm").addEventListener("submit", submitCommand);
  document.getElementById("budgetToolForm").addEventListener("submit", submitBudgetTool);
  document.getElementById("debtToolForm").addEventListener("submit", submitDebtTool);
  document.getElementById("savingToolForm").addEventListener("submit", submitSavingTool);
  document.getElementById("templateToolForm").addEventListener("submit", submitTemplateTool);
  document.getElementById("recurringToolForm").addEventListener("submit", submitRecurringTool);
  document.getElementById("importToolForm").addEventListener("submit", submitImportTool);
  document.getElementById("accountToolForm").addEventListener("submit", submitAccountTool);
  document.getElementById("categoryToolForm").addEventListener("submit", submitCategoryTool);
  document.getElementById("cardToolForm").addEventListener("submit", submitCardTool);
  document.getElementById("periodToolForm").addEventListener("submit", submitPeriodTool);
  document.getElementById("searchToolForm").addEventListener("submit", submitSearchTool);

  document.body.addEventListener("click", (event) => {
    const target = event.target.closest("[data-command]");
    if (!target) {
      return;
    }
    if (target.dataset.exportScope) {
      downloadExport(target.dataset.exportScope, target.dataset.exportRedact === "true");
      return;
    }
    if (target.closest(".button-grid")) {
      executeCommand(target.dataset.command);
      return;
    }
    document.getElementById("commandText").value = target.dataset.command;
    document.getElementById("commandText").focus();
  });
}

function setToday() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  document.getElementById("occurredAt").value = `${yyyy}-${mm}-${dd}`;
}

async function refreshAll() {
  try {
    const [options, dashboard, entries] = await Promise.all([
      getJson("/api/finance/options"),
      getJson("/api/finance/dashboard"),
      getJson("/api/finance/entries?limit=30"),
    ]);
    state.options = options;
    state.dashboard = dashboard;
    renderOptions(options);
    renderDashboard(dashboard);
    renderEntries(entries.entries || []);
  } catch (error) {
    showReply(`加载失败：${error.message}`);
  }
}

async function submitEntry(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const payload = {
    entry_type: data.get("entry_type"),
    amount: Number(data.get("amount")),
    currency: data.get("currency") || "CNY",
    category: String(data.get("category") || "其他").trim(),
    note: String(data.get("note") || "").trim(),
    occurred_at: data.get("occurred_at") || null,
    account: String(data.get("account") || "默认账户").trim(),
    book: String(data.get("book") || "日常账本").trim(),
    transfer_to_account: String(data.get("transfer_to_account") || "").trim() || null,
    reimbursable: Boolean(data.get("reimbursable")),
    tags: splitTags(String(data.get("tags") || "")),
  };

  if (!payload.amount || payload.amount <= 0) {
    toast("金额需要大于 0");
    return;
  }

  try {
    const result = await postJson("/api/finance/entries", payload);
    showReply(result.reply);
    form.querySelector("[name='amount']").value = "";
    form.querySelector("[name='note']").value = "";
    form.querySelector("[name='tags']").value = "";
    await refreshAll();
  } catch (error) {
    showReply(`保存失败：${error.message}`);
  }
}

async function submitCommand(event) {
  event.preventDefault();
  const textarea = document.getElementById("commandText");
  const text = textarea.value.trim();
  if (!text) {
    toast("请输入命令");
    return;
  }
  try {
    const result = await postJson("/api/finance/command", { text });
    showReply(result.reply);
    await refreshAll();
  } catch (error) {
    showReply(`执行失败：${error.message}`);
  }
}

async function submitBudgetTool(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const category = String(data.get("category") || "").trim();
  const amount = Number(data.get("amount"));
  if (!category || !amount) {
    toast("请填写分类和金额");
    return;
  }
  await executeCommand(`设置本月${category}预算 ${amount}`);
  event.currentTarget.querySelector("[name='amount']").value = "";
}

async function submitDebtTool(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const action = data.get("action");
  const person = String(data.get("person") || "").trim();
  const amount = Number(data.get("amount"));
  if (!person || !amount) {
    toast("请填写对象和金额");
    return;
  }

  const commands = {
    lend: `借给${person} ${amount}`,
    borrow: `我向${person}借了 ${amount}`,
    lend_repay: `${person}还我 ${amount}`,
    borrow_repay: `我还${person} ${amount}`,
  };
  await executeCommand(commands[action] || commands.lend);
  event.currentTarget.querySelector("[name='amount']").value = "";
}

async function submitSavingTool(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const action = data.get("action");
  const name = String(data.get("name") || "").trim();
  const amount = Number(data.get("amount"));
  if (!name) {
    toast("请填写名称");
    return;
  }
  if (action !== "progress" && !amount) {
    toast("请填写金额");
    return;
  }

  const commands = {
    create: `创建愿望目标 ${name} ${amount}`,
    add: `为${name}存钱 ${amount}`,
    progress: `${name}储蓄进度`,
  };
  await executeCommand(commands[action] || commands.progress);
  if (action !== "progress") {
    event.currentTarget.querySelector("[name='amount']").value = "";
  }
}

async function submitTemplateTool(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const name = String(data.get("name") || "").trim();
  const command = String(data.get("command") || "").trim();
  if (!name || !command) {
    toast("请填写模板名称和命令");
    return;
  }
  await executeCommand(`新增模板 ${name} = ${command}`);
}

async function submitRecurringTool(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const day = Number(data.get("day"));
  const note = String(data.get("note") || "").trim();
  const amount = Number(data.get("amount"));
  if (!day || day < 1 || day > 31 || !note || !amount) {
    toast("请填写日期、备注和金额");
    return;
  }
  await executeCommand(`每月${day}号自动记账${note} ${amount}`);
}

async function submitImportTool(event) {
  event.preventDefault();
  const fileInput = event.currentTarget.querySelector("input[type='file']");
  const file = fileInput.files && fileInput.files[0];
  if (!file) {
    toast("请选择 .xlsx 文件");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    toast("只支持 .xlsx 文件");
    return;
  }
  try {
    const contentBase64 = await fileToBase64(file);
    const result = await postJson("/api/finance/import", {
      filename: file.name,
      content_base64: contentBase64,
    });
    showReply(result.reply);
    fileInput.value = "";
    await refreshAll();
  } catch (error) {
    showReply(`导入失败：${error.message}`);
  }
}

async function submitAccountTool(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const action = data.get("action");
  const account = String(data.get("account") || "").trim();
  const amount = Number(data.get("amount"));
  if (!account) {
    toast("请填写账户");
    return;
  }
  if (action === "opening") {
    if (Number.isNaN(amount)) {
      toast("请填写初始余额");
      return;
    }
    await executeCommand(`设置${account}初始余额 ${amount}`);
    return;
  }
  await executeCommand(`${account}余额多少`);
}

async function submitCategoryTool(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const action = data.get("action");
  const category = String(data.get("category") || "").trim();
  const parent = String(data.get("parent") || "").trim();
  if (!category) {
    toast("请填写分类");
    return;
  }
  if (action === "hide") {
    await executeCommand(`隐藏分类 ${category}`);
    return;
  }
  await executeCommand(parent ? `新增分类 ${category} 属于${parent}` : `新增分类 ${category}`);
}

async function submitCardTool(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const account = String(data.get("account") || "").trim();
  const statementDay = Number(data.get("statement_day"));
  const repaymentDay = Number(data.get("repayment_day"));
  if (!account || !validMonthDay(statementDay) || !validMonthDay(repaymentDay)) {
    toast("请填写信用卡、账单日和还款日");
    return;
  }
  await executeCommand(`设置${account}账单日${statementDay}号还款日${repaymentDay}号`);
}

async function submitPeriodTool(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const monthStart = Number(data.get("month_start"));
  const weekStart = String(data.get("week_start") || "").trim();
  if (validMonthDay(monthStart)) {
    await executeCommand(`设置每月从${monthStart}号开始`);
  }
  if (weekStart) {
    await executeCommand(`设置每周从${weekStart}开始`);
  }
  if (!validMonthDay(monthStart) && !weekStart) {
    await executeCommand("财务周期设置");
  }
}

async function submitSearchTool(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const keyword = String(data.get("keyword") || "").trim();
  if (!keyword) {
    toast("请填写关键词");
    return;
  }
  await executeCommand(`搜索${keyword}`);
}

async function executeCommand(text) {
  try {
    document.getElementById("commandText").value = text;
    const result = await postJson("/api/finance/command", { text });
    showReply(result.reply);
    await refreshAll();
  } catch (error) {
    showReply(`执行失败：${error.message}`);
  }
}

function renderOptions(options) {
  fillSelect("currencySelect", options.currencies || state.options.currencies, "CNY");
  fillDatalist(
    "categoryList",
    (options.categories || []).map((item) => item.label || item.name),
  );
  fillDatalist(
    "accountList",
    (options.accounts || []).map((item) => item.name),
  );
  fillDatalist("bookList", options.books || []);
  renderTemplateActions(options.templates || []);
}

function renderDashboard(data) {
  document.getElementById("periodLabel").textContent = data.period || "--";
  document.getElementById("incomeMetric").textContent = money(data.totals.income);
  document.getElementById("expenseMetric").textContent = money(data.totals.expense);
  document.getElementById("netMetric").textContent = money(data.totals.net);
  document.getElementById("reimburseMetric").textContent = money(data.totals.pending_reimbursement);
  renderBudgets(data.budgets || []);
  renderCategories(data.categories || []);
  renderSavings(data.saving_goals || []);
  renderDebts(data.debts || []);
}

function renderEntries(entries) {
  document.getElementById("entryCountLabel").textContent = `${entries.length} 条`;
  const body = document.getElementById("entriesBody");
  body.innerHTML = "";
  if (!entries.length) {
    body.innerHTML = `<tr><td colspan="6" class="empty-state">暂无流水</td></tr>`;
    return;
  }
  for (const entry of entries) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(datePart(entry.occurred_at))}</td>
      <td><span class="badge ${badgeClass(entry.entry_type)}">${escapeHtml(entry.entry_type_label)}</span></td>
      <td>${escapeHtml(entry.category)}</td>
      <td>${escapeHtml(entry.note)}${tagsHtml(entry.tags)}</td>
      <td>${escapeHtml(entry.account || "")}</td>
      <td class="number-cell">${escapeHtml(money(entry.amount, entry.currency))}</td>
    `;
    body.appendChild(row);
  }
}

function renderBudgets(items) {
  const node = document.getElementById("budgetList");
  if (!items.length) {
    node.innerHTML = `<div class="empty-state">暂无预算</div>`;
    return;
  }
  node.innerHTML = items
    .map((item) => {
      const progress = Math.min(item.progress, 140);
      return `
        <div class="progress-item">
          <div class="row-between">
            <strong>${escapeHtml(item.category)}</strong>
            <span>${escapeHtml(money(item.spent, item.currency))} / ${escapeHtml(money(item.amount, item.currency))}</span>
          </div>
          <div class="bar-track"><div class="bar-fill ${levelClass(item.progress)}" style="width:${progress}%"></div></div>
          <span class="soft-label">剩余 ${escapeHtml(money(item.remaining, item.currency))}</span>
        </div>
      `;
    })
    .join("");
}

function renderCategories(items) {
  const node = document.getElementById("categoryListPanel");
  if (!items.length) {
    node.innerHTML = `<div class="empty-state">本月暂无支出</div>`;
    return;
  }
  const max = Math.max(...items.map((item) => item.total), 1);
  node.innerHTML = items
    .map((item) => `
      <div class="category-item">
        <div class="row-between">
          <strong>${escapeHtml(item.category)}</strong>
          <span>${escapeHtml(money(item.total))}</span>
        </div>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.max(4, item.total / max * 100)}%"></div></div>
        <span class="soft-label">${item.count} 笔，占 ${item.share}%</span>
      </div>
    `)
    .join("");
}

function renderSavings(items) {
  const node = document.getElementById("savingList");
  if (!items.length) {
    node.innerHTML = `<div class="empty-state">暂无愿望目标</div>`;
    return;
  }
  node.innerHTML = items
    .map((item) => `
      <div class="progress-item">
        <div class="row-between">
          <strong>${escapeHtml(item.name)}</strong>
          <span>${escapeHtml(money(item.current_amount, item.currency))} / ${escapeHtml(money(item.target_amount, item.currency))}</span>
        </div>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.min(item.progress, 100)}%"></div></div>
        <span class="soft-label">${escapeHtml(item.status)}，${item.progress}%</span>
      </div>
    `)
    .join("");
}

function renderDebts(items) {
  const node = document.getElementById("debtList");
  if (!items.length) {
    node.innerHTML = `<div class="empty-state">暂无未结清欠款</div>`;
    return;
  }
  node.innerHTML = items
    .map((item) => {
      const label = item.debt_type === "lend" ? `${item.person}欠我` : `我欠${item.person}`;
      return `
        <div class="compact-item">
          <div class="row-between">
            <strong>${escapeHtml(label)}</strong>
            <span>${escapeHtml(money(item.remaining, item.currency))}</span>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderQuickActions() {
  const node = document.getElementById("quickActions");
  node.innerHTML = quickCommands
    .map((command) => `<button type="button" class="quick-action" data-command="${escapeAttr(command)}">${escapeHtml(command)}</button>`)
    .join("");
}

function renderTemplateActions(templates) {
  const node = document.getElementById("quickActions");
  const existing = quickCommands
    .map((command) => `<button type="button" class="quick-action" data-command="${escapeAttr(command)}">${escapeHtml(command)}</button>`)
    .join("");
  const templateButtons = templates
    .map((template) => {
      const command = `使用模板 ${template.name}`;
      return `<button type="button" class="quick-action" data-command="${escapeAttr(command)}">模板：${escapeHtml(template.name)}</button>`;
    })
    .join("");
  node.innerHTML = existing + templateButtons;
}

async function getJson(url) {
  return requestJson("GET", url);
}

async function postJson(url, payload) {
  return requestJson("POST", url, payload);
}

async function requestJson(method, url, payload, allowAuthRetry = true) {
  const headers = authHeaders({ "Content-Type": "application/json" });
  const response = await fetch(url, {
    method,
    headers,
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (response.status === 401 && allowAuthRetry) {
    const nextToken = await requestAuthToken();
    if (nextToken) {
      return requestJson(method, url, payload, false);
    }
  }
  return readJsonResponse(response);
}

async function downloadExport(scope, redact = false, allowAuthRetry = true) {
  try {
    const params = new URLSearchParams({ scope, redact: redact ? "true" : "false" });
    const response = await fetch(`/api/finance/export?${params.toString()}`, {
      headers: authHeaders(),
    });
    if (response.status === 401 && allowAuthRetry) {
      const nextToken = await requestAuthToken();
      if (nextToken) {
        return downloadExport(scope, redact, false);
      }
    }
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const filename = filenameFromDisposition(disposition) || `ledger-${scope}.xlsx`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showReply(`已下载账本 Excel：${filename}`);
  } catch (error) {
    showReply(`下载失败：${error.message}`);
  }
}

function authHeaders(base = {}) {
  const token = localStorage.getItem(authStorageKey);
  const headers = { ...base };
  if (token) {
    headers["X-Jarvis-Web-Token"] = token;
  }
  return headers;
}

function showAuthOverlay() {
  const overlay = document.getElementById("authOverlay");
  const input = document.getElementById("authTokenInput");
  overlay.classList.remove("hidden");
  input.value = localStorage.getItem(authStorageKey) || "";
  input.focus();
}

function hideAuthOverlay() {
  document.getElementById("authOverlay").classList.add("hidden");
}

function requestAuthToken() {
  if (pendingAuthPromise) {
    return pendingAuthPromise;
  }
  showAuthOverlay();
  pendingAuthPromise = new Promise((resolve) => {
    pendingAuthResolve = resolve;
  });
  return pendingAuthPromise;
}

function submitAuthToken(event) {
  event.preventDefault();
  const token = document.getElementById("authTokenInput").value.trim();
  if (!token) {
    toast("请输入访问口令");
    return;
  }
  localStorage.setItem(authStorageKey, token);
  hideAuthOverlay();
  toast("访问口令已保存");
  if (pendingAuthResolve) {
    const resolve = pendingAuthResolve;
    pendingAuthResolve = null;
    pendingAuthPromise = null;
    resolve(token);
  } else {
    refreshAll();
  }
}

function clearAuthToken() {
  localStorage.removeItem(authStorageKey);
  document.getElementById("authTokenInput").value = "";
  hideAuthOverlay();
  toast("访问口令已清除");
  if (pendingAuthResolve) {
    const resolve = pendingAuthResolve;
    pendingAuthResolve = null;
    pendingAuthPromise = null;
    resolve("");
  }
}

async function readJsonResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((item) => item.msg).join("；") : data.detail;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return data;
}

function fillSelect(id, values, selected) {
  const node = document.getElementById(id);
  node.innerHTML = values
    .map((value) => `<option value="${escapeAttr(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(value)}</option>`)
    .join("");
}

function fillDatalist(id, values) {
  const node = document.getElementById(id);
  const unique = Array.from(new Set(values.filter(Boolean)));
  node.innerHTML = unique.map((value) => `<option value="${escapeAttr(value)}"></option>`).join("");
}

function splitTags(value) {
  return value
    .split(/[,，\s]+/)
    .map((item) => item.replace(/^#/, "").trim())
    .filter(Boolean);
}

function validMonthDay(value) {
  return Number.isInteger(value) && value >= 1 && value <= 31;
}

async function fileToBase64(file) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 8192;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

function filenameFromDisposition(disposition) {
  const utf8Match = disposition.match(/filename\\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    return decodeURIComponent(utf8Match[1]);
  }
  const asciiMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
  return asciiMatch ? asciiMatch[1] : "";
}

function money(value, currency = "CNY") {
  const amount = Number(value || 0);
  if (currency === "CNY") {
    return `¥${amount.toFixed(2)}`;
  }
  return `${amount.toFixed(2)} ${currency}`;
}

function datePart(value) {
  return String(value || "").slice(0, 10);
}

function badgeClass(type) {
  if (type === "expense") return "expense";
  if (type === "income" || type === "refund" || type === "reimbursement") return "income";
  return "transfer";
}

function levelClass(progress) {
  if (progress >= 100) return "danger";
  if (progress >= 80) return "warn";
  return "";
}

function tagsHtml(tags) {
  if (!tags || !tags.length) {
    return "";
  }
  return ` <span class="soft-label">${tags.map((tag) => `#${escapeHtml(tag)}`).join(" ")}</span>`;
}

function showReply(text) {
  document.getElementById("replyBox").textContent = text || "已完成";
}

function toast(text) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = text;
  document.body.appendChild(node);
  window.setTimeout(() => node.remove(), 2400);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}
