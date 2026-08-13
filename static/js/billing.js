const billingLoading = document.getElementById("billingLoading");
const billingContent = document.getElementById("billingContent");
const billingViewStage = document.getElementById("billingViewStage");
const billingError = document.getElementById("billingError");
const billingPeriodLabel = document.getElementById("billingPeriodLabel");
const billingPlanBadge = document.getElementById("billingPlanBadge");
const billingPlanPrice = document.getElementById("billingPlanPrice");
const billingCurrentPlan = document.getElementById("billingCurrentPlan");
const billingUsageLabel = document.getElementById("billingUsageLabel");
const billingUsageBar = document.getElementById("billingUsageBar");
const billingUsagePercent = document.getElementById("billingUsagePercent");
const billingUsageResetNote = document.getElementById("billingUsageResetNote");
const billingUsageOverNote = document.getElementById("billingUsageOverNote");
const billingPresetButtons = document.querySelectorAll(".billing-preset-btn");
const billingPlansGrid = document.getElementById("billingPlansGrid");
const billingBalanceValue = document.getElementById("billingBalanceValue");
const billingPlanExpiresValue = document.getElementById("billingPlanExpiresValue");
const balanceTopupAmount = document.getElementById("balanceTopupAmount");
const balanceTopupMsg = document.getElementById("balanceTopupMsg");
const billingTopupHint = document.getElementById("billingTopupHint");
const paypalButtonContainer = document.getElementById("paypalButtonContainer");
const billingPaypalDisabled = document.getElementById("billingPaypalDisabled");
const billingPaypalConfigMsg = document.getElementById("billingPaypalConfigMsg");
const couponRedeemForm = document.getElementById("couponRedeemForm");
const couponRedeemMsg = document.getElementById("couponRedeemMsg");
const billingPlansPanel = document.getElementById("billingPlansPanel");
const billingUpgradePlanBtn = document.getElementById("billingUpgradePlanBtn");
const billingViewPlansBtn = document.getElementById("billingViewPlansBtn");
const billingChargeDesc = document.getElementById("billingChargeDesc");
const billingPlanDescription = document.getElementById("billingPlanDescription");
const billingBalanceConfirm = document.getElementById("billingBalanceConfirm");
const billingBalanceConfirmBack = document.getElementById("billingBalanceConfirmBack");
const billingBalanceConfirmCancel = document.getElementById("billingBalanceConfirmCancel");
const billingBalanceConfirmSubmit = document.getElementById("billingBalanceConfirmSubmit");
const billingBalanceConfirmPlan = document.getElementById("billingBalanceConfirmPlan");
const billingBalanceConfirmAmount = document.getElementById("billingBalanceConfirmAmount");
const billingBalanceConfirmCurrent = document.getElementById("billingBalanceConfirmCurrent");
const billingBalanceConfirmAfter = document.getElementById("billingBalanceConfirmAfter");
const billingBalanceConfirmMsg = document.getElementById("billingBalanceConfirmMsg");
const billingBalanceConfirmDiscountRow = document.getElementById("billingBalanceConfirmDiscountRow");
const billingBalanceConfirmDiscount = document.getElementById("billingBalanceConfirmDiscount");
const billingBalanceCouponSection = document.getElementById("billingBalanceCouponSection");
const billingBalanceCouponToggle = document.getElementById("billingBalanceCouponToggle");
const billingBalanceCouponPanel = document.getElementById("billingBalanceCouponPanel");
const billingBalanceCouponCode = document.getElementById("billingBalanceCouponCode");
const billingBalanceCouponApply = document.getElementById("billingBalanceCouponApply");
const billingBalanceCouponMsg = document.getElementById("billingBalanceCouponMsg");
const billingBalanceCouponApplied = document.getElementById("billingBalanceCouponApplied");

let billingState = null;
let pendingBalancePlan = null;
let pendingPurchaseCouponCode = null;
let pendingPurchaseDiscountJpy = 0;
let paypalButtonsInstance = null;
let paypalSdkLoading = null;
let upgradeSpotlightTimer = null;

function formatNumber(n) {
  return Number(n).toLocaleString("ja-JP");
}

function formatBalanceJpy(amount) {
  const value = Math.round(Number(amount) || 0);
  return `¥${value.toLocaleString("ja-JP", { maximumFractionDigits: 0, minimumFractionDigits: 0 })}`;
}

function formatPeriod(period) {
  if (!period || !period.includes("-")) return period || "—";
  const [y, m] = period.split("-");
  return `${y}年${Number(m)}月`;
}

function formatUsagePercent(percent) {
  if (percent == null || !Number.isFinite(Number(percent))) return "—";
  return `${Math.round(Number(percent))}%`;
}

function applyUsageBarState(bar, percentEl, percent, status) {
  const pct = Number(percent) || 0;
  const barWidth = Math.min(100, Math.max(0, pct));
  if (bar) {
    bar.style.width = `${barWidth}%`;
    bar.classList.remove("is-normal", "is-warning", "is-danger", "is-over-limit");
    if (status === "over" || status === "blocked" || pct >= 100) {
      bar.classList.add("is-over-limit", "is-danger");
    } else if (status === "warning" || pct >= 80) {
      bar.classList.add("is-warning");
    } else {
      bar.classList.add("is-normal");
    }
  }
  if (percentEl) {
    percentEl.textContent = formatUsagePercent(pct);
    percentEl.classList.toggle("is-warning", pct >= 80 && pct < 100);
    percentEl.classList.toggle("is-danger", pct >= 100);
  }
}

function syncPresetButtons() {
  const amount = parseInt(balanceTopupAmount?.value, 10);
  billingPresetButtons.forEach((btn) => {
    const preset = parseInt(btn.dataset.amount, 10);
    btn.classList.toggle("is-active", Number.isFinite(amount) && preset === amount);
  });
}

function showBillingMsg(el, text, isError) {
  if (!el) return;
  el.textContent = text;
  el.classList.remove("hidden", "success", "error");
  el.classList.add(isError ? "error" : "success");
}

function getTopupAmount() {
  const min = billingState?.min_topup_jpy ?? 500;
  const raw = balanceTopupAmount?.value;
  const amount = parseInt(raw, 10);
  if (!Number.isFinite(amount) || amount < min) {
    throw new Error(`${min}円以上の金額を指定してください`);
  }
  return amount;
}

function loadPaypalSdk(clientId, currency) {
  if (window.paypal) return Promise.resolve(window.paypal);
  if (paypalSdkLoading) return paypalSdkLoading;

  paypalSdkLoading = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(clientId)}&currency=${encodeURIComponent(currency)}&intent=capture&components=buttons`;
    script.async = true;
    script.onload = () => resolve(window.paypal);
    script.onerror = () => reject(new Error("PayPal SDKの読み込みに失敗しました"));
    document.head.appendChild(script);
  });
  return paypalSdkLoading;
}

function paypalButtonsStyle() {
  return {
    layout: "vertical",
    color: "gold",
    shape: "rect",
    label: "paypal",
  };
}

function refreshPaypalButtonsForTheme() {
  if (!billingState || billingState.features?.billing_disabled) return;
  if (!paypalButtonContainer || paypalButtonContainer.classList.contains("hidden")) return;
  setupPaypalButtons();
}

function initPaypalThemeObserver() {
  new MutationObserver(refreshPaypalButtonsForTheme).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (document.documentElement.getAttribute("data-theme") === "system") {
      refreshPaypalButtonsForTheme();
    }
  });
}

function destroyPaypalButtons() {
  if (paypalButtonsInstance?.close) {
    try {
      paypalButtonsInstance.close();
    } catch (e) {}
  }
  paypalButtonsInstance = null;
  if (paypalButtonContainer) paypalButtonContainer.innerHTML = "";
}

async function setupPaypalButtons() {
  destroyPaypalButtons();

  const paypalCfg = billingState?.paypal;
  if (!paypalCfg?.enabled || !paypalCfg.client_id) {
    paypalButtonContainer?.classList.add("hidden");
    billingPaypalDisabled?.classList.remove("hidden");
    return;
  }

  paypalButtonContainer?.classList.remove("hidden");
  billingPaypalDisabled?.classList.add("hidden");

  try {
    const paypal = await loadPaypalSdk(paypalCfg.client_id, paypalCfg.currency || "JPY");
    paypalButtonsInstance = paypal.Buttons({
      style: paypalButtonsStyle(),
      createOrder: async () => {
        const amount_jpy = getTopupAmount();
        const res = await fetch("/api/billing/paypal/create-order", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ amount_jpy }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "注文の作成に失敗しました");
        return data.order_id;
      },
      onApprove: async (data) => {
        if (balanceTopupMsg) balanceTopupMsg.classList.add("hidden");
        const res = await fetch("/api/billing/paypal/capture-order", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ order_id: data.orderID }),
        });
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || "決済の確定に失敗しました");

        if (payload.billing) {
          billingState = payload.billing;
          renderUsage(payload.billing);
        }
        if (payload.user) {
          window.__USER__ = payload.user;
          window.updateAccountDisplay?.(payload.user);
        }
        showBillingMsg(balanceTopupMsg, payload.message || "残高を追加しました", false);
      },
      onError: (err) => {
        showBillingMsg(
          balanceTopupMsg,
          err?.message || "PayPalでエラーが発生しました",
          true
        );
      },
      onCancel: () => {
        showBillingMsg(balanceTopupMsg, "決済がキャンセルされました", true);
      },
    });
    await paypalButtonsInstance.render(paypalButtonContainer);
  } catch (err) {
    showBillingMsg(billingPaypalConfigMsg, err.message, true);
    paypalButtonContainer?.classList.add("hidden");
    billingPaypalDisabled?.classList.remove("hidden");
  }
}

function showPlanPaypalMissingNotice(planName) {
  const label = planName ? `（${planName}）` : "";
  const text = `PayPalの申込URLが未設定です${label}。管理者に PAYPAL_PLAN_*_URL または system_config の paypal.plan_urls を設定してください。`;
  if (billingError) {
    billingError.textContent = text;
    billingError.classList.remove("hidden");
  } else {
    window.NexNotify?.showError(text);
  }
}

function planPaypalUrl(plan) {
  return String(plan?.paypal_url ?? "").trim();
}

function showPlanPaypalPopupBlockedNotice() {
  const text = "ポップアップを許可してください";
  if (billingError) {
    billingError.textContent = text;
    billingError.classList.remove("hidden");
  } else {
    window.NexNotify?.showError(text);
  }
}

async function executeBalancePlanSubscription(plan) {
  if (!plan?.id || !plan.is_clickable) return;
  if (billingBalanceConfirmMsg) billingBalanceConfirmMsg.classList.add("hidden");
  if (billingError) billingError.classList.add("hidden");

  const finalCharge = getBalanceConfirmFinalCharge(plan);
  const balance = Math.round(Number(billingState?.balance) || 0);
  if (finalCharge > balance) {
    showBillingMsg(
      billingBalanceConfirmMsg,
      window.t?.("billingBalanceInsufficient") ||
        `残高が不足しています（あと ¥${formatNumber(finalCharge - balance)} 必要です）`,
      true
    );
    return;
  }

  billingBalanceConfirmSubmit?.setAttribute("disabled", "disabled");
  billingBalanceConfirmCancel?.setAttribute("disabled", "disabled");
  billingBalanceConfirmBack?.setAttribute("disabled", "disabled");

  try {
    const payload = { plan_id: plan.id };
    if (pendingPurchaseCouponCode) {
      payload.coupon_code = pendingPurchaseCouponCode;
    }
    const res = await fetch("/api/billing/subscribe-with-balance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "申し込みに失敗しました");

    if (data.billing) renderUsage(data.billing);
    if (data.user) {
      window.__USER__ = data.user;
      window.updateAccountDisplay?.(data.user);
    }
    const successMsg = data.message || "プランを申し込みました";
    closeBalancePaymentConfirm();
    showBillingMsg(balanceTopupMsg, successMsg, false);
    window.NexCelebrate?.celebrate();
    window.NexNotify?.showSuccess(successMsg, { durationMs: 4500 });
  } catch (err) {
    showBillingMsg(billingBalanceConfirmMsg, err.message, true);
  } finally {
    billingBalanceConfirmSubmit?.removeAttribute("disabled");
    billingBalanceConfirmCancel?.removeAttribute("disabled");
    billingBalanceConfirmBack?.removeAttribute("disabled");
  }
}

const BILLING_VIEW_MAIN = "main";
const BILLING_VIEW_CONFIRM = "confirm";

function setBillingView(view) {
  const next = view === BILLING_VIEW_CONFIRM ? BILLING_VIEW_CONFIRM : BILLING_VIEW_MAIN;
  if (billingViewStage) {
    billingViewStage.dataset.billingView = next;
  }
  const isConfirm = next === BILLING_VIEW_CONFIRM;
  billingContent?.toggleAttribute("aria-hidden", isConfirm);
  billingBalanceConfirm?.toggleAttribute("aria-hidden", !isConfirm);
}

function getBalanceConfirmBaseCharge(plan) {
  return Math.round(Number(plan?.price_jpy) || 0);
}

function getBalanceConfirmFinalCharge(plan) {
  const base = getBalanceConfirmBaseCharge(plan);
  return Math.max(0, base - Math.round(Number(pendingPurchaseDiscountJpy) || 0));
}

function resetBalanceConfirmCoupon() {
  pendingPurchaseCouponCode = null;
  pendingPurchaseDiscountJpy = 0;
  if (billingBalanceCouponCode) billingBalanceCouponCode.value = "";
  if (billingBalanceCouponMsg) billingBalanceCouponMsg.classList.add("hidden");
  if (billingBalanceCouponApplied) {
    billingBalanceCouponApplied.textContent = "";
    billingBalanceCouponApplied.classList.add("hidden");
  }
  billingBalanceCouponPanel?.classList.add("hidden");
  billingBalanceConfirmDiscountRow?.classList.add("hidden");
}

function updateBalanceConfirmPricing(plan) {
  if (!plan) return;
  const base = getBalanceConfirmBaseCharge(plan);
  const finalCharge = getBalanceConfirmFinalCharge(plan);
  const balance = Math.round(Number(billingState?.balance) || 0);
  const priceLabel = plan.price_jpy_label || formatBalanceJpy(base);

  if (billingBalanceConfirmAmount) {
    billingBalanceConfirmAmount.textContent =
      pendingPurchaseDiscountJpy > 0
        ? formatBalanceJpy(finalCharge)
        : priceLabel;
  }
  if (billingBalanceConfirmCurrent) {
    billingBalanceConfirmCurrent.textContent =
      billingState?.balance_label || formatBalanceJpy(balance);
  }
  if (billingBalanceConfirmAfter) {
    billingBalanceConfirmAfter.textContent = formatBalanceJpy(balance - finalCharge);
  }
  if (billingBalanceConfirmDiscountRow && billingBalanceConfirmDiscount) {
    const showDiscount = pendingPurchaseDiscountJpy > 0;
    billingBalanceConfirmDiscountRow.classList.toggle("hidden", !showDiscount);
    if (showDiscount) {
      billingBalanceConfirmDiscount.textContent = `-${formatBalanceJpy(pendingPurchaseDiscountJpy)}`;
    }
  }
  if (billingBalanceCouponApplied) {
    if (pendingPurchaseCouponCode) {
      billingBalanceCouponApplied.textContent =
        (window.t?.("billingBalanceCouponApplied") || "適用中: {code}").replace(
          "{code}",
          pendingPurchaseCouponCode
        ) +
        (pendingPurchaseDiscountJpy > 0
          ? `（-${formatBalanceJpy(pendingPurchaseDiscountJpy)}）`
          : "");
      billingBalanceCouponApplied.classList.remove("hidden");
    } else {
      billingBalanceCouponApplied.classList.add("hidden");
    }
  }
}

function closeBalancePaymentConfirm() {
  pendingBalancePlan = null;
  resetBalanceConfirmCoupon();
  setBillingView(BILLING_VIEW_MAIN);
  if (billingBalanceConfirmMsg) billingBalanceConfirmMsg.classList.add("hidden");
  billingBalanceConfirmSubmit?.removeAttribute("disabled");
  billingBalanceConfirmCancel?.removeAttribute("disabled");
  billingBalanceConfirmBack?.removeAttribute("disabled");
}

function openBalancePaymentConfirm(plan) {
  if (!plan?.id || !plan.is_clickable) return;
  if (balanceTopupMsg) balanceTopupMsg.classList.add("hidden");
  if (billingError) billingError.classList.add("hidden");
  if (billingBalanceConfirmMsg) billingBalanceConfirmMsg.classList.add("hidden");

  const priceJpy = getBalanceConfirmBaseCharge(plan);
  if (priceJpy <= 0) return;

  pendingBalancePlan = plan;
  resetBalanceConfirmCoupon();
  if (billingBalanceConfirmPlan) billingBalanceConfirmPlan.textContent = plan.name || plan.id;
  updateBalanceConfirmPricing(plan);

  const couponDisabled = Boolean(billingState?.features?.coupon_disabled);
  billingBalanceCouponSection?.classList.toggle("hidden", couponDisabled);

  setBillingView(BILLING_VIEW_CONFIRM);
  billingBalanceConfirmSubmit?.focus({ preventScroll: true });
}

function subscribePlanWithBalance(plan) {
  openBalancePaymentConfirm(plan);
}

async function openPlanPaypalCheckout(plan) {
  if (balanceTopupMsg) balanceTopupMsg.classList.add("hidden");
  if (billingError) billingError.classList.add("hidden");

  if (billingState?.paypal?.enabled && plan?.id) {
    try {
      const res = await fetch("/api/billing/paypal/create-subscription", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_id: plan.id }),
      });
      const data = await res.json();
      if (res.ok && data.approve_url) {
        const opened = window.open(data.approve_url, "_blank");
        if (!opened) {
          showPlanPaypalPopupBlockedNotice();
          return;
        }
        opened.opener = null;
        return;
      }
      if (res.status !== 503 && res.status !== 400) {
        throw new Error(data.error || "サブスクリプションの開始に失敗しました");
      }
    } catch (err) {
      if (!planPaypalUrl(plan)) {
        if (billingError) {
          billingError.textContent = err.message;
          billingError.classList.remove("hidden");
        }
        return;
      }
    }
  }

  const url = planPaypalUrl(plan);
  if (!url) {
    showPlanPaypalMissingNotice(plan.name);
    return;
  }
  const opened = window.open(url, "_blank");
  if (!opened) {
    showPlanPaypalPopupBlockedNotice();
    return;
  }
  opened.opener = null;
}

function attachBillingPlanCardAction(card, plan) {
  if (!plan.is_clickable) return;
  card.addEventListener("click", (e) => {
    if (e.target.closest(".billing-plan-option-actions")) return;
    e.preventDefault();
    e.stopPropagation();
    openPlanPaypalCheckout(plan);
  });
}

function attachBillingPlanBalanceAction(card, plan) {
  const btn = card.querySelector(".billing-plan-balance-btn");
  if (!btn) return;
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    subscribePlanWithBalance(plan);
  });
}

function billingUserLanguage() {
  const lang = (window.__USER__?.language || "ja").trim().toLowerCase();
  return lang === "en" || lang === "ko" ? lang : "ja";
}

function planMarketingDescription(plan) {
  const lang = billingUserLanguage();
  const ja = String(plan.description_ja ?? "").trim();
  const en = String(plan.description_en ?? "").trim();
  const fallback = String(plan.description ?? "").trim();
  if (lang === "ja") return ja || en || fallback;
  return en || ja || fallback;
}

function renderPlans(plans) {
  if (!billingPlansGrid) return;
  billingPlansGrid.innerHTML = "";
  plans.forEach((plan) => {
    const card = document.createElement("article");
    const classes = ["billing-plan-option"];
    if (plan.is_current) classes.push("is-current");
    if (plan.is_clickable) classes.push("is-clickable");
    else classes.push("is-disabled");
    card.className = classes.join(" ");
    card.dataset.plan = plan.id;
    const desc = planMarketingDescription(plan);
    const descHtml = desc
      ? `<p class="billing-plan-option-desc">${escapeHtml(desc)}</p>`
      : "";
    let statusHtml = "";
    if (plan.is_enterprise) {
      statusHtml =
        '<p class="billing-plan-option-status">未設定 · お問い合わせ</p>';
    } else if (plan.is_clickable) {
      const priceJpy = plan.price_jpy_label || formatBalanceJpy(plan.price_jpy ?? 0);
      const sufficient = Boolean(plan.balance_sufficient);
      const shortfall =
        !sufficient && plan.price_jpy != null
          ? Math.max(0, Math.round(plan.price_jpy) - Math.round(billingState?.balance ?? 0))
          : 0;
      const balanceTitle = sufficient
        ? `${priceJpy} を残高から引き落とし`
        : `残高不足（クーポンで割引可能 · あと ¥${formatNumber(shortfall)} 必要）`;
      statusHtml = `
        <p class="billing-plan-option-status billing-plan-option-status--action">カードをクリック → PayPal</p>
        <div class="billing-plan-option-actions">
          <button type="button" class="billing-plan-balance-btn settings-btn settings-btn--primary" title="${escapeHtml(balanceTitle)}" aria-label="${escapeHtml(
        `残高で申し込む ${plan.name}`
      )}">
            残高で申し込む（${escapeHtml(priceJpy)}）
          </button>
          ${
            sufficient
              ? ""
              : `<p class="billing-plan-balance-hint">あと ¥${escapeHtml(formatNumber(shortfall))} 必要（購入時クーポン可）</p>`
          }
        </div>`;
    }
    const bodyInner = `
        <div class="billing-plan-option-head">
          <span class="billing-plan-option-name">${escapeHtml(plan.name)}</span>
          ${plan.is_current ? '<span class="billing-plan-current-tag">利用中</span>' : ""}
        </div>
        <p class="billing-plan-option-price">${escapeHtml(plan.price_label)}</p>
        ${descHtml}
        ${statusHtml}`;
    const accent = '<div class="billing-plan-option-accent" aria-hidden="true"></div>';
    card.innerHTML = `${accent}<div class="billing-plan-option-body">${bodyInner}</div>`;
    if (plan.is_clickable) {
      const url = planPaypalUrl(plan);
      card.dataset.paypalUrl = url;
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute(
        "aria-label",
        url ? `${plan.name} — PayPal で申し込む` : `${plan.name} — PayPal URL未設定`
      );
      attachBillingPlanCardAction(card, plan);
      attachBillingPlanBalanceAction(card, plan);
    }
    billingPlansGrid.appendChild(card);
  });
  syncBillingPlansPanelView();
}

function escapeHtml(text) {
  const el = document.createElement("span");
  el.textContent = text ?? "";
  return el.innerHTML;
}

function upgradeablePlans(plans) {
  return (plans || []).filter((p) => p.is_clickable);
}

function billingPlansPanelDescEl() {
  return billingPlansPanel?.querySelector(".billing-section-desc");
}

function applyBillingPlansPanelCopy(mode) {
  const titleEl = document.getElementById("billing-plans-heading");
  const descEl = billingPlansPanelDescEl();
  const upgradeable = upgradeablePlans(billingState?.plans);
  const isUpgrade = mode === "upgrade";
  if (titleEl) {
    titleEl.textContent = window.t(
      isUpgrade && upgradeable.length > 0
        ? "billingPlansTitleUpgrade"
        : "billingPlansTitle"
    );
  }
  if (descEl) {
    if (isUpgrade && upgradeable.length === 0) {
      descEl.textContent = window.t("billingPlansNoUpgrade");
    } else {
      descEl.textContent = window.t(
        isUpgrade ? "billingPlansDescUpgrade" : "billingPlansDesc"
      );
    }
  }
}

function applyBillingPlansCardVisibility(mode) {
  if (!billingPlansGrid) return;
  const plans = billingState?.plans || [];
  const upgradeable = upgradeablePlans(plans);
  const filterUpgrade =
    mode === "upgrade" && upgradeable.length > 0;
  billingPlansGrid.querySelectorAll(".billing-plan-option").forEach((card) => {
    const plan = plans.find((p) => p.id === card.dataset.plan);
    const hide = filterUpgrade && plan && !plan.is_clickable;
    card.classList.toggle("hidden", Boolean(hide));
  });
}

function clearUpgradeSpotlight() {
  if (upgradeSpotlightTimer) {
    clearTimeout(upgradeSpotlightTimer);
    upgradeSpotlightTimer = null;
  }
  billingPlansGrid
    ?.querySelectorAll(".billing-plan-option.is-upgrade-spotlight")
    .forEach((el) => el.classList.remove("is-upgrade-spotlight"));
}

function spotlightFirstUpgradeCard() {
  clearUpgradeSpotlight();
  const first = billingPlansGrid?.querySelector(
    ".billing-plan-option.is-clickable:not(.hidden)"
  );
  if (!first) return;
  first.classList.add("is-upgrade-spotlight");
  upgradeSpotlightTimer = setTimeout(() => {
    first.classList.remove("is-upgrade-spotlight");
    upgradeSpotlightTimer = null;
  }, 2800);
}

function syncBillingPlansPanelView() {
  if (!billingPlansPanel || billingPlansPanel.classList.contains("hidden")) {
    return;
  }
  const mode = billingPlansPanel.dataset.mode || "all";
  billingPlansPanel.classList.toggle(
    "billing-plans-panel--upgrade",
    mode === "upgrade"
  );
  applyBillingPlansPanelCopy(mode);
  applyBillingPlansCardVisibility(mode);
}

function showBillingPlansPanel(mode = "all") {
  if (!billingPlansPanel) return;
  const panelMode = mode === "upgrade" ? "upgrade" : "all";
  billingPlansPanel.dataset.mode = panelMode;
  billingPlansPanel.classList.toggle(
    "billing-plans-panel--upgrade",
    panelMode === "upgrade"
  );
  applyBillingPlansPanelCopy(panelMode);
  applyBillingPlansCardVisibility(panelMode);
  billingPlansPanel.classList.remove("hidden");
  const scrollTarget =
    panelMode === "upgrade"
      ? billingPlansGrid?.querySelector(
          ".billing-plan-option.is-clickable:not(.hidden)"
        )
      : billingPlansPanel;
  (scrollTarget || billingPlansPanel).scrollIntoView({
    behavior: "smooth",
    block: "nearest",
  });
  if (panelMode === "upgrade") {
    spotlightFirstUpgradeCard();
  } else {
    clearUpgradeSpotlight();
  }
}

function billingMinAmountText(minTopup) {
  const min = minTopup ?? billingState?.min_topup_jpy ?? 500;
  return formatNumber(min);
}

function updateBillingTopupHint(minTopup) {
  if (!billingTopupHint) return;
  const min = billingMinAmountText(minTopup);
  const template = window.t("billingTopupHint");
  billingTopupHint.textContent = template.includes("{min}")
    ? template.replace("{min}", min)
    : `${min}円以上を指定してください`;
}

function updateBillingChargeDesc(minTopup) {
  if (!billingChargeDesc) return;
  const min = billingMinAmountText(minTopup);
  const prefix = window.t("billingChargeDescPrefix");
  const suffix = window.t("billingChargeDescSuffix");
  billingChargeDesc.replaceChildren(
    document.createTextNode(prefix),
    document.createTextNode(min),
    document.createTextNode(suffix)
  );
}

function applyBillingRestrictions(features) {
  const f = features || {};
  const billingOff = Boolean(f.billing_disabled);
  const couponOff = Boolean(f.coupon_disabled);

  document.getElementById("billingTopupDisabledNotice")?.classList.toggle("hidden", !billingOff);
  document.getElementById("billingTopupCard")?.classList.toggle("hidden", billingOff);
  document.getElementById("billingCouponDisabledNotice")?.classList.toggle("hidden", !couponOff);
  document.getElementById("billingCouponCard")?.classList.toggle("hidden", couponOff);
}

function renderUsage(data) {
  billingState = data;
  applyBillingRestrictions(data.features);
  window.applySystemFeatures?.(data.features);

  const minTopup = data.min_topup_jpy ?? 500;
  updateBillingChargeDesc(minTopup);
  if (balanceTopupAmount) {
    balanceTopupAmount.min = String(minTopup);
    if (parseInt(balanceTopupAmount.value, 10) < minTopup) {
      balanceTopupAmount.value = String(minTopup);
    }
  }
  updateBillingTopupHint(minTopup);

  if (billingBalanceValue) {
    billingBalanceValue.textContent = data.balance_label || formatBalanceJpy(data.balance ?? 0);
  }
  if (billingPlanExpiresValue) {
    billingPlanExpiresValue.textContent = data.plan_expires_label || "—";
  }

  if (billingPeriodLabel) {
    billingPeriodLabel.textContent = `${formatPeriod(data.period)}${window.t("billingPeriodSuffix")}`;
  }
  if (billingPlanBadge) {
    billingPlanBadge.textContent = data.plan_name;
    billingPlanBadge.dataset.plan = data.plan;
  }
  if (billingPlanPrice) billingPlanPrice.textContent = data.plan_price_label;
  if (billingCurrentPlan) billingCurrentPlan.dataset.plan = data.plan;
  if (billingPlanDescription) {
    const planDesc = String(data.plan_description ?? "").trim();
    billingPlanDescription.textContent = planDesc;
    billingPlanDescription.classList.toggle("hidden", !planDesc);
  }

  if (billingUsageLabel) {
    billingUsageLabel.textContent = data.usage_display_label || "—";
  }
  if (billingUsageResetNote) {
    const resetLabel = String(data.usage_reset_label || "").trim();
    billingUsageResetNote.textContent = resetLabel;
    billingUsageResetNote.classList.toggle("hidden", !resetLabel);
  }
  if (data.usage_unlimited) {
    if (billingUsageBar) {
      billingUsageBar.style.width = "100%";
      billingUsageBar.classList.remove("is-warning", "is-danger", "is-over-limit");
      billingUsageBar.classList.add("is-normal");
    }
    if (billingUsagePercent) billingUsagePercent.textContent = "—";
    if (billingUsageOverNote) billingUsageOverNote.classList.add("hidden");
  } else {
    applyUsageBarState(
      billingUsageBar,
      billingUsagePercent,
      data.usage_percent ?? 0,
      data.usage_status
    );
    if (billingUsageOverNote) {
      const over = Boolean(data.usage_is_over_limit);
      billingUsageOverNote.classList.toggle("hidden", !over);
      if (over && data.on_demand_billing_enabled) {
        billingUsageOverNote.textContent = "オンデマンド課金中（残高から差し引き）";
      } else if (over) {
        billingUsageOverNote.textContent = window.t?.("billingUsageOverNote") || "超過利用中";
      }
    }
  }

  const poolExpires = String(data.usage_pool_expires_label || "").trim();
  if (billingUsageResetNote && poolExpires) {
    billingUsageResetNote.textContent = `枠の有効期限: ${poolExpires}`;
    billingUsageResetNote.classList.remove("hidden");
  }
  const noteEl = document.getElementById("billingModelNote");
  if (noteEl && data.billing_model_note) {
    noteEl.textContent = data.billing_model_note;
  }
  const descEl = document.getElementById("billingUsageDescText");
  if (descEl && data.active_entitlements?.length) {
    const parts = data.active_entitlements.map(
      (e) => `${e.plan_id}×${e.quantity || 1}`
    );
    descEl.textContent = `有効枠: ${parts.join(" + ")}（合算が利用上限）`;
  }

  syncPresetButtons();
  renderPlans(data.plans || []);
  if (!data.features?.billing_disabled) {
    setupPaypalButtons();
  } else {
    destroyPaypalButtons();
  }
}

function escapeAttr(text) {
  return escapeHtml(text).replace(/"/g, "&quot;");
}

async function copyRequestId(requestId, buttonEl) {
  const text = String(requestId || "").trim();
  if (!text) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    if (buttonEl) {
      buttonEl.classList.add("is-copied");
      buttonEl.setAttribute("aria-label", "コピーしました");
      setTimeout(() => {
        buttonEl.classList.remove("is-copied");
        buttonEl.setAttribute("aria-label", "リクエストIDをコピー");
      }, 1600);
    }
    window.NexNotify?.showSuccess?.("リクエストIDをコピーしました", { durationMs: 2000 });
  } catch {
    window.NexNotify?.showError?.("コピーに失敗しました");
  }
}

function formatRequestLogTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function renderBillingRequestLogs(payload) {
  const body = document.getElementById("billingRequestLogsBody");
  if (!body) return;
  const events = payload?.events || [];
  if (!events.length) {
    body.innerHTML =
      '<tr><td colspan="8" class="billing-request-logs-empty">リクエストログはまだありません</td></tr>';
    return;
  }
  body.innerHTML = events
    .map((ev) => {
      const rawId = String(ev.request_id || ev.id || "").trim();
      const idHtml = escapeHtml(rawId);
      const shortId =
        rawId.length > 14 ? `${escapeHtml(rawId.slice(0, 8))}…${escapeHtml(rawId.slice(-4))}` : idHtml;
      const session = escapeHtml(ev.session_id || "—");
      const shortSession =
        session.length > 14 ? `${escapeHtml(session.slice(0, 10))}…` : session;
      return `<tr>
        <td class="billing-log-id">
          <button type="button" class="billing-request-id-copy" data-copy-request-id="${escapeAttr(rawId)}" title="リクエストIDをコピー" aria-label="リクエストIDをコピー">
            <code>${shortId}</code>
          </button>
        </td>
        <td>${escapeHtml(ev.status_label || ev.status || "—")}</td>
        <td>${escapeHtml(formatRequestLogTime(ev.created_at))}</td>
        <td title="${session}"><code>${shortSession}</code></td>
        <td>${Number(ev.tool_call_count) || 0}</td>
        <td>${escapeHtml(ev.payment_type_label || ev.payment_type || "—")}</td>
        <td>${escapeHtml(ev.billing_plan_label || ev.billing_plan || "—")}</td>
        <td>$${Number(ev.cost_usd || 0).toFixed(4)}</td>
      </tr>`;
    })
    .join("");
}

async function loadBillingRequestLogs() {
  const body = document.getElementById("billingRequestLogsBody");
  if (!body) return;
  try {
    const res = await fetch("/api/billing/request-logs?limit=80");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "ログの取得に失敗しました");
    if (data.billing_model_note) {
      const noteEl = document.getElementById("billingModelNote");
      if (noteEl) noteEl.textContent = data.billing_model_note;
    }
    renderBillingRequestLogs(data);
  } catch (err) {
    body.innerHTML = `<tr><td colspan="8" class="billing-request-logs-empty">${escapeHtml(err.message)}</td></tr>`;
  }
}

function handleSubscriptionReturnQuery() {
  const params = new URLSearchParams(window.location.search);
  const sub = params.get("subscription");
  if (!sub) return;
  const isSuccess = sub === "success";
  showBillingMsg(
    balanceTopupMsg,
    isSuccess
      ? "PayPalでの申し込みを受け付けました。プラン反映まで数十秒かかる場合があります。"
      : "PayPalの申し込みがキャンセルされました",
    !isSuccess
  );
  params.delete("subscription");
  const qs = params.toString();
  const path = window.location.pathname + (window.location.hash || "");
  window.history.replaceState({}, "", qs ? `${path}?${qs}` : path);
}

async function loadBillingUsage() {
  if (!billingLoading || !billingContent) return;

  closeBalancePaymentConfirm();
  billingLoading.classList.remove("hidden");
  billingViewStage?.classList.add("hidden");
  billingError?.classList.add("hidden");

  try {
    const res = await fetch("/api/billing/usage");
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "利用量の取得に失敗しました");
    }
    renderUsage(data);
    await loadBillingRequestLogs();
    billingLoading.classList.add("hidden");
    billingViewStage?.classList.remove("hidden");
    setBillingView(BILLING_VIEW_MAIN);
    handleSubscriptionReturnQuery();
  } catch (err) {
    billingLoading.classList.add("hidden");
    if (billingError) {
      billingError.textContent = err.message;
      billingError.classList.remove("hidden");
    }
  }
}

billingPresetButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const amount = btn.dataset.amount;
    if (balanceTopupAmount && amount) balanceTopupAmount.value = amount;
    if (balanceTopupMsg) balanceTopupMsg.classList.add("hidden");
    syncPresetButtons();
  });
});

balanceTopupAmount?.addEventListener("input", () => {
  if (balanceTopupMsg) balanceTopupMsg.classList.add("hidden");
  syncPresetButtons();
});

if (couponRedeemForm) {
  couponRedeemForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (couponRedeemMsg) couponRedeemMsg.classList.add("hidden");
    const code = document.getElementById("couponRedeemCode")?.value.trim();
    if (!code) return;

    try {
      const res = await fetch("/api/coupons/redeem", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "利用に失敗しました");

      if (data.billing) renderUsage(data.billing);
      if (data.user) {
        window.__USER__ = data.user;
        window.updateAccountDisplay?.(data.user);
      }
      couponRedeemForm.reset();
      const successMsg = data.message || "クーポンを利用しました";
      showBillingMsg(couponRedeemMsg, successMsg, false);
      window.NexCelebrate?.celebrate();
      window.NexNotify?.showSuccess(successMsg, { durationMs: 4000 });
    } catch (err) {
      showBillingMsg(couponRedeemMsg, err.message, true);
    }
  });
}

billingUpgradePlanBtn?.addEventListener("click", () =>
  showBillingPlansPanel("upgrade")
);
billingViewPlansBtn?.addEventListener("click", () =>
  showBillingPlansPanel("all")
);

billingBalanceConfirmBack?.addEventListener("click", () => {
  closeBalancePaymentConfirm();
  showBillingPlansPanel("all");
});

billingBalanceConfirmCancel?.addEventListener("click", () => {
  closeBalancePaymentConfirm();
  showBillingPlansPanel("all");
});

billingBalanceConfirmSubmit?.addEventListener("click", () => {
  if (pendingBalancePlan) executeBalancePlanSubscription(pendingBalancePlan);
});

billingBalanceCouponToggle?.addEventListener("click", () => {
  billingBalanceCouponPanel?.classList.toggle("hidden");
  if (!billingBalanceCouponPanel?.classList.contains("hidden")) {
    billingBalanceCouponCode?.focus();
  }
});

billingBalanceCouponApply?.addEventListener("click", () => {
  void applyBalancePurchaseCoupon();
});

billingBalanceCouponCode?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    void applyBalancePurchaseCoupon();
  }
});

async function applyBalancePurchaseCoupon() {
  if (!pendingBalancePlan?.id) return;
  if (billingBalanceCouponMsg) billingBalanceCouponMsg.classList.add("hidden");
  const code = billingBalanceCouponCode?.value.trim();
  if (!code) {
    showBillingMsg(
      billingBalanceCouponMsg,
      window.t?.("billingCouponCodeRequired") || "クーポンコードを入力してください",
      true
    );
    return;
  }
  billingBalanceCouponApply?.setAttribute("disabled", "disabled");
  try {
    const res = await fetch("/api/billing/preview-purchase-coupon", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_id: pendingBalancePlan.id, code }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "クーポンを適用できませんでした");
    pendingPurchaseCouponCode = data.code || code;
    pendingPurchaseDiscountJpy = Math.round(Number(data.discount_jpy) || 0);
    updateBalanceConfirmPricing(pendingBalancePlan);
    billingBalanceCouponPanel?.classList.add("hidden");
    showBillingMsg(
      billingBalanceCouponMsg,
      data.benefit_label ||
        window.t?.("billingBalanceCouponAppliedSuccess") ||
        "クーポンを適用しました",
      false
    );
  } catch (err) {
    pendingPurchaseCouponCode = null;
    pendingPurchaseDiscountJpy = 0;
    updateBalanceConfirmPricing(pendingBalancePlan);
    showBillingMsg(billingBalanceCouponMsg, err.message, true);
  } finally {
    billingBalanceCouponApply?.removeAttribute("disabled");
  }
}

window.billingApp = { loadUsage: loadBillingUsage, refreshPlans: () => {
  if (billingState) renderPlans(billingState.plans || []);
} };

document.getElementById("billingRequestLogsBody")?.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-copy-request-id]");
  if (!btn) return;
  e.preventDefault();
  void copyRequestId(btn.getAttribute("data-copy-request-id"), btn);
});

initPaypalThemeObserver();

const prevBillingApplyLanguage = window.applyLanguage;
window.applyLanguage = function (lang) {
  prevBillingApplyLanguage?.(lang);
  if (!billingState) return;
  renderPlans(billingState.plans || []);
  if (!billingPlanDescription) return;
  const currentPlan = (billingState.plans || []).find((p) => p.is_current);
  const planDesc = currentPlan ? planMarketingDescription(currentPlan) : "";
  billingPlanDescription.textContent = planDesc;
  billingPlanDescription.classList.toggle("hidden", !planDesc);
  syncBillingPlansPanelView();
};
