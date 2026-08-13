(function () {
  let rootEl = null;
  let activeRequest = null;

  function t(key) {
    return window.t?.(key) || key;
  }

  function esc(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function enabled() {
    return window.__USER__?.user_questions_enabled === true;
  }

  function ensureRoot() {
    if (rootEl) return rootEl;
    const host =
      document.querySelector("#viewChat .input-wrapper") ||
      document.querySelector(".input-wrapper");
    if (!host) return null;
    rootEl = document.createElement("div");
    rootEl.id = "userQuestionModal";
    rootEl.className = "user-question-modal hidden";
    rootEl.setAttribute("role", "dialog");
    rootEl.setAttribute("aria-modal", "true");
    rootEl.setAttribute("aria-labelledby", "userQuestionModalTitle");
    const inputRow = host.querySelector(".input-row");
    if (inputRow) {
      host.insertBefore(rootEl, inputRow);
    } else {
      host.appendChild(rootEl);
    }
    return rootEl;
  }

  function hide() {
    rootEl?.classList.add("hidden");
    activeRequest = null;
    if (rootEl) rootEl.innerHTML = "";
  }

  function collectAnswers(formEl, questions) {
    const answers = [];
    for (const question of questions || []) {
      const qid = question.id;
      const field = formEl.querySelector(`[data-question-id="${CSS.escape(qid)}"]`);
      if (!field) continue;
      let answer = "";
      if (field.type === "radio") {
        const checked = formEl.querySelector(
          `input[name="uq-${CSS.escape(qid)}"]:checked`
        );
        answer = checked?.value || "";
        const custom = formEl.querySelector(`[data-custom-for="${CSS.escape(qid)}"]`);
        if (checked?.dataset?.custom === "1" && custom) {
          answer = custom.value.trim();
        }
      } else {
        answer = field.value.trim();
      }
      if (answer) {
        answers.push({ id: qid, answer });
      }
    }
    return answers;
  }

  function render(payload) {
    const el = ensureRoot();
    if (!el || !payload) return;
    const questions = Array.isArray(payload.questions) ? payload.questions : [];
    const intro = String(payload.intro || "").trim();
    activeRequest = {
      token: payload.token,
      questions,
    };

    const questionHtml = questions
      .map((question, index) => {
        const qid = question.id || `q${index + 1}`;
        const prompt = question.prompt || "";
        const choices = Array.isArray(question.choices) ? question.choices : [];
        const allowCustom = question.allow_custom !== false;
        const name = `uq-${qid}`;
        let choicesHtml = "";
        if (choices.length) {
          choicesHtml = choices
            .map(
              (choice, choiceIndex) => `
              <label class="user-question-choice">
                <input type="radio" name="${esc(name)}" value="${esc(choice)}" data-question-id="${esc(qid)}"${choiceIndex === 0 ? " checked" : ""}>
                <span>${esc(choice)}</span>
              </label>`
            )
            .join("");
          if (allowCustom) {
            choicesHtml += `
              <label class="user-question-choice">
                <input type="radio" name="${esc(name)}" value="" data-question-id="${esc(qid)}" data-custom="1">
                <span>${esc(t("userQuestionsCustomChoice"))}</span>
              </label>
              <input type="text" class="user-question-custom-input" data-custom-for="${esc(qid)}" placeholder="${esc(t("userQuestionsCustomPlaceholder"))}" autocomplete="off">`;
          }
        } else {
          choicesHtml = `
            <input type="text" class="user-question-text-input" data-question-id="${esc(qid)}" placeholder="${esc(t("userQuestionsAnswerPlaceholder"))}" autocomplete="off">`;
        }
        return `
          <fieldset class="user-question-item">
            <legend class="user-question-prompt">${esc(prompt)}</legend>
            <div class="user-question-choices">${choicesHtml}</div>
          </fieldset>`;
      })
      .join("");

    el.innerHTML = `
      <div class="user-question-modal-inner">
        <header class="user-question-modal-head">
          <h3 class="user-question-modal-title" id="userQuestionModalTitle">${esc(t("userQuestionsModalTitle"))}</h3>
          <button type="button" class="user-question-modal-close" aria-label="${esc(t("userQuestionsClose"))}">×</button>
        </header>
        ${intro ? `<p class="user-question-modal-intro">${esc(intro)}</p>` : ""}
        <form class="user-question-form" id="userQuestionForm">
          ${questionHtml}
          <div class="user-question-modal-actions">
            <button type="submit" class="user-question-submit">${esc(t("userQuestionsSubmit"))}</button>
          </div>
        </form>
      </div>`;

    el.classList.remove("hidden");

    el.querySelector(".user-question-modal-close")?.addEventListener("click", () => {
      const req = activeRequest;
      hide();
      if (req?.token) {
        window.NexUserQuestions?.onDismiss?.(req.token);
      }
    });

    const form = el.querySelector("#userQuestionForm");
    form?.addEventListener("submit", (event) => {
      event.preventDefault();
      const req = activeRequest;
      if (!req?.token) return;
      const answers = collectAnswers(form, req.questions);
      hide();
      window.NexUserQuestions?.onSubmit?.(req.token, answers);
    });
  }

  window.NexUserQuestionModal = {
    enabled,
    show: render,
    hide,
    isVisible: () => Boolean(activeRequest && !rootEl?.classList.contains("hidden")),
  };
})();
