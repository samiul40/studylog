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

// Bulk Unit Modal Logic
function addRow(title = "", duration = "", contentKind = "") {
  const table = document.querySelector("#units-table tbody");
  if (!table) return;

  const row = document.createElement("tr");

  const totalMins = parseInt(duration) || 0;
  const durationHours = Math.floor(totalMins / 60);
  const durationMins = totalMins % 60;

  const durationCell =
    contentKind !== "reading"
      ? `
        <td>
          <div class="duration-picker">
            <div class="input-group input-group-sm">
              <input type="number" class="form-control dp-hours" min="0" placeholder="h" value="${durationHours || ""}">
              <span class="input-group-text">h</span>
              <input type="number" class="form-control dp-mins" min="0" max="59" placeholder="m" value="${durationMins || ""}">
              <span class="input-group-text">m</span>
            </div>
            <input type="hidden" name="duration[]" value="${duration}">
          </div>
        </td>
      `
      : "";

  row.innerHTML = `
    <td>
      <input type="text" name="title[]" class="form-control" value="${title}">
    </td>
    ${durationCell}
    <td>
      <button type="button" class="btn btn-danger btn-sm">
        Delete
      </button>
    </td>
  `;

  row.querySelector("button")?.addEventListener("click", () => {
    row.remove();
  });

  initDurationPickers(row);
  table.appendChild(row);
}

function initBulkModal() {
  const modal = document.getElementById("bulkUnitModal");
  if (!modal) return;

  const contentKind = modal.dataset.contentKind;

  modal.addEventListener("shown.bs.modal", function () {
    const tbody = document.querySelector("#units-table tbody");
    if (!tbody) return;

    tbody.innerHTML = "";

    for (let i = 0; i < 5; i++) {
      addRow("", "", contentKind);
    }
  });

  modal.querySelector(".js-add-row-btn")?.addEventListener("click", () => {
    addRow("", "", contentKind);
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

// Init All
document.addEventListener("DOMContentLoaded", function () {
  initBulkModal();
  togglePassword();
  initDurationPickers(document);
  initMarkComplete(document);

  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".js-submit-btn");
    if (btn) handleSubmit(btn);
  });

  document.addEventListener("change", function (e) {
    if (e.target.classList.contains("js-auto-submit")) {
      e.target.form.submit();
    }
  });
});
