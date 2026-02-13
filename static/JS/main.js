let cameraRunning = false;
let autoCaptureInterval = null;

function toggleCamera() {
  cameraRunning ? stopCamera() : startCamera();
}

function startCamera() {
  fetch("/start_camera", { method: "POST" })
    .then(res => res.json())
    .then(data => {
      if (data.status === "started") {
        cameraRunning = true;
        document.getElementById("cameraFeed").src = "/video_feed?" + Date.now();
        document.getElementById("cameraSection").style.display = "block";
        document.getElementById("captureBtn").style.display = "inline-block";
        autoCaptureInterval = setInterval(() => {
          if (cameraRunning) captureImage();
        }, 6000);
      } else {
        console.error("Failed to start camera:", data.message);
      }
    })
    .catch(err => console.error("Start camera error:", err));
}

function stopCamera() {
  fetch("/stop_camera", { method: "POST" })
    .then(res => res.json())
    .then(data => {
      cameraRunning = false;
      clearInterval(autoCaptureInterval);
      document.getElementById("cameraFeed").src = "";
    })
    .catch(err => console.error("Stop camera error:", err));
}
window.captureImage = async function () {
  try {
    const response = await fetch("/capture_frame", { method: "POST" });
    if (!response.ok) throw new Error("HTTP error " + response.status);

    const data = await response.json();
    console.log("Captured image:", data);
    const capturedImage = document.getElementById("capturedImage");
    if (data.img && capturedImage) {
      capturedImage.src = data.img + "?t=" + Date.now();
    }

    showResults(data);

  } catch (err) {
    console.error("CAPTURE ERROR", err);
    showError(err.message);
  }
}

function showResults(data) {
  document.getElementById("resultsSection").style.display = "block";
  updateResultLabel(data.result || "Unknown");

  document.getElementById("resultDetails").innerHTML = `
    <strong>Part Number:</strong> ${data.part_number || "-"}<br>
    <strong>SSIM Score:</strong> ${data.ssim || "-"}<br>
    <strong>Defect Type:</strong> ${data.defect_type || "-"}<br>
    <strong>Best Match:</strong> ${data.best_match || "-"}
  `;

  saveInspectionToDB(data);
}
function updateResultLabel(result) {
  const label = document.getElementById("resultLabel");
  label.style.fontSize = "24px";

  if (result === "Accepted") {
    label.textContent = "Result: Accepted";
    label.style.color = "green";
  } else if (result === "Rejected") {
    label.textContent = "Result: Rejected";
    label.style.color = "red";
  } else {
    label.textContent = "Result: " + result;
    label.style.color = "black";
  }
}
function saveInspectionToDB(data) {
  const location = document.getElementById("locationFilter")?.value || "Unknown";
  const shift = document.getElementById("shiftFilter")?.value || "Unknown";

  let image_name = data.image_name || "";
  if (!image_name && data.img) {
    image_name = data.img.split("/").pop();
  }

  const payload = {
    part_number: data.part_number || null,
    part_name: data.part_name || null,
    image_name: image_name,
    ssim_score: parseFloat(data.ssim) || null,
    result: data.result || null,
    best_match: data.best_match || null,
    defect_type: data.defect_type || null,
    location: location,
    shifts: shift
  };

  fetch("/save_inspection", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
    .then(res => res.json())
    .then(resp => console.log("Inspection saved:", resp))
    .catch(err => console.error("Save inspection error:", err));
}

document.getElementById("imageInput")?.addEventListener("change", function () {
  const file = this.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("image", file);

  const loading = document.getElementById("loadingIndicator");
  if (loading) loading.style.display = "block";

  fetch("/upload", { method: "POST", body: formData })
    .then(res => {
      if (loading) loading.style.display = "none";
      if (!res.ok) throw new Error("Upload failed");
      return res.json();
    })
    .then(data => showResults(data))
    .catch(err => showError(err.message));
});

function showError(message) {
  const alertBox = document.getElementById("errorAlert");
  document.getElementById("errorMessage").innerText = message;
  alertBox.style.display = "block";
}
function fetchDailyNotification() {
  fetch("/api/daily-notification")
    .then(res => res.json())
    .then(data => {
      if (data.message) alert(data.message);
    })
    .catch(err => console.error("Notification error:", err));
}

fetchDailyNotification();
setInterval(fetchDailyNotification, 60000);

document.addEventListener("keydown", function (event) {
  switch (event.key.toLowerCase()) {
    case " ":
      document.getElementById("cameraBtn")?.click();
      event.preventDefault();
      break;
    case "c":
      document.getElementById("captureBtn")?.click();
      break;
    case "t":
      document.getElementById("imageInput")?.click();
      break;
  }
});

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    new bootstrap.Tooltip(el);
  });
});

document.addEventListener("DOMContentLoaded", function () {
  const btn = document.getElementById("loadInspectionDetailsBtn");
  const section = document.getElementById("inspectionDetailsSection");

  if (!btn || !section) return;

  btn.addEventListener("click", async function (e) {
    e.preventDefault();
    section.style.display = "block";
    section.innerHTML = "<p class='text-center text-muted'>Loading...</p>";

    try {
      const res = await fetch(btn.getAttribute("href"));
      if (!res.ok) throw new Error("Failed to load");
      section.innerHTML = await res.text();
    } catch (err) {
      section.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
    }
  });
});
