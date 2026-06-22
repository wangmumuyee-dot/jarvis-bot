const state = {
  options: {
    currencies: ["CNY", "USD", "HKD", "JPY", "EUR"],
    categories: [],
    accounts: [],
    books: [],
    templates: [],
  },
  dashboard: null,
  entries: [],
  accountEditorMode: "closed",
  accountSaving: false,
  entrySaving: false,
  entryComposerOpen: true,
  refreshing: false,
  pendingDeleteEntryId: null,
  entryFilters: {
    range: "month",
    startDate: "",
    endDate: "",
  },
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
const viewStorageKey = "jarvisFinanceActiveView";
const viewTitles = {
  record: "记账",
  entries: "流水",
  insights: "洞察",
  budget: "预算",
  debt: "欠款",
  saving: "愿望",
  accounts: "账户",
  tools: "工具",
  command: "命令",
};
let pendingAuthResolve = null;
let pendingAuthPromise = null;

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  setToday();
  renderQuickActions();
  const hashView = window.location.hash.replace(/^#/, "");
  setActiveView(viewTitles[hashView] ? hashView : localStorage.getItem(viewStorageKey) || "record");
  refreshAll();
});

window.addEventListener("hashchange", () => {
  const hashView = window.location.hash.replace(/^#/, "");
  if (viewTitles[hashView]) {
    setActiveView(hashView);
  }
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/finance-sw.js", { scope: "/" })
      .catch((error) => console.warn("Finance PWA service worker registration failed", error));
  });
}

function bindEvents() {
  document.getElementById("menuButton").addEventListener("click", openMenu);
  document.getElementById("closeMenuButton").addEventListener("click", closeMenu);
  document.getElementById("menuBackdrop").addEventListener("click", closeMenu);
  document.getElementById("refreshButton").addEventListener("click", refreshAll);
  document.getElementById("authButton").addEventListener("click", () => showAuthOverlay());
  document.getElementById("authForm").addEventListener("submit", submitAuthToken);
  document.getElementById("clearAuthButton").addEventListener("click", clearAuthToken);

  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveView(button.dataset.viewTarget || "record");
      closeMenu();
    });
  });

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
  document.getElementById("entryComposerToggle").addEventListener("click", toggleEntryComposer);
  document.getElementById("entryCollapsedTrigger").addEventListener("click", openEntryComposer);
  document.getElementById("entryEditForm").addEventListener("submit", submitEntryEdit);
  document.getElementById("cancelEntryEditButton").addEventListener("click", closeEntryEditor);
  document.getElementById("entryEditModal").addEventListener("click", (event) => {
    if (event.target.id === "entryEditModal") {
      closeEntryEditor();
    }
  });
  document.getElementById("cancelEntryDeleteButton").addEventListener("click", closeEntryDeleteModal);
  document.getElementById("confirmEntryDeleteButton").addEventListener("click", confirmEntryDelete);
  document.getElementById("entryDeleteModal").addEventListener("click", (event) => {
    if (event.target.id === "entryDeleteModal") {
      closeEntryDeleteModal();
    }
  });
  document.querySelectorAll("#editEntryTypeGroup .segment").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("#editEntryTypeGroup .segment").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      document.getElementById("editEntryType").value = button.dataset.editType;
    });
  });
  document.getElementById("commandForm").addEventListener("submit", submitCommand);
  document.getElementById("budgetToolForm").addEventListener("submit", submitBudgetTool);
  document.getElementById("debtToolForm").addEventListener("submit", submitDebtTool);
  document.getElementById("savingToolForm").addEventListener("submit", submitSavingTool);
  document.getElementById("templateToolForm").addEventListener("submit", submitTemplateTool);
  document.getElementById("recurringToolForm").addEventListener("submit", submitRecurringTool);
  document.getElementById("importToolForm").addEventListener("submit", submitImportTool);
  document.getElementById("accountToolForm").addEventListener("submit", submitAccountTool);
  document.getElementById("newAccountButton").addEventListener("click", startNewAccount);
  document.getElementById("cancelAccountEditButton").addEventListener("click", closeAccountEditor);
  document.getElementById("deleteAccountButton").addEventListener("click", deleteSelectedAccount);
  document.getElementById("categoryToolForm").addEventListener("submit", submitCategoryTool);
  document.getElementById("cardToolForm").addEventListener("submit", submitCardTool);
  document.getElementById("periodToolForm").addEventListener("submit", submitPeriodTool);
  document.getElementById("searchToolForm").addEventListener("submit", submitSearchTool);
  document.getElementById("entryFilterForm").addEventListener("submit", applyEntryFilters);
  document.querySelectorAll("[data-entry-range]").forEach((button) => {
    button.addEventListener("click", () => setEntryFilterRange(button.dataset.entryRange || "month"));
  });
  document.getElementById("entriesBody").addEventListener("click", (event) => {
    const editButton = event.target.closest("[data-edit-entry-id]");
    if (editButton) {
      event.preventDefault();
      event.stopPropagation();
      const entry = state.entries.find((item) => String(item.id) === editButton.dataset.editEntryId);
      if (entry) {
        editEntry(entry);
      }
      return;
    }
    const deleteButton = event.target.closest("[data-delete-entry-id]");
    if (deleteButton) {
      event.preventDefault();
      event.stopPropagation();
      deleteEntryById(Number(deleteButton.dataset.deleteEntryId));
    }
  });

  document.body.addEventListener("click", (event) => {
    const target = event.target.closest("[data-command]");
    if (!target) {
      return;
    }
    if (target.dataset.exportScope) {
      downloadExport(target.dataset.exportScope, target.dataset.exportRedact === "true");
      return;
    }
    document.getElementById("commandText").value = target.dataset.command;
    executeCommand(target.dataset.command);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeEntryEditor();
      closeEntryDeleteModal();
    }
  });
}

function openMenu() {
  document.getElementById("sideMenu").classList.remove("hidden");
  document.getElementById("menuBackdrop").classList.remove("hidden");
  document.getElementById("menuButton").setAttribute("aria-expanded", "true");
}

function closeMenu() {
  document.getElementById("sideMenu").classList.add("hidden");
  document.getElementById("menuBackdrop").classList.add("hidden");
  document.getElementById("menuButton").setAttribute("aria-expanded", "false");
}

function setActiveView(view) {
  const nextView = viewTitles[view] ? view : "record";
  localStorage.setItem(viewStorageKey, nextView);
  if (window.location.hash !== `#${nextView}`) {
    history.replaceState(null, "", `#${nextView}`);
  }
  document.body.dataset.currentView = nextView;
  document.getElementById("viewTitle").textContent = viewTitles[nextView];
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.classList.toggle("active", button.dataset.viewTarget === nextView);
  });
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    const views = (panel.dataset.viewPanel || "").split(/\s+/);
    panel.classList.toggle("active-view", views.includes(nextView));
  });
  document.querySelectorAll(".primary-grid, .tools-grid, .detail-grid").forEach((container) => {
    container.classList.toggle("view-container-hidden", !container.querySelector("[data-view-panel].active-view"));
  });
  if (nextView === "record") {
    openEntryComposer();
  }
  window.scrollTo({ top: 0, behavior: "auto" });
}

function setToday() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  document.getElementById("occurredAt").value = `${yyyy}-${mm}-${dd}`;
  syncEntryFilterInputs();
}

async function refreshAll() {
  if (state.refreshing) {
    return;
  }
  state.refreshing = true;
  setRefreshState("loading");
  try {
    const [options, dashboard, entries] = await Promise.all([
      getJson("/api/finance/options"),
      getJson("/api/finance/dashboard"),
      getJson("/api/finance/entries?limit=0"),
    ]);
    state.options = options;
    state.dashboard = dashboard;
    state.entries = entries.entries || [];
    renderOptions(options);
    renderDashboard(dashboard);
    renderEntries(filteredEntries());
    setRefreshState("success");
  } catch (error) {
    showReply(`加载失败：${error.message}`);
    setRefreshState("error", error.message);
  } finally {
    state.refreshing = false;
  }
}

async function submitEntry(event) {
  event.preventDefault();
  if (state.entrySaving) {
    return;
  }
  const form = event.currentTarget;
  const payload = entryPayloadFromForm(form);

  if (!payload.amount || payload.amount <= 0) {
    toast("金额需要大于 0");
    return;
  }

  state.entrySaving = true;
  const submitButton = form.querySelector("button[type='submit']");
  const originalLabel = submitButton ? submitButton.textContent : "";
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = "保存中...";
  }
  setEntrySaveFeedback("正在保存这笔流水...", "pending");
  try {
    const result = await postJson("/api/finance/entries", payload);
    showReply(result.reply);
    toast("流水已保存");
    form.querySelector("[name='amount']").value = "";
    form.querySelector("[name='note']").value = "";
    form.querySelector("[name='tags']").value = "";
    await refreshAll();
    closeEntryComposer();
    setEntrySaveFeedback(
      `已保存：${money(payload.amount, payload.currency)} · ${payload.category} · ${payload.account}`,
      "success",
    );
  } catch (error) {
    showReply(`保存失败：${error.message}`);
    setEntrySaveFeedback(`保存失败：${error.message}`, "error");
  } finally {
    state.entrySaving = false;
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel || "保存流水";
    }
  }
}

async function submitEntryEdit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const entryId = Number(form.elements.id.value);
  if (!entryId) {
    toast("请先选择流水");
    return;
  }
  const payload = entryPayloadFromForm(form);
  if (!payload.amount || payload.amount <= 0) {
    toast("金额需要大于 0");
    return;
  }
  try {
    const result = await putJson(`/api/finance/entries/${entryId}`, payload);
    showReply(result.reply);
    closeEntryEditor();
    await refreshAll();
    setActiveView("entries");
  } catch (error) {
    showReply(`修改失败：${error.message}`);
  }
}

async function deleteEntryById(entryId) {
  if (!entryId) {
    toast("请先选择要删除的流水");
    return;
  }
  state.pendingDeleteEntryId = entryId;
  const message = document.getElementById("entryDeleteMessage");
  message.textContent = `确定删除流水 #${entryId}？删除后不能恢复。`;
  document.getElementById("entryDeleteModal").classList.remove("hidden");
}

async function confirmEntryDelete() {
  const entryId = Number(state.pendingDeleteEntryId);
  if (!entryId) {
    closeEntryDeleteModal();
    return;
  }
  try {
    const result = await deleteJson(`/api/finance/entries/${entryId}`);
    showReply(result.reply);
    toast("流水已删除");
    const form = document.getElementById("entryEditForm");
    if (Number(form.elements.id.value) === entryId) {
      closeEntryEditor();
    }
    closeEntryDeleteModal();
    await refreshAll();
    setActiveView("entries");
  } catch (error) {
    showReply(`删除失败：${error.message}`);
  }
}

function closeEntryDeleteModal() {
  state.pendingDeleteEntryId = null;
  document.getElementById("entryDeleteModal").classList.add("hidden");
}

function entryPayloadFromForm(form) {
  const data = new FormData(form);
  return {
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
  if (state.accountSaving) {
    return;
  }
  const form = event.currentTarget;
  const data = new FormData(event.currentTarget);
  const payload = {
    id: Number(data.get("id")) || null,
    name: String(data.get("name") || "").trim(),
    account_type: data.get("account_type") || "asset",
    currency: data.get("currency") || "CNY",
    opening_balance: Number(data.get("opening_balance") || 0),
  };
  if (!payload.name) {
    toast("请填写账户名");
    return;
  }
  if (Number.isNaN(payload.opening_balance)) {
    toast("请填写有效余额");
    return;
  }
  state.accountSaving = true;
  const submitButton = form.querySelector("button[type='submit']");
  const originalLabel = submitButton ? submitButton.textContent : "";
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = "保存中...";
  }
  try {
    const result = await postJson("/api/finance/accounts", payload);
    showReply(result.reply);
    closeAccountEditor();
    await refreshAll();
    setActiveView("accounts");
  } catch (error) {
    showReply(`账户保存失败：${error.message}`);
  } finally {
    state.accountSaving = false;
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel || "保存账户";
    }
  }
}

async function deleteSelectedAccount() {
  const form = document.getElementById("accountToolForm");
  const accountId = Number(form.elements.id.value);
  if (!accountId) {
    toast("请先选择账户");
    return;
  }
  try {
    const result = await deleteJson(`/api/finance/accounts/${accountId}`);
    showReply(result.reply);
    closeAccountEditor();
    await refreshAll();
    setActiveView("accounts");
  } catch (error) {
    showReply(`删除失败：${error.message}`);
  }
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
  fillSelect("editCurrencySelect", options.currencies || state.options.currencies, "CNY");
  document.querySelectorAll(".account-currency-select").forEach((node) => {
    fillSelectElement(node, options.currencies || state.options.currencies, "CNY");
  });
  fillDatalist(
    "categoryList",
    (options.categories || []).map((item) => item.label || item.name),
  );
  fillDatalist(
    "accountList",
    (options.accounts || []).map((item) => item.name),
  );
  fillAccountSelect("accountSelect", options.accounts || [], "默认账户", false);
  fillAccountSelect("transferAccountSelect", options.accounts || [], "", true);
  fillAccountSelect("editAccountSelect", options.accounts || [], "默认账户", false);
  fillAccountSelect("editTransferAccountSelect", options.accounts || [], "", true);
  document.querySelectorAll(".account-select").forEach((node) => {
    fillAccountSelectElement(node, options.accounts || [], node.value || "默认账户", false);
  });
  fillDatalist("bookList", options.books || []);
  renderTemplateActions(options.templates || []);
  renderAccounts(options.accounts || []);
}

function renderDashboard(data) {
  document.getElementById("periodLabel").textContent = data.period || "--";
  document.getElementById("incomeMetric").textContent = money(data.totals.income);
  document.getElementById("expenseMetric").textContent = money(data.totals.expense);
  document.getElementById("netMetric").textContent = money(data.totals.net);
  document.getElementById("reimburseMetric").textContent = money(data.totals.pending_reimbursement);
  renderAssets(data.assets || {});
  renderBudgets(data.budgets || []);
  renderCategories(data.categories || []);
  renderSavings(data.saving_goals || []);
  renderDebts(data.debts || []);
}

function renderAssets(assets) {
  const primaryCurrency = assets.primary_currency || "CNY";
  const primaryTotal = Number(assets.primary_total || 0);
  const currencyItems = assets.currencies || [];
  const accountItems = assets.accounts || [];
  const historyItems = assets.history || [];

  document.getElementById("assetMetric").textContent = money(primaryTotal, primaryCurrency);
  document.getElementById("assetHint").textContent = currencyItems.length > 1 ? `含 ${currencyItems.length} 个币种` : `按 ${primaryCurrency} 统计`;
  renderAssetHistory(historyItems, primaryCurrency);

  const currencyNode = document.getElementById("assetCurrencyList");
  if (!currencyItems.length) {
    currencyNode.innerHTML = `<div class="empty-state">暂无账户资产</div>`;
  } else {
    currencyNode.innerHTML = currencyItems
      .map((item) => `
        <div class="compact-item">
          <div class="row-between">
            <strong>${escapeHtml(item.currency)}</strong>
            <span>${escapeHtml(money(item.total, item.currency))}</span>
          </div>
        </div>
      `)
      .join("");
  }

  const accountNode = document.getElementById("accountAssetList");
  if (!accountItems.length) {
    accountNode.innerHTML = "";
    return;
  }
  accountNode.innerHTML = accountItems
    .map((item) => `
      <div class="account-item static-account-item">
        <span>
          <strong>${escapeHtml(item.name)}</strong>
          <small>${escapeHtml(accountTypeLabel(item.account_type))}</small>
        </span>
        <b>${escapeHtml(money(item.balance, item.currency))}</b>
      </div>
    `)
    .join("");
}

function renderAssetHistory(items, currency) {
  const node = document.getElementById("assetChart");
  const rangeNode = document.getElementById("assetChartRange");
  if (!items.length) {
    node.innerHTML = "暂无资产曲线";
    node.classList.add("empty-state");
    rangeNode.textContent = "--";
    return;
  }

  node.classList.remove("empty-state");
  const values = items.map((item) => Number(item.total || 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 320;
  const height = 156;
  const paddingX = 8;
  const paddingTop = 12;
  const paddingBottom = 28;
  const chartHeight = height - paddingTop - paddingBottom;
  const stepX = items.length > 1 ? (width - paddingX * 2) / (items.length - 1) : 0;
  const points = items
    .map((item, index) => {
      const x = paddingX + stepX * index;
      const y = paddingTop + (max - Number(item.total || 0)) / span * chartHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const areaPoints = `${paddingX},${height - paddingBottom} ${points} ${paddingX + stepX * (items.length - 1)},${height - paddingBottom}`;
  const startLabel = items[0].label || items[0].date;
  const endLabel = items[items.length - 1].label || items[items.length - 1].date;
  rangeNode.textContent = `${startLabel} - ${endLabel}`;

  const midValue = (min + max) / 2;
  node.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" class="asset-chart-svg" aria-label="每日总资产折线图">
      <line x1="${paddingX}" y1="${paddingTop}" x2="${paddingX}" y2="${height - paddingBottom}" class="asset-chart-grid" />
      <line x1="${paddingX}" y1="${paddingTop + chartHeight / 2}" x2="${width - paddingX}" y2="${paddingTop + chartHeight / 2}" class="asset-chart-grid" />
      <line x1="${paddingX}" y1="${height - paddingBottom}" x2="${width - paddingX}" y2="${height - paddingBottom}" class="asset-chart-grid" />
      <polygon points="${areaPoints}" class="asset-chart-area"></polygon>
      <polyline points="${points}" class="asset-chart-line"></polyline>
      <circle cx="${paddingX}" cy="${paddingTop + (max - values[0]) / span * chartHeight}" r="3.5" class="asset-chart-dot"></circle>
      <circle cx="${paddingX + stepX * (items.length - 1)}" cy="${paddingTop + (max - values[values.length - 1]) / span * chartHeight}" r="4" class="asset-chart-dot current"></circle>
      <text x="${paddingX}" y="10" class="asset-chart-label">${escapeHtml(money(max, currency))}</text>
      <text x="${paddingX}" y="${paddingTop + chartHeight / 2 - 4}" class="asset-chart-label">${escapeHtml(money(midValue, currency))}</text>
      <text x="${paddingX}" y="${height - 8}" class="asset-chart-label">${escapeHtml(startLabel)}</text>
      <text x="${width - paddingX}" y="${height - 8}" text-anchor="end" class="asset-chart-label">${escapeHtml(endLabel)}</text>
    </svg>
  `;
}

function renderEntries(entries) {
  document.getElementById("entryCountLabel").textContent = `${entries.length} 条`;
  renderEntryFilterSummary(entries.length);
  const body = document.getElementById("entriesBody");
  body.innerHTML = "";
  if (!entries.length) {
    body.innerHTML = `<div class="empty-state">暂无流水</div>`;
    return;
  }
  for (const entry of entries) {
    const card = document.createElement("article");
    card.className = "entry-card";
    card.innerHTML = `
      <div class="entry-card-top">
        <div class="entry-card-main">
          <div class="entry-card-title">
            <strong>${escapeHtml(entry.category)}</strong>
            <span class="badge ${badgeClass(entry.entry_type)}">${escapeHtml(entry.entry_type_label)}</span>
          </div>
          <div class="entry-card-meta">
            <span>${escapeHtml(datePart(entry.occurred_at))}</span>
            <span>${escapeHtml(entry.account || "默认账户")}</span>
          </div>
        </div>
        <b class="entry-card-amount">${escapeHtml(money(entry.amount, entry.currency))}</b>
      </div>
      <div class="entry-card-bottom">
        <div class="entry-card-note">${escapeHtml(entry.note || "无备注")}${tagsHtml(entry.tags)}</div>
        <div class="table-actions">
          <button class="text-button table-action" type="button" data-edit-entry-id="${escapeAttr(entry.id)}">修改</button>
          <button class="text-button table-action danger-text" type="button" data-delete-entry-id="${escapeAttr(entry.id)}">删除</button>
        </div>
      </div>
    `;
    body.appendChild(card);
  }
}

function applyEntryFilters(event) {
  event.preventDefault();
  const form = event.currentTarget;
  state.entryFilters.range = "custom";
  state.entryFilters.startDate = String(form.elements.start_date.value || "");
  state.entryFilters.endDate = String(form.elements.end_date.value || "");
  renderEntryFilterUi();
  renderEntries(filteredEntries());
  toast("已应用自定义筛选");
}

function filteredEntries() {
  const { startDate, endDate } = resolvedEntryDateRange();
  return state.entries.filter((entry) => {
    const day = datePart(entry.occurred_at);
    if (startDate && day < startDate) {
      return false;
    }
    if (endDate && day > endDate) {
      return false;
    }
    return true;
  });
}

function setEntryFilterRange(range) {
  const nextRange = ["today", "week", "month", "custom"].includes(range) ? range : "month";
  state.entryFilters.range = nextRange;
  if (nextRange !== "custom") {
    const { startDate, endDate } = quickEntryRange(nextRange);
    state.entryFilters.startDate = startDate;
    state.entryFilters.endDate = endDate;
  }
  renderEntryFilterUi();
  syncEntryFilterInputs();
  renderEntries(filteredEntries());
  toast(`已切换到${entryRangeLabel(nextRange)}`);
}

function renderEntryFilterUi() {
  document.querySelectorAll("[data-entry-range]").forEach((button) => {
    const isActive = button.dataset.entryRange === state.entryFilters.range;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
  document.getElementById("entryFilterCustom").classList.toggle("hidden", state.entryFilters.range !== "custom");
}

function syncEntryFilterInputs() {
  document.getElementById("entryFilterStart").value = state.entryFilters.startDate || "";
  document.getElementById("entryFilterEnd").value = state.entryFilters.endDate || "";
}

function resolvedEntryDateRange() {
  if (state.entryFilters.range === "custom") {
    return {
      startDate: state.entryFilters.startDate,
      endDate: state.entryFilters.endDate,
    };
  }
  return quickEntryRange(state.entryFilters.range);
}

function renderEntryFilterSummary(count) {
  const node = document.getElementById("entryFilterSummary");
  if (!node) {
    return;
  }
  if (state.entryFilters.range === "custom") {
    const start = state.entryFilters.startDate || "不限";
    const end = state.entryFilters.endDate || "不限";
    node.textContent = `自定义 ${start} - ${end} · ${count} 条`;
    return;
  }
  node.textContent = `${entryRangeLabel(state.entryFilters.range)} · ${count} 条`;
}

function quickEntryRange(range) {
  const today = new Date();
  const todayText = formatDateInput(today);
  if (range === "today") {
    return { startDate: todayText, endDate: todayText };
  }
  if (range === "week") {
    const start = new Date(today);
    const day = start.getDay();
    const diff = day === 0 ? 6 : day - 1;
    start.setDate(start.getDate() - diff);
    return { startDate: formatDateInput(start), endDate: todayText };
  }
  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  return { startDate: formatDateInput(start), endDate: todayText };
}

function entryRangeLabel(range) {
  if (range === "today") return "今天";
  if (range === "week") return "本周";
  if (range === "custom") return "自定义";
  return "本月";
}

function editEntry(entry) {
  const form = document.getElementById("entryEditForm");
  form.elements.id.value = entry.id;
  setEditEntryType(entry.entry_type || "expense");
  form.elements.amount.value = entry.amount;
  form.elements.currency.value = entry.currency || "CNY";
  form.elements.category.value = entry.category || "其他";
  form.elements.occurred_at.value = datePart(entry.occurred_at);
  form.elements.account.value = entry.account || "默认账户";
  form.elements.book.value = entry.book || "日常账本";
  form.elements.transfer_to_account.value = entry.transfer_to_account || "";
  form.elements.note.value = entry.note || "";
  form.elements.tags.value = (entry.tags || []).join(", ");
  form.elements.reimbursable.checked = Boolean(entry.reimbursable);
  document.getElementById("entryEditorTitle").textContent = `修改流水 #${entry.id}`;
  document.getElementById("entryEditModal").classList.remove("hidden");
  setActiveView("entries");
  form.elements.amount.focus();
}

function setEditEntryType(type) {
  document.getElementById("editEntryType").value = type;
  document.querySelectorAll("#editEntryTypeGroup .segment").forEach((button) => {
    button.classList.toggle("active", button.dataset.editType === type);
  });
}

function closeEntryEditor() {
  const form = document.getElementById("entryEditForm");
  const modal = document.getElementById("entryEditModal");
  if (modal.classList.contains("hidden")) {
    return;
  }
  form.reset();
  form.elements.id.value = "";
  setEditEntryType("expense");
  modal.classList.add("hidden");
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

function setEntrySaveFeedback(text, stateName) {
  const node = document.getElementById("entrySaveFeedback");
  if (!node) {
    return;
  }
  node.textContent = text || "";
  node.classList.remove("hidden", "pending", "success", "error");
  if (!text) {
    node.classList.add("hidden");
    return;
  }
  node.classList.add(stateName || "success");
}

function setRefreshState(stateName, detail = "") {
  const button = document.getElementById("refreshButton");
  const icon = document.getElementById("refreshIcon");
  const status = document.getElementById("refreshStatus");
  if (!button || !icon || !status) {
    return;
  }
  button.disabled = stateName === "loading";
  icon.classList.toggle("spinning", stateName === "loading");
  if (stateName === "loading") {
    status.textContent = "刷新中...";
    return;
  }
  if (stateName === "error") {
    status.textContent = `刷新失败${detail ? `：${detail}` : ""}`;
    toast("刷新失败");
    return;
  }
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  status.textContent = `已刷新 ${hh}:${mm}:${ss}`;
  toast("数据已刷新");
}

function openEntryComposer() {
  state.entryComposerOpen = true;
  const panel = document.getElementById("entryPanel");
  const body = document.getElementById("entryComposerBody");
  const toggle = document.getElementById("entryComposerToggle");
  const trigger = document.getElementById("entryCollapsedTrigger");
  panel.classList.remove("collapsed");
  body.classList.remove("hidden");
  trigger.classList.add("hidden");
  toggle.textContent = "收起";
}

function closeEntryComposer() {
  state.entryComposerOpen = false;
  const panel = document.getElementById("entryPanel");
  const body = document.getElementById("entryComposerBody");
  const toggle = document.getElementById("entryComposerToggle");
  const trigger = document.getElementById("entryCollapsedTrigger");
  panel.classList.add("collapsed");
  body.classList.add("hidden");
  trigger.classList.remove("hidden");
  toggle.textContent = "记一笔";
}

function toggleEntryComposer() {
  if (state.entryComposerOpen) {
    closeEntryComposer();
    return;
  }
  openEntryComposer();
}

function renderAccounts(items) {
  const node = document.getElementById("accountManageList");
  if (!node) {
    return;
  }
  if (!items.length) {
    node.innerHTML = `<div class="empty-state">暂无账户</div>`;
    return;
  }
  node.innerHTML = items
    .map((item) => `
      <button class="account-item" type="button" data-account-id="${escapeAttr(item.id)}">
        <span>
          <strong>${escapeHtml(item.name)}</strong>
          <small>${escapeHtml(accountTypeLabel(item.account_type))} · 初始 ${escapeHtml(money(item.opening_balance, item.currency))}</small>
        </span>
        <b>${escapeHtml(money(item.balance, item.currency))}</b>
      </button>
    `)
    .join("");

  node.querySelectorAll("[data-account-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const account = items.find((item) => String(item.id) === button.dataset.accountId);
      if (!account) {
        return;
      }
      editAccount(account);
    });
  });
}

function startNewAccount() {
  const form = document.getElementById("accountToolForm");
  state.accountEditorMode = "new";
  form.reset();
  form.elements.id.value = "";
  form.elements.account_type.value = "asset";
  form.elements.currency.value = "CNY";
  form.elements.opening_balance.value = "";
  document.getElementById("accountEditorTitle").textContent = "新增账户";
  document.getElementById("deleteAccountButton").classList.add("hidden");
  form.classList.remove("hidden");
  form.elements.name.focus();
}

function editAccount(account) {
  const form = document.getElementById("accountToolForm");
  state.accountEditorMode = "edit";
  form.elements.id.value = account.id;
  form.elements.name.value = account.name;
  form.elements.account_type.value = account.account_type;
  form.elements.currency.value = account.currency;
  form.elements.opening_balance.value = account.opening_balance;
  document.getElementById("accountEditorTitle").textContent = `编辑账户：${account.name}`;
  document.getElementById("deleteAccountButton").classList.remove("hidden");
  form.classList.remove("hidden");
  form.elements.name.focus();
}

function closeAccountEditor() {
  const form = document.getElementById("accountToolForm");
  state.accountEditorMode = "closed";
  form.reset();
  form.elements.id.value = "";
  form.classList.add("hidden");
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

async function putJson(url, payload) {
  return requestJson("PUT", url, payload);
}

async function deleteJson(url) {
  return requestJson("DELETE", url);
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
  fillSelectElement(node, values, selected);
}

function fillSelectElement(node, values, selected) {
  node.innerHTML = values
    .map((value) => `<option value="${escapeAttr(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(value)}</option>`)
    .join("");
}

function fillAccountSelect(id, accounts, selected, includeEmpty) {
  fillAccountSelectElement(document.getElementById(id), accounts, selected, includeEmpty);
}

function fillAccountSelectElement(node, accounts, selected, includeEmpty) {
  const current = selected || node.value || "";
  const options = accounts.map((account) => account.name);
  if (current && !options.includes(current)) {
    options.unshift(current);
  }
  const emptyOption = includeEmpty ? `<option value="">不选择</option>` : "";
  node.innerHTML =
    emptyOption +
    options
      .map((name) => `<option value="${escapeAttr(name)}" ${name === current ? "selected" : ""}>${escapeHtml(name)}</option>`)
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

function formatDateInput(date) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
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

function accountTypeLabel(value) {
  const labels = {
    asset: "资产账户",
    cash: "现金",
    debit_card: "储蓄卡",
    credit_card: "信用卡",
    wallet: "钱包",
    liability: "负债",
    other: "其他",
  };
  return labels[value] || value || "账户";
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
