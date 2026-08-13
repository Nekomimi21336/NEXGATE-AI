const authForm = document.getElementById("authForm");
const authError = document.getElementById("authError");
const authSubmit = document.getElementById("authSubmit");
const authSubtitle = document.getElementById("authSubtitle");
const authTitle = document.getElementById("authTitle");
const toggleMode = document.getElementById("toggleMode");
const authSwitchLabel = document.getElementById("authSwitchLabel");
const loginFields = document.getElementById("loginFields");
const registerFields = document.getElementById("registerFields");
const authSwitchWrap = document.getElementById("authSwitchWrap");

const usernameLogin = document.getElementById("username");
const passwordLogin = document.getElementById("password");
const displayNameInput = document.getElementById("displayName");
const regUsername = document.getElementById("regUsername");
const emailInput = document.getElementById("email");
const phoneInput = document.getElementById("phone");
const regPassword = document.getElementById("regPassword");
const usernameHint = document.getElementById("usernameHint");

const USERNAME_TAKEN_MSG = "このユーザー名は登録できません";
const GOOGLE_LOGIN_ERRORS = {
  disabled: "Google ログインは現在利用できません",
  not_configured: "Google ログインが設定されていません",
  invalid_state: "認証セッションが無効です。もう一度お試しください",
  missing_code: "認証コードがありません。もう一度お試しください",
  registration_disabled: "現在、新規登録は停止されています",
  redirect_uri_mismatch:
    "Google OAuth の Redirect URI が一致しません。管理画面の設定と Google Cloud Console を確認してください",
  invalid_grant: "認証コードが無効または期限切れです。もう一度ログインしてください",
  invalid_client: "Google OAuth のクライアント設定が不正です。管理者に連絡してください",
  token_exchange_failed: "Google との認証に失敗しました。もう一度お試しください",
  profile_incomplete: "Google プロフィール情報が不足しています",
  no_access_token: "Google からアクセストークンを取得できませんでした",
  login_disabled:
    "このアカウントでは Google ログインが無効です。設定の連携から有効にしてください",
  email_exists:
    "このメールは既に登録されています。ログイン後、設定の連携から Google ログインを有効にしてください",
  google_linked_other: "この Google アカウントは別のユーザーに紐づいています",
  account_blocked: "このアカウントは利用停止中です",
  oauth_failed: "Google ログインに失敗しました。もう一度お試しください",
};

const DISCORD_LOGIN_ERRORS = {
  disabled: "Discord ログインは現在利用できません",
  not_configured: "Discord ログインが設定されていません",
  invalid_state: "認証セッションが無効です。もう一度お試しください",
  missing_code: "認証コードがありません。もう一度お試しください",
  registration_disabled: "現在、新規登録は停止されています",
};

const authLayout = document.getElementById("authLayout");
const authOauthButtons = document.getElementById("authOauthButtons");
const authGoogleBtn = document.getElementById("authGoogleBtn");
const authGoogleBtnLabel = document.getElementById("authGoogleBtnLabel");
const authDiscordBtn = document.getElementById("authDiscordBtn");
const authDiscordBtnLabel = document.getElementById("authDiscordBtnLabel");

let isRegister = false;
let usernameCheckTimer = null;
let lastUsernameCheck = "";

function setFieldHint(el, text, state) {
  if (!el) return;
  el.textContent = text;
  el.classList.remove("hidden", "is-error", "is-ok");
  if (state === "error") el.classList.add("is-error");
  if (state === "ok") el.classList.add("is-ok");
}

function setInputState(input, state) {
  if (!input) return;
  input.classList.remove("auth-input--error", "auth-input--ok");
  if (state === "error") input.classList.add("auth-input--error");
  if (state === "ok") input.classList.add("auth-input--ok");
}

function showAuthError(message) {
  if (!authError) return;
  if (message) {
    authError.textContent = message;
    authError.classList.remove("hidden");
  } else {
    authError.classList.add("hidden");
  }
}

function updateRegistrationUi() {
  const disabled = Boolean(window.__SYSTEM_FEATURES__?.registration_disabled);
  if (!authSwitchWrap) return;
  if (disabled) {
    isRegister = false;
    applyAuthMode();
    authSwitchWrap.classList.add("hidden");
  } else {
    authSwitchWrap.classList.remove("hidden");
  }
}

function applyAuthMode() {
  document.body.classList.toggle("auth-mode-register", isRegister);
  authLayout?.classList.toggle("auth-layout--register", isRegister);

  loginFields?.classList.toggle("hidden", isRegister);
  registerFields?.classList.toggle("hidden", !isRegister);

  if (authTitle) {
    authTitle.textContent = isRegister ? "アカウント作成" : "ログイン";
  }
  if (authSubtitle) {
    authSubtitle.textContent = isRegister
      ? "必要事項を入力して無料で始められます（初期プラン: Free）"
      : "ユーザー名またはメールアドレスでサインイン";
  }
  if (authSubmit) {
    authSubmit.textContent = isRegister ? "アカウントを作成" : "ログイン";
  }
  if (toggleMode) {
    toggleMode.textContent = isRegister ? "ログイン画面に戻る" : "新規アカウントを作成";
  }
  if (authSwitchLabel) {
    authSwitchLabel.textContent = isRegister
      ? "すでにアカウントをお持ちの方"
      : "アカウントをお持ちでない方";
  }
  updateOAuthLoginUi();

  usernameLogin.required = !isRegister;
  passwordLogin.required = !isRegister;
  displayNameInput.required = isRegister;
  regUsername.required = isRegister;
  emailInput.required = isRegister;
  regPassword.required = isRegister;

  usernameLogin.disabled = isRegister;
  passwordLogin.disabled = isRegister;
  displayNameInput.disabled = !isRegister;
  regUsername.disabled = !isRegister;
  emailInput.disabled = !isRegister;
  phoneInput.disabled = !isRegister;
  regPassword.disabled = !isRegister;

  showAuthError("");
  if (!isRegister) {
    setFieldHint(usernameHint, "英字・数字・_ -（3〜32文字）", null);
    setInputState(regUsername, null);
  }
}

function updateOAuthLoginUi() {
  const googleAvailable = Boolean(window.__SYSTEM_FEATURES__?.google_login_available);
  const discordAvailable = Boolean(window.__SYSTEM_FEATURES__?.discord_login_available);
  authOauthButtons?.classList.toggle("hidden", !googleAvailable && !discordAvailable);
  authGoogleBtn?.classList.toggle("hidden", !googleAvailable);
  authDiscordBtn?.classList.toggle("hidden", !discordAvailable);
  if (authGoogleBtnLabel) {
    authGoogleBtnLabel.textContent = isRegister
      ? "Googleで登録"
      : "Googleでログイン";
  }
  if (authDiscordBtnLabel) {
    authDiscordBtnLabel.textContent = isRegister
      ? "Discordで登録"
      : "Discordでログイン";
  }
}

const VERIFY_MESSAGES = {
  success: "メールアドレスの確認が完了しました。ログインしてください。",
  already: "このアカウントは既に登録済みです。ログインしてください。",
  email_used: "このメールアドレスは既に登録されています。",
  missing: "認証リンクが無効です。",
  error: "メール認証に失敗しました。",
};

function handleOAuthLoginRedirectQuery() {
  const params = new URLSearchParams(location.search);
  const googleErr = params.get("google_login_error");
  const discordErr = params.get("discord_login_error");
  const verify = params.get("verify");
  if (verify) {
    const message =
      verify === "error"
        ? params.get("message") || VERIFY_MESSAGES.error
        : VERIFY_MESSAGES[verify] || VERIFY_MESSAGES.error;
    if (verify === "success") {
      if (authError) {
        authError.textContent = message;
        authError.classList.remove("hidden");
        authError.classList.add("auth-error--success");
      }
    } else {
      authError?.classList.remove("auth-error--success");
      showAuthError(message);
    }
    params.delete("verify");
    params.delete("message");
  }
  const err = googleErr || discordErr;
  if (err) {
    const message = googleErr
      ? GOOGLE_LOGIN_ERRORS[googleErr] || decodeURIComponent(googleErr)
      : DISCORD_LOGIN_ERRORS[discordErr] || decodeURIComponent(discordErr);
    showAuthError(message);
    params.delete("google_login_error");
    params.delete("discord_login_error");
  }
  if (!verify && !err) return;
  const qs = params.toString();
  const next = location.pathname + (qs ? `?${qs}` : "") + location.hash;
  history.replaceState(history.state, "", next);
}

updateRegistrationUi();
applyAuthMode();
updateOAuthLoginUi();
handleOAuthLoginRedirectQuery();

toggleMode?.addEventListener("click", () => {
  if (window.__SYSTEM_FEATURES__?.registration_disabled) return;
  isRegister = !isRegister;
  applyAuthMode();
});

async function checkUsernameAvailable(username) {
  const res = await fetch(
    `/api/auth/check-username?username=${encodeURIComponent(username)}`
  );
  const data = await res.json();
  return data;
}

function scheduleUsernameCheck() {
  if (!isRegister || !regUsername) return;
  const raw = regUsername.value.trim();
  clearTimeout(usernameCheckTimer);
  if (!raw) {
    setFieldHint(usernameHint, "英字・数字・_ -（3〜32文字）", null);
    setInputState(regUsername, null);
    return;
  }
  usernameCheckTimer = setTimeout(async () => {
    if (raw === lastUsernameCheck) return;
    lastUsernameCheck = raw;
    try {
      const data = await checkUsernameAvailable(raw);
      if (regUsername.value.trim() !== raw) return;
      if (data.available) {
        setFieldHint(usernameHint, "このユーザー名は利用できます", "ok");
        setInputState(regUsername, "ok");
      } else {
        const msg =
          data.error === "このユーザー名は登録できません" ||
          data.error === "このユーザー名は既に使われています"
            ? USERNAME_TAKEN_MSG
            : data.error || USERNAME_TAKEN_MSG;
        setFieldHint(usernameHint, msg, "error");
        setInputState(regUsername, "error");
      }
    } catch {
      setFieldHint(usernameHint, "確認できませんでした", null);
      setInputState(regUsername, null);
    }
  }, 400);
}

regUsername?.addEventListener("input", scheduleUsernameCheck);
regUsername?.addEventListener("blur", scheduleUsernameCheck);

function validateRegisterClient() {
  const display_name = displayNameInput?.value.trim() || "";
  const username = regUsername?.value.trim() || "";
  const email = emailInput?.value.trim() || "";
  const password = regPassword?.value || "";

  if (!display_name) return "表示名を入力してください";
  if (!username) return "ユーザー名を入力してください";
  if (!/^[a-zA-Z0-9_-]{3,32}$/.test(username)) {
    return "ユーザー名は英字・数字・アンダースコア・ハイフンのみ（3〜32文字）";
  }
  if (!email) return "メールアドレスを入力してください";
  if (password.length < 4) return "パスワードは4文字以上で入力してください";
  return null;
}

authForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  showAuthError("");

  authSubmit.disabled = true;

  try {
    if (isRegister) {
      const clientErr = validateRegisterClient();
      if (clientErr) {
        showAuthError(clientErr);
        return;
      }

      const username = regUsername.value.trim();
      const check = await checkUsernameAvailable(username);
      if (!check.available) {
        const msg =
          check.error === "このユーザー名は登録できません" ||
          check.error === "このユーザー名は既に使われています"
            ? USERNAME_TAKEN_MSG
            : check.error || USERNAME_TAKEN_MSG;
        setFieldHint(usernameHint, msg, "error");
        setInputState(regUsername, "error");
        showAuthError(msg);
        return;
      }

      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password: regPassword.value,
          display_name: displayNameInput.value.trim(),
          email: emailInput.value.trim(),
          phone: phoneInput.value.trim(),
        }),
      });
      const data = await res.json();
      if (res.status === 202 && data.verification_required) {
        isRegister = false;
        applyAuthMode();
        showAuthError(data.message || "確認メールを送信しました。メール内のリンクから登録を完了してください。");
        return;
      }
      if (!res.ok) {
        const err =
          res.status === 409
            ? USERNAME_TAKEN_MSG
            : data.error || "登録に失敗しました";
        if (res.status === 409) {
          setFieldHint(usernameHint, USERNAME_TAKEN_MSG, "error");
          setInputState(regUsername, "error");
        }
        showAuthError(err);
        return;
      }
      applyThemeAndRedirect(data.user);
      return;
    }

    if (!isRegister) {
      const loginId = usernameLogin.value.trim();
      if (!loginId || !passwordLogin.value) {
        showAuthError("ユーザー名またはメールアドレスとパスワードを入力してください");
        return;
      }
    }

    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: usernameLogin.value.trim(),
        password: passwordLogin.value,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      showAuthError(data.error || "ログインに失敗しました");
      return;
    }
    applyThemeAndRedirect(data.user);
  } catch {
    showAuthError("通信エラーが発生しました");
  } finally {
    authSubmit.disabled = false;
  }
});

function applyThemeAndRedirect(user) {
  if (user?.theme) {
    try {
      localStorage.setItem("nexgate_theme", user.theme);
      document.documentElement.setAttribute("data-theme", user.theme);
    } catch (e) {}
  }
  if (user?.chat_background_pattern) {
    try {
      localStorage.setItem("nexgate_chat_background", user.chat_background_pattern);
      document.documentElement.setAttribute("data-chat-background", user.chat_background_pattern);
    } catch (e) {}
  }
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");
  if (next && next.startsWith("/") && !next.startsWith("//")) {
    window.location.href = next;
    return;
  }
  window.location.href = "/chat";
}
