let csrfToken = null;
const message = document.querySelector("#message");
const loginForm = document.querySelector("#login-form");
const registerForm = document.querySelector("#register-form");
const signedOut = document.querySelector("#signed-out");
const signedIn = document.querySelector("#signed-in");

function notify(text, state = "") {
  message.textContent = text;
  message.dataset.state = state;
}

function busy(value) {
  document.querySelectorAll("button").forEach(button => { button.disabled = value; });
}

function selectForm(mode) {
  loginForm.hidden = mode !== "login";
  registerForm.hidden = mode !== "register";
  document.querySelector("#show-login").setAttribute("aria-pressed", String(mode === "login"));
  document.querySelector("#show-register").setAttribute("aria-pressed", String(mode === "register"));
}

function renderUser(user) {
  signedIn.hidden = !user;
  signedOut.hidden = Boolean(user);
  document.querySelector("#current-username").textContent = user ? user.username : "";
  document.querySelector(".intro").textContent = user ? "查看当前账号，或安全退出登录。" : "登录你的账号，开始使用。";
}

async function api(path, body) {
  if (body !== undefined && !csrfToken) throw new Error("安全令牌不可用，请重新检查登录状态。");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  const options = { credentials: "same-origin", cache: "no-store", signal: controller.signal };
  if (body !== undefined) {
    options.method = "POST";
    options.headers = { "Content-Type": "application/json", "X-CSRF-Token": csrfToken };
    options.body = JSON.stringify(body);
  }
  try {
    const response = await fetch(`/api/auth/${path}`, options);
    const result = await response.json();
    if (!response.ok) {
      const error = new Error(result.message || "操作失败，请稍后重试。");
      error.status = response.status;
      throw error;
    }
    return result;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，未确认操作成功。请重新检查登录状态。");
    if (error instanceof TypeError) throw new Error("无法连接后端，请稍后重试。");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function refreshSession() {
  busy(true);
  csrfToken = null;
  notify("正在检查登录状态…");
  try {
    csrfToken = (await api("csrf")).csrf_token;
    try {
      renderUser((await api("me")).user);
      notify("登录状态有效。", "ok");
    } catch (error) {
      if (error.status !== 401) throw error;
      renderUser(null);
      notify("尚未登录，请登录或创建账号。");
    }
  } catch (error) {
    // Do not present cached identity as an authenticated success after connection failure.
    signedIn.hidden = true;
    signedOut.hidden = true;
    notify(error.message, "error");
  } finally { busy(false); }
}

document.querySelector("#show-login").addEventListener("click", () => selectForm("login"));
document.querySelector("#show-register").addEventListener("click", () => selectForm("register"));
document.querySelector("#refresh-session").addEventListener("click", refreshSession);

registerForm.addEventListener("submit", async event => {
  event.preventDefault();
  busy(true);
  const values = new FormData(registerForm);
  try {
    const result = await api("register", { username: values.get("username"), password: values.get("password") });
    registerForm.reset();
    loginForm.elements.username.value = result.user.username;
    selectForm("login");
    notify(result.message, "ok");
    loginForm.elements.password.focus();
  } catch (error) { notify(error.message, "error"); }
  finally { busy(false); }
});

loginForm.addEventListener("submit", async event => {
  event.preventDefault();
  busy(true);
  const values = new FormData(loginForm);
  try {
    const result = await api("login", { username: values.get("username"), password: values.get("password") });
    csrfToken = result.csrf_token;
    loginForm.reset();
    renderUser(result.user);
    notify("登录成功。", "ok");
  } catch (error) { notify(error.message, "error"); }
  finally { busy(false); }
});

document.querySelector("#logout").addEventListener("click", async () => {
  busy(true);
  try {
    const result = await api("logout", {});
    csrfToken = null;
    renderUser(null);
    selectForm("login");
    notify(result.message, "ok");
    csrfToken = (await api("csrf")).csrf_token;
  } catch (error) {
    signedIn.hidden = true;
    signedOut.hidden = true;
    if (error.status === 401 || error.status === 403) csrfToken = null;
    notify(error.message + " 请重新检查登录状态。", "error");
  }
  finally { busy(false); }
});

refreshSession();
