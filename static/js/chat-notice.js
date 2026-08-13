(function () {
  const notice = document.getElementById("chatRestrictionNotice");
  const textEl = document.getElementById("chatRestrictionNoticeText");
  const billingLink = document.getElementById("chatRestrictionBillingLink");
  const dismissBtn = document.getElementById("chatRestrictionNoticeDismiss");

  function hideChatRestrictionNotice() {
    notice?.classList.add("hidden");
  }

  function showChatRestrictionNotice(message, { showBillingLink = true } = {}) {
    if (!notice || !textEl || !message) return;
    textEl.textContent = message;
    billingLink?.classList.toggle("hidden", !showBillingLink);
    notice.classList.remove("hidden");
    notice.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  billingLink?.addEventListener("click", (e) => {
    e.preventDefault();
    if (window.NexRouter?.navigate) {
      window.NexRouter.navigate("/billing");
    } else {
      window.location.href = "/billing";
    }
    hideChatRestrictionNotice();
  });

  dismissBtn?.addEventListener("click", hideChatRestrictionNotice);

  window.showChatRestrictionNotice = showChatRestrictionNotice;
  window.hideChatRestrictionNotice = hideChatRestrictionNotice;
})();
