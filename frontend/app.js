const button = document.querySelector("#recheck");
const checkedAt = document.querySelector("#checked-at");

function show(name, state, label, detail) {
  const status = document.querySelector(`#${name}-status`);
  status.dataset.state = state;
  status.textContent = label;
  document.querySelector(`#${name}-detail`).textContent = detail;
}

async function check(name, url) {
  show(name, "pending", "检查中…", "正在请求实时状态。");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(url, { cache: "no-store", signal: controller.signal });
    const result = await response.json();
    if (response.ok && result.status === "ok") {
      show(name, "ok", "正常", result.message);
    } else {
      show(name, "error", "检查失败", result.message || "检查未成功，请稍后重试。");
    }
  } catch (error) {
    const message = error.name === "AbortError"
      ? "请求超时，请稍后重试。"
      : "无法取得检查结果，请确认后端服务已启动。";
    show(name, "error", "检查失败", message);
  } finally {
    clearTimeout(timer);
  }
}

async function checkAll() {
  button.disabled = true;
  button.textContent = "检查中…";
  await Promise.all([
    check("backend", "/api/health/live"),
    check("database", "/api/health/database"),
  ]);
  checkedAt.textContent = `检查完成：${new Date().toLocaleString("zh-CN", { hour12: false })}`;
  button.disabled = false;
  button.textContent = "重新检查";
}

button.addEventListener("click", checkAll);
checkAll();
