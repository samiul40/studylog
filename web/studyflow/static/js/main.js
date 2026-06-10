// Global Utilities
function handleSubmit(button) {
  button.disabled = true;

  button.querySelector(".btn-text")?.classList.add("d-none");
  button.querySelector(".spinner-border")?.classList.remove("d-none");

  button.form.submit();
}

// Duration picker: syncs h/m visible inputs → hidden total-minutes field
function initDurationPickers(root) {
  root.querySelectorAll(".duration-picker").forEach(picker => {
    const hoursInput = picker.querySelector(".dp-hours");
    const minsInput = picker.querySelector(".dp-mins");
    const hidden = picker.querySelector("input[type='hidden']");
    if (!hoursInput || !minsInput || !hidden) return;

    function sync() {
      const h = parseInt(hoursInput.value) || 0;
      const m = parseInt(minsInput.value) || 0;
      hidden.value = h * 60 + m || "";
    }

    hoursInput.addEventListener("input", sync);
    minsInput.addEventListener("input", sync);
  });
}

// Mark as Complete button — copies duration picker values into progress picker
function initMarkComplete(root) {
  root.querySelectorAll('[data-action="mark-complete"]').forEach(btn => {
    btn.addEventListener("click", () => {
      const modal = btn.closest(".modal");
      if (!modal) return;

      const pickers = modal.querySelectorAll(".duration-picker");
      if (pickers.length < 2) return;

      const durationPicker = pickers[0];
      const progressPicker = pickers[1];

      progressPicker.querySelector(".dp-hours").value = durationPicker.querySelector(".dp-hours").value;
      progressPicker.querySelector(".dp-mins").value = durationPicker.querySelector(".dp-mins").value;

      progressPicker.querySelector(".dp-hours").dispatchEvent(new Event("input"));
    });
  });
}

// Toggle password
function togglePassword() {
  const toggle = document.getElementById("togglePass");
  const icon = document.getElementById("togglePassword");
  const password = document.getElementById("password");

  if (!toggle || !password || !icon) return;

  toggle.addEventListener("click", () => {
    const isPassword = password.type === "password";
    password.type = isPassword ? "text" : "password";

    icon.classList.toggle("fa-eye");
    icon.classList.toggle("fa-eye-slash");
  });
}

// KPI count-up — animates .kpi-value integers from 0 on page load
function initCountUp() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  document.querySelectorAll(".kpi-value").forEach(el => {
    const target = parseInt(el.textContent.trim(), 10);
    if (isNaN(target) || target <= 1) return;

    el.textContent = "0";
    const duration = Math.min(600 + target * 12, 1000);
    const startTime = performance.now();

    function tick(now) {
      const t = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
      el.textContent = Math.round(eased * target);
      if (t < 1) requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
  });
}

// Init All
document.addEventListener("DOMContentLoaded", function () {
  // Move all modals to <body> so Bootstrap's backdrop (also appended to body)
  // doesn't paint over them — the pageFadeIn animation on <main> creates a
  // stacking context that otherwise traps the modal below the backdrop.
  document.querySelectorAll("main .modal").forEach(function (modal) {
    document.body.appendChild(modal);
  });

  togglePassword();
  initDurationPickers(document);
  initMarkComplete(document);
  initCountUp();

  // CSP-safe replacement for onclick="handleSubmit(this)" on spinner submit buttons
  document.addEventListener("click", function (e) {
    const btn = e.target.closest('button[type="submit"]');
    if (!btn || !btn.querySelector(".spinner-border")) return;
    e.preventDefault();
    handleSubmit(btn);
  });
});
