const state = {
  shotJson: null,
  sceneData: null,
  projectedRegions: null,
  maskFilenames: null,
  prompts: null,
  workflow: null,
  depthUploaded: false,
  spatialMode: true,
  docPaths: {
    parse: null,
    scene: null,
    prompt: null,
    workflow: null,
  },
};

const statusEl = document.getElementById("status");
const textInputEl = document.getElementById("text-input");
const timeoutInputEl = document.getElementById("timeout-input");
const depthFileEl = document.getElementById("depth-file");
const depthPreviewWrapEl = document.getElementById("depth-preview-wrap");
const depthPreviewImgEl = document.getElementById("depth-preview-img");
const depthPreviewIframeEl = document.getElementById("depth-renderer-iframe");
const depthPreviewMetaEl = document.getElementById("depth-preview-meta");
const generatePreviewWrapEl = document.getElementById("generate-preview-wrap");
const generatePreviewImgEl = document.getElementById("generate-preview-img");
const generatePreviewMetaEl = document.getElementById("generate-preview-meta");
const spatialModeCheckbox = document.getElementById("spatial-mode");
const projectCanvasEl = document.getElementById("project-canvas");
const projectCanvasWrapEl = document.getElementById("project-canvas-wrap");

const resultEls = {
  parse: document.getElementById("result-parse"),
  scene: document.getElementById("result-scene"),
  project: document.getElementById("result-project"),
  prompt: document.getElementById("result-prompt"),
  workflow: document.getElementById("result-workflow"),
  depth: document.getElementById("result-depth"),
  generate: document.getElementById("result-generate"),
};

const docEditors = {
  parse: document.getElementById("doc-parse"),
  scene: document.getElementById("doc-scene"),
  prompt: document.getElementById("doc-prompt"),
  workflow: document.getElementById("doc-workflow"),
};

const docPathEls = {
  parse: document.getElementById("doc-path-parse"),
  scene: document.getElementById("doc-path-scene"),
  prompt: document.getElementById("doc-path-prompt"),
  workflow: document.getElementById("doc-path-workflow"),
};

const docSaveBtns = {
  parse: document.getElementById("save-doc-parse"),
  scene: document.getElementById("save-doc-scene"),
  prompt: document.getElementById("save-doc-prompt"),
  workflow: document.getElementById("save-doc-workflow"),
};

const btnParse = document.getElementById("btn-parse");
const btnScene = document.getElementById("btn-scene");
const btnProject = document.getElementById("btn-project");
const btnPrompt = document.getElementById("btn-prompt");
const btnWorkflow = document.getElementById("btn-workflow");
const btnUploadDepth = document.getElementById("btn-upload-depth");
const btnGenerateDepth = document.getElementById("btn-generate-depth");
const btnGenerate = document.getElementById("btn-generate");
const btnRunToWorkflow = document.getElementById("run-to-workflow");
const btnRunAll = document.getElementById("run-all");
const btnPrevStep = document.getElementById("btn-prev-step");
const btnNextStep = document.getElementById("btn-next-step");
const stepTabs = Array.from(document.querySelectorAll(".step-tab"));
const stepPanels = Array.from(document.querySelectorAll(".step-panel"));
const stepOrder = ["parse", "scene", "project", "prompt", "workflow", "depth", "generate"];
let currentStepIndex = 0;

// ======= spatial mode toggle =======

if (spatialModeCheckbox) {
  spatialModeCheckbox.addEventListener("change", () => {
    state.spatialMode = spatialModeCheckbox.checked;
    syncStepNavigation();
  });
}

function useSpatial() {
  return state.spatialMode && spatialModeCheckbox && spatialModeCheckbox.checked;
}

// ======= utilities =======

function isStepUnlocked(stepKey) {
  switch (stepKey) {
    case "parse":
      return true;
    case "scene":
      return Boolean(state.docPaths.parse);
    case "project":
      return useSpatial() && Boolean(state.docPaths.scene);
    case "prompt":
      return Boolean(state.docPaths.parse);
    case "workflow":
      return Boolean(state.docPaths.parse);
    case "depth":
      return Boolean(state.sceneData);
    case "generate":
      return Boolean(state.workflow) && state.depthUploaded;
    default:
      return false;
  }
}

function getNextUnlockedIndex(fromIndex) {
  for (let i = fromIndex + 1; i < stepOrder.length; i += 1) {
    if (isStepUnlocked(stepOrder[i])) return i;
  }
  return fromIndex;
}

function getPrevUnlockedIndex(fromIndex) {
  for (let i = fromIndex - 1; i >= 0; i -= 1) {
    if (isStepUnlocked(stepOrder[i])) return i;
  }
  return fromIndex;
}

function goToStep(index) {
  const clamped = Math.max(0, Math.min(stepOrder.length - 1, index));
  const targetKey = stepOrder[clamped];
  if (!isStepUnlocked(targetKey) && clamped !== 0) return;
  currentStepIndex = clamped;

  stepTabs.forEach((tab) => {
    const tabIndex = Number(tab.dataset.stepIndex || -1);
    tab.classList.toggle("active", tabIndex === currentStepIndex);
  });

  stepPanels.forEach((panel) => {
    const panelKey = panel.dataset.stepPanel;
    panel.classList.toggle("active", panelKey === targetKey);
  });

  syncStepNavigation();
}

function syncStepNavigation() {
  stepTabs.forEach((tab) => {
    const tabIndex = Number(tab.dataset.stepIndex || -1);
    const stepKey = stepOrder[tabIndex];
    const unlocked = isStepUnlocked(stepKey);
    tab.disabled = !unlocked;
    tab.classList.toggle("active", tabIndex === currentStepIndex);
  });

  const prevIndex = getPrevUnlockedIndex(currentStepIndex);
  const nextIndex = getNextUnlockedIndex(currentStepIndex);
  if (btnPrevStep) btnPrevStep.disabled = prevIndex === currentStepIndex;
  if (btnNextStep) btnNextStep.disabled = nextIndex === currentStepIndex;
}

function goPrevStep() {
  const prevIndex = getPrevUnlockedIndex(currentStepIndex);
  if (prevIndex !== currentStepIndex) goToStep(prevIndex);
}

function goNextStep() {
  const nextIndex = getNextUnlockedIndex(currentStepIndex);
  if (nextIndex !== currentStepIndex) goToStep(nextIndex);
}

function setStatus(message) {
  statusEl.textContent = message;
}

function pretty(data) {
  return JSON.stringify(data, null, 2);
}

function renderResult(key, data) {
  if (resultEls[key]) {
    resultEls[key].textContent = pretty(data);
  }
}

function getErrorPayload(error, fallbackMessage) {
  if (error && typeof error === "object") {
    if (error.detail) return { success: false, detail: error.detail };
    if (error.message) return { success: false, detail: error.message };
    return { success: false, detail: fallbackMessage, raw: error };
  }
  return { success: false, detail: String(error || fallbackMessage) };
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw data;
  return data;
}

async function loadDocument(path) {
  return postJson("/api/doc/load", { path });
}

async function saveDocument(path, data) {
  return postJson("/api/doc/save", { path, data });
}

function readEditorJson(stepKey) {
  const editor = docEditors[stepKey];
  if (!editor) return {};
  const raw = (editor.value || "").trim();
  if (!raw) return {};
  return JSON.parse(raw);
}

function writeEditorJson(stepKey, data) {
  const editor = docEditors[stepKey];
  if (!editor) return;
  editor.value = pretty(data ?? {});
}

function setDocPath(stepKey, path) {
  state.docPaths[stepKey] = path || null;
  const pathEl = docPathEls[stepKey];
  if (pathEl) pathEl.textContent = path ? `saved_to: ${path}` : "saved_to: -";
  const saveBtn = docSaveBtns[stepKey];
  if (saveBtn) saveBtn.disabled = !path;
}

function clearStepDoc(stepKey) {
  writeEditorJson(stepKey, {});
  setDocPath(stepKey, null);
}

async function getShotJsonFromParseDoc() {
  const parsePath = state.docPaths.parse;
  if (!parsePath) throw new Error("Step 1 document path is missing. Please run Step 1 first.");
  const loaded = await loadDocument(parsePath);
  const shotJson = loaded?.data;
  if (!shotJson || typeof shotJson !== "object") throw new Error("Step 1 document is invalid.");
  state.shotJson = shotJson;
  writeEditorJson("parse", shotJson);
  return shotJson;
}

async function saveCurrentDoc(stepKey) {
  const path = state.docPaths[stepKey];
  if (!path) {
    setStatus(`Step ${stepKey} has no saved document path yet`);
    return;
  }
  let data;
  try {
    data = readEditorJson(stepKey);
  } catch {
    setStatus(`Step ${stepKey} document JSON is invalid`);
    throw new Error("Invalid JSON");
  }
  await saveDocument(path, data);
  setStatus(`Step ${stepKey} document saved`);
}

// ======= Projection Canvas =======

const REGION_COLORS = [
  "#ef4444", "#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6",
  "#ec4899", "#06b6d4", "#f97316", "#84cc16", "#14b8a6",
];

function drawProjectionCanvas(regions, width = 1024, height = 1024) {
  if (!projectCanvasEl || !projectCanvasWrapEl) return;

  const canvas = projectCanvasEl;
  const ctx = canvas.getContext("2d");
  const scale = canvas.width / width;

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // 半透明黑色背景
  ctx.fillStyle = "rgba(0,0,0,0.85)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // 绘制中线
  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(canvas.width / 2, 0);
  ctx.lineTo(canvas.width / 2, canvas.height);
  ctx.moveTo(0, canvas.height / 2);
  ctx.lineTo(canvas.width, canvas.height / 2);
  ctx.stroke();

  regions.forEach((region, i) => {
    const color = REGION_COLORS[i % REGION_COLORS.length];
    const [x1, y1, x2, y2] = region.bbox;

    // 填充矩形
    ctx.fillStyle = color + "22";
    ctx.fillRect(x1 * scale, y1 * scale, (x2 - x1) * scale, (y2 - y1) * scale);

    // 边框
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(x1 * scale, y1 * scale, (x2 - x1) * scale, (y2 - y1) * scale);

    // 标签
    const label = `${region.object_id} (${region.object_type})`;
    ctx.fillStyle = color;
    ctx.font = "11px monospace";
    const labelY = y1 * scale - 4;
    ctx.fillText(label, x1 * scale + 2, labelY > 12 ? labelY : y1 * scale + 14);

    // 中心点
    const cx = region.center_2d[0] * scale;
    const cy = region.center_2d[1] * scale;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(cx, cy, 3, 0, Math.PI * 2);
    ctx.fill();
  });

  projectCanvasWrapEl.style.display = "block";
}

function clearProjectionCanvas() {
  if (!projectCanvasEl || !projectCanvasWrapEl) return;
  const ctx = projectCanvasEl.getContext("2d");
  ctx.clearRect(0, 0, projectCanvasEl.width, projectCanvasEl.height);
  projectCanvasWrapEl.style.display = "none";
}

// ======= 3D Preview (existing) =======

let rendererMessageListenerReady = false;

function ensureRendererMessageListener() {
  if (rendererMessageListenerReady) return;
  window.addEventListener("message", (event) => {
    if (event.origin !== window.location.origin) return;
    const payload = event.data;
    if (!payload || payload.type !== "rgb_snapshot" || !payload.dataUrl) return;
    if (!depthPreviewImgEl || !depthPreviewWrapEl) return;
    depthPreviewImgEl.src = payload.dataUrl;
    depthPreviewWrapEl.style.display = "block";
  });
  rendererMessageListenerReady = true;
}

function clearDepthPreview() {
  if (!depthPreviewWrapEl || !depthPreviewMetaEl) return;
  if (depthPreviewImgEl) depthPreviewImgEl.removeAttribute("src");
  depthPreviewMetaEl.textContent = "";
  depthPreviewWrapEl.style.display = "none";
}

function showDepthPreview(data) {
  if (!depthPreviewWrapEl || !depthPreviewIframeEl || !depthPreviewMetaEl || !depthPreviewImgEl) return;
  const sceneData = state.sceneData;
  if (!sceneData) { clearDepthPreview(); return; }
  ensureRendererMessageListener();
  const sendSceneData = () => {
    depthPreviewIframeEl.contentWindow?.postMessage(
      { type: "load_scene_data", scene_data: sceneData },
      window.location.origin,
    );
  };
  const requestSnapshotWithRetries = () => {
    let attempt = 0;
    const timer = setInterval(() => {
      attempt += 1;
      depthPreviewIframeEl.contentWindow?.postMessage(
        { type: "export_rgb_snapshot" },
        window.location.origin,
      );
      if (attempt >= 6 || (depthPreviewImgEl.getAttribute("src") || "").startsWith("data:image/")) {
        clearInterval(timer);
      }
    }, 180);
  };
  if (depthPreviewIframeEl.contentWindow) {
    sendSceneData();
    requestSnapshotWithRetries();
  }
  depthPreviewIframeEl.onload = () => {
    sendSceneData();
    requestSnapshotWithRetries();
  };
  depthPreviewMetaEl.textContent = [data?.method_used ? `method_used: ${data.method_used}` : ""].filter(Boolean).join("\n");
}

// ======= Generate Preview =======

function resolveGenerateImageUrl(data) {
  const outputPath = data?.output_path;
  if (outputPath && typeof outputPath === "string") {
    const normalized = outputPath.replaceAll("\\", "/").replace(/^\.\//, "");
    if (normalized.startsWith("data/")) return `/${normalized}?v=${Date.now()}`;
    const marker = "/data/";
    const index = normalized.indexOf(marker);
    if (index !== -1) {
      const relative = normalized.slice(index + 1);
      return `/${relative}?v=${Date.now()}`;
    }
  }
  const filename = data?.filename;
  if (filename) {
    const encoded = encodeURIComponent(filename);
    return `http://127.0.0.1:8188/view?filename=${encoded}&subfolder=&type=output`;
  }
  return "";
}

function clearGeneratePreview() {
  generatePreviewImgEl.removeAttribute("src");
  generatePreviewMetaEl.textContent = "";
  generatePreviewWrapEl.style.display = "none";
}

function showGeneratePreview(data) {
  const imageUrl = resolveGenerateImageUrl(data);
  if (!imageUrl) { clearGeneratePreview(); return; }
  generatePreviewImgEl.src = imageUrl;
  generatePreviewMetaEl.textContent = [
    data?.filename ? `filename: ${data.filename}` : "",
    data?.output_path ? `output_path: ${data.output_path}` : "",
  ].filter(Boolean).join("\n");
  generatePreviewWrapEl.style.display = "block";
}

// ======= Button states =======

function updateButtons() {
  const hasParseDoc = Boolean(state.docPaths.parse);
  const hasSceneData = Boolean(state.sceneData);
  const hasWorkflow = Boolean(state.workflow);
  const hasDepthFile = Boolean(depthFileEl && depthFileEl.files && depthFileEl.files.length > 0);

  if (btnScene) btnScene.disabled = !hasParseDoc;
  if (btnProject) btnProject.disabled = !hasSceneData;
  if (btnPrompt) btnPrompt.disabled = !hasParseDoc;
  if (btnWorkflow) btnWorkflow.disabled = !hasParseDoc;
  if (btnGenerateDepth) btnGenerateDepth.disabled = !hasSceneData;
  if (btnUploadDepth) btnUploadDepth.disabled = !hasWorkflow || !hasDepthFile;
  if (btnGenerate) btnGenerate.disabled = !hasWorkflow || !state.depthUploaded;
  syncStepNavigation();
}

function resetFromParseDownstream() {
  state.sceneData = null;
  state.projectedRegions = null;
  state.prompts = null;
  state.workflow = null;
  state.depthUploaded = false;
  setDocPath("scene", null);
  setDocPath("prompt", null);
  setDocPath("workflow", null);
  writeEditorJson("scene", {});
  writeEditorJson("prompt", {});
  writeEditorJson("workflow", {});
  renderResult("scene", {});
  renderResult("project", {});
  renderResult("prompt", {});
  renderResult("workflow", {});
  renderResult("depth", {});
  renderResult("generate", {});
  clearProjectionCanvas();
  clearGeneratePreview();
  clearDepthPreview();
}

function resetFromSceneDownstream() {
  state.projectedRegions = null;
  state.maskFilenames = null;
  state.prompts = null;
  state.workflow = null;
  state.depthUploaded = false;
  setDocPath("prompt", null);
  setDocPath("workflow", null);
  writeEditorJson("prompt", {});
  writeEditorJson("workflow", {});
  renderResult("project", {});
  renderResult("prompt", {});
  renderResult("workflow", {});
  renderResult("depth", {});
  renderResult("generate", {});
  clearProjectionCanvas();
  clearGeneratePreview();
}

function resetAll() {
  state.shotJson = null;
  setDocPath("parse", null);
  writeEditorJson("parse", {});
  resetFromParseDownstream();
  renderResult("parse", {});
  if (depthFileEl) depthFileEl.value = "";
  setStatus("State reset");
  goToStep(0);
  updateButtons();
}

// ======= Step 1: Parse =======

async function runParse() {
  setStatus("Running /api/parse...");
  try {
    const data = await postJson("/api/parse", {
      text: textInputEl.value,
      save_intermediate: true,
    });
    state.shotJson = data.shot_json || null;
    resetFromParseDownstream();
    renderResult("parse", data);
    writeEditorJson("parse", state.shotJson || {});
    setDocPath("parse", data.saved_to || null);
    setStatus("Step 1 done: parse success");
    goToStep(1);
  } catch (error) {
    state.shotJson = null;
    setDocPath("parse", null);
    writeEditorJson("parse", {});
    resetFromParseDownstream();
    const payload = getErrorPayload(error, "Parse failed");
    renderResult("parse", payload);
    setStatus("Step 1 failed");
    throw error;
  } finally {
    updateButtons();
  }
}

// ======= Step 2: Scene Build =======

async function runSceneBuild() {
  setStatus("Running /api/scene/build...");
  try {
    const shotJson = await getShotJsonFromParseDoc();
    const data = await postJson("/api/scene/build", {
      shot_json: shotJson,
      save_intermediate: true,
    });
    state.sceneData = data.scene_data || null;
    resetFromSceneDownstream();
    renderResult("scene", data);
    writeEditorJson("scene", state.sceneData || {});
    setDocPath("scene", data.saved_to || null);
    setStatus("Step 2 done: scene build success");
    goToStep(useSpatial() ? 2 : 3);
  } catch (error) {
    const payload = getErrorPayload(error, "Scene build failed");
    renderResult("scene", payload);
    setStatus("Step 2 failed");
    throw error;
  } finally {
    updateButtons();
  }
}

// ======= NEW Step 2.5: Project 3D→2D =======

async function runProject() {
  const scenePath = state.docPaths.scene;
  if (!scenePath) {
    setStatus("Please run Step 2 first to build and save scene data");
    return;
  }
  setStatus("Running /api/scene/project...");
  try {
    const sceneDoc = await loadDocument(scenePath);
    const sceneData = sceneDoc?.data;
    if (!sceneData || typeof sceneData !== "object") {
      throw new Error("Step 2 scene document is invalid or empty");
    }
    state.sceneData = sceneData;
    writeEditorJson("scene", sceneData);

    const shotJson = await getShotJsonFromParseDoc();
    const data = await postJson("/api/scene/project", {
      shot_json: shotJson,
      scene_data: sceneData,
      width: 1024,
      height: 1024,
    });
    state.projectedRegions = data.regions || [];
    state.maskFilenames = data.mask_filenames || {};
    renderResult("project", data);
    if (state.projectedRegions.length > 0) {
      drawProjectionCanvas(state.projectedRegions);
      setStatus(`Step 2.5 done: ${state.projectedRegions.length} objects projected`);
      goToStep(3);
    } else {
      clearProjectionCanvas();
      setStatus("Step 2.5 done: no objects to project");
      goToStep(3);
    }
  } catch (error) {
    state.projectedRegions = null;
    clearProjectionCanvas();
    const payload = getErrorPayload(error, "Projection failed");
    renderResult("project", payload);
    setStatus("Step 2.5 failed");
    throw error;
  } finally {
    updateButtons();
  }
}

// ======= Step 3: Regional Prompts =======

async function runPromptBuild() {
  setStatus("Running /api/prompt/regional...");
  try {
    const shotJson = await getShotJsonFromParseDoc();
    // Use regional endpoint when spatial mode is on
    const url = useSpatial() ? "/api/prompt/regional" : "/api/prompt/build";
    const data = await postJson(url, {
      shot_json: shotJson,
      save_intermediate: true,
    });
    state.prompts = data.regional_prompts || data.prompts || null;
    renderResult("prompt", data);
    writeEditorJson("prompt", state.prompts || {});
    setDocPath("prompt", data.saved_to || null);
    const mode = useSpatial() ? "regional" : "global";
    setStatus(`Step 3 done: prompt build success (${mode})`);
    goToStep(4);
  } catch (error) {
    const payload = getErrorPayload(error, "Prompt build failed");
    renderResult("prompt", payload);
    setStatus("Step 3 failed");
    throw error;
  } finally {
    updateButtons();
  }
}

// ======= Step 4: Workflow Build =======

async function runWorkflowBuild() {
  setStatus("Running /api/workflow/build...");
  try {
    const shotJson = await getShotJsonFromParseDoc();
    const data = await postJson("/api/workflow/build", {
      shot_json: shotJson,
      save_intermediate: true,
      use_regional: state.spatialMode,
      mask_filenames: state.maskFilenames || null,
    });
    state.workflow = data.workflow || null;
    state.depthUploaded = false;
    renderResult("workflow", data);
    writeEditorJson("workflow", state.workflow || {});
    setDocPath("workflow", data.saved_to || null);
    clearGeneratePreview();
    setStatus("Step 4 done: workflow build success");
    goToStep(5);
  } catch (error) {
    state.workflow = null;
    state.depthUploaded = false;
    const payload = getErrorPayload(error, "Workflow build failed");
    renderResult("workflow", payload);
    setStatus("Step 4 failed");
    throw error;
  } finally {
    updateButtons();
  }
}

// ======= Step 5: Depth =======

async function runDepthRender() {
  if (!state.sceneData) {
    setStatus("Please run Step 2 first to build scene data");
    return;
  }
  setStatus("Running /api/depth/render...");
  try {
    const data = await postJson("/api/depth/render", {
      scene_data: state.sceneData,
      method: "playwright",
      upload_to_comfy: true,
    });
    state.depthUploaded = Boolean(data.success);
    renderResult("depth", data);
    showDepthPreview(data);
    setStatus("Step 5 done: depth render success");
    goToStep(6);
  } catch (error) {
    state.depthUploaded = false;
    const payload = getErrorPayload(error, "Depth render failed");
    renderResult("depth", payload);
    clearDepthPreview();
    setStatus("Step 5 failed");
    throw error;
  } finally {
    updateButtons();
  }
}

async function runDepthUpload() {
  if (!btnUploadDepth || !state.workflow) return;
  const file = depthFileEl && depthFileEl.files && depthFileEl.files[0];
  if (!file) {
    setStatus("Please choose a depth image first");
    return;
  }
  setStatus("Uploading depth image...");
  const formData = new FormData();
  formData.append("file", file);
  try {
    const response = await fetch("/api/depth/upload", {
      method: "POST",
      body: formData,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw data;
    state.depthUploaded = Boolean(data.success);
    renderResult("depth", data);
    showDepthPreview({ saved_path: "/data/depth/depth_map.png", method_used: "uploaded" });
    setStatus("Step 5 done: depth upload success");
    goToStep(6);
  } catch (error) {
    state.depthUploaded = false;
    const payload = getErrorPayload(error, "Depth upload failed");
    renderResult("depth", payload);
    setStatus("Step 5 failed");
    throw error;
  } finally {
    updateButtons();
  }
}

// ======= Step 6: Generate =======

async function runGenerate() {
  if (!state.workflow || !state.depthUploaded) return;
  const timeout = Number(timeoutInputEl.value) || 300;
  setStatus("Running /api/generate...");
  try {
    const data = await postJson("/api/generate", { workflow: state.workflow, timeout });
    renderResult("generate", data);
    showGeneratePreview(data);
    setStatus("Step 6 done: generate success");
  } catch (error) {
    const payload = getErrorPayload(error, "Generate failed");
    renderResult("generate", payload);
    clearGeneratePreview();
    setStatus("Step 6 failed");
    throw error;
  }
}

// ======= Batch runners =======

async function runToWorkflow() {
  btnRunToWorkflow.disabled = true;
  try {
    await runParse();
    await runSceneBuild();
    if (useSpatial()) await runProject();
    await runPromptBuild();
    await runWorkflowBuild();
    const steps = useSpatial() ? "1-5" : "1-4";
    setStatus(`Steps ${steps} completed`);
  } catch {
    setStatus("Run halted due to failure");
  } finally {
    btnRunToWorkflow.disabled = false;
    updateButtons();
  }
}

async function runAll() {
  btnRunAll.disabled = true;
  try {
    await runParse();
    await runSceneBuild();
    if (useSpatial()) await runProject();
    await runPromptBuild();
    await runWorkflowBuild();
    await runDepthRender();
    await runGenerate();
    setStatus("All steps completed");
  } catch {
    setStatus("Run halted due to failure");
  } finally {
    btnRunAll.disabled = false;
    updateButtons();
  }
}


stepTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const index = Number(tab.dataset.stepIndex || 0);
    goToStep(index);
  });
});

if (btnPrevStep) btnPrevStep.addEventListener("click", goPrevStep);
if (btnNextStep) btnNextStep.addEventListener("click", goNextStep);


if (btnParse) btnParse.addEventListener("click", () => runParse().catch(() => {}));
if (btnScene) btnScene.addEventListener("click", () => runSceneBuild().catch(() => {}));
if (btnProject) btnProject.addEventListener("click", () => runProject().catch(() => {}));
if (btnPrompt) btnPrompt.addEventListener("click", () => runPromptBuild().catch(() => {}));
if (btnWorkflow) btnWorkflow.addEventListener("click", () => runWorkflowBuild().catch(() => {}));
if (btnGenerateDepth) btnGenerateDepth.addEventListener("click", () => runDepthRender().catch(() => {}));
if (btnUploadDepth) btnUploadDepth.addEventListener("click", () => runDepthUpload().catch(() => {}));
if (btnGenerate) btnGenerate.addEventListener("click", () => runGenerate().catch(() => {}));
if (btnRunToWorkflow) btnRunToWorkflow.addEventListener("click", () => runToWorkflow().catch(() => {}));
if (btnRunAll) btnRunAll.addEventListener("click", () => runAll().catch(() => {}));

docSaveBtns.parse?.addEventListener("click", () => saveCurrentDoc("parse").catch(() => {}));
docSaveBtns.scene?.addEventListener("click", () => saveCurrentDoc("scene").catch(() => {}));
docSaveBtns.prompt?.addEventListener("click", () => saveCurrentDoc("prompt").catch(() => {}));
docSaveBtns.workflow?.addEventListener("click", () => saveCurrentDoc("workflow").catch(() => {}));

document.getElementById("open-depth-renderer")?.addEventListener("click", () => {
  window.open("/web/threejs_depth_renderer/index.html", "_blank");
});

document.getElementById("reset-state")?.addEventListener("click", () => {
  resetAll();
});

if (depthFileEl) {
  depthFileEl.addEventListener("change", () => {
    state.depthUploaded = false;
    updateButtons();
  });
}

resetAll();
