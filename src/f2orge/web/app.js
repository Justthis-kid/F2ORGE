(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const editor = $("#editor");
  const output = $("#output");
  const consoleLog = $("#console-log");
  const graphCanvas = $("#graph-canvas");
  const nodeLayer = $("#nodes");
  const wireLayer = $("#wires");
  const nodes = [];
  const links = {};
  let nextId = 1;
  let selectedId = null;
  let wireSource = null;
  let currentFile = { name: "Untitled.forge", dirty: false };
  let commandHistory = [];
  let historyIndex = 0;
  let busy = false;
  let generatedTarget = "python";
  let generatedBinary = "";
  let chartResult = null;

  const nodeInputs = {
    Input: 0, Constant: 0, Script: 0, Function: 1, Call: 2, Add: 2, Subtract: 2,
    Multiply: 2, Divide: 2, Power: 2, Compare: 2, Output: 1, Output2: 1,
  };
  const symbols = { Add: "+", Subtract: "-", Multiply: "*", Divide: "/", Power: "^", Compare: "<=" };
  // A Compare node's value is an operator, or a magnitude comparison that ignores units.
  const comparisons = { "<": "<", "<=": "<=", ">": ">", ">=": ">=", "==": "==", "!=": "!=",
    lt: "<", le: "<=", gt: ">", ge: ">=", eq: "==", ne: "!=",
    "mag<": "mag<", "mag<=": "mag<=", "mag>": "mag>", "mag>=": "mag>=" };
  const magnitudeCalls = { "mag<": "less_mag", "mag<=": "less_equal_mag",
    "mag>": "greater_mag", "mag>=": "greater_equal_mag" };
  const supportedFunctions = [
    "sin", "cos", "tan", "asin", "acos", "atan", "exp", "ln", "log", "sqrt", "abs",
    "cross", "sum", "mean", "median", "std", "var", "percentile", "linreg", "det",
    "transpose", "inverse", "real", "imag", "conj", "arg", "mag", "cbrt", "sign",
    "fft", "ifft", "lowpass", "highpass", "db", "undb", "pH", "fromPH", "normalize",
    "cumsum", "diff", "trapz", "ceil", "floor",
  ];
  const reservedNames = new Set(["eq", "import", "export", "solve", "convert", "print", "for"]);

  function setStatus(message) {
    $("#graph-message").textContent = message;
  }

  async function convertScript() {
    if (busy) return;
    const target = $("#export-target").value;
    const targetLabel = {
      python: "Python",
      micropython: "MicroPython",
      cpp: "C++",
      "ti-basic": "TI-84 BASIC",
    }[target];
    $("#export-script").disabled = true;
    try {
      const result = await request("/api/transpile", { source: editor.value, target });
      generatedTarget = target;
      generatedBinary = result.binary || "";
      $("#transpile-title").textContent = `Generated ${targetLabel}`;
      $("#transpile-output").value = result.output;
      $("#transpile-dialog").showModal();
    } catch (error) {
      pushConsole(error.message, "error");
      $("#server-status").textContent = "Code conversion failed";
    } finally {
      $("#export-script").disabled = false;
    }
  }

  async function showPlot(command, label) {
    try {
      const result = await request("/api/plot", { command });
      pushConsole(label, "command");
      openPlot(result.title, result.svg);
    } catch (error) {
      pushConsole(error.message, "error");
    }
  }

  function openPlot(title, svgMarkup) {
    try {
      $("#plot-title").textContent = title;
      const content = $("#plot-content");
      content.innerHTML = svgMarkup;
      const svg = content.querySelector("svg");
      const originalViewBox = svg.getAttribute("viewBox");
      let drag = null;
      svg.addEventListener("wheel", (event) => {
        event.preventDefault();
        const box = svg.viewBox.baseVal;
        const rect = svg.getBoundingClientRect();
        const px = box.x + (event.clientX - rect.left) * box.width / rect.width;
        const py = box.y + (event.clientY - rect.top) * box.height / rect.height;
        const scale = event.deltaY < 0 ? 0.8 : 1.25;
        svg.setAttribute("viewBox",
          `${px - (px - box.x) * scale} ${py - (py - box.y) * scale} ${box.width * scale} ${box.height * scale}`);
      }, { passive: false });
      svg.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        const box = svg.viewBox.baseVal;
        drag = { x: event.clientX, y: event.clientY, left: box.x, top: box.y, width: box.width, height: box.height };
        svg.classList.add("dragging");
        svg.setPointerCapture(event.pointerId);
      });
      svg.addEventListener("pointermove", (event) => {
        if (!drag) return;
        const rect = svg.getBoundingClientRect();
        const dx = (event.clientX - drag.x) * drag.width / rect.width;
        const dy = (event.clientY - drag.y) * drag.height / rect.height;
        svg.setAttribute("viewBox", `${drag.left - dx} ${drag.top - dy} ${drag.width} ${drag.height}`);
      });
      const stopDrag = () => { drag = null; svg.classList.remove("dragging"); };
      svg.addEventListener("pointerup", stopDrag);
      svg.addEventListener("pointercancel", stopDrag);
      $("#reset-plot").onclick = () => svg.setAttribute("viewBox", originalViewBox);
      $("#plot-dialog").showModal();
    } catch (error) {
      pushConsole(error.message, "error");
    }
  }

  function parseCsv(text) {
      const records = [];
      let row = [], cell = "", quoted = false;
      for (let i = 0; i < text.length; i += 1) {
        const char = text[i];
        if (quoted && char === '"' && text[i + 1] === '"') { cell += '"'; i += 1; }
        else if (char === '"') quoted = !quoted;
        else if (char === "," && !quoted) { row.push(cell.trim()); cell = ""; }
        else if ((char === "\n" || char === "\r") && !quoted) {
          if (char === "\r" && text[i + 1] === "\n") i += 1;
          row.push(cell.trim()); cell = "";
          if (row.some((value) => value !== "")) records.push(row);
          row = [];
        } else cell += char;
      }
      if (quoted) throw new Error("CSV contains an unclosed quoted field.");
      row.push(cell.trim());
      if (row.some((value) => value !== "")) records.push(row);
      if (records.length < 2) throw new Error("Add a header row and at least one data row.");
      const width = records[0].length;
      if (!width || records.some((item) => item.length !== width)) {
        throw new Error("Every CSV row must have the same number of columns.");
      }
      const columns = records[0].map((header) => {
        const match = header.match(/^(.+?)\s*\[([^\]]+)\]\s*$/);
        return { name: (match ? match[1] : header).trim(), unit: match ? match[2].trim() : "" };
      });
      return { columns, rows: records.slice(1) };
    }

  function refreshChartSelectors() {
      const data = parseCsv($("#chart-csv").value);
      const previous = {
        x: $("#chart-x").value, y: $("#chart-y3").value, z: $("#chart-z3").value,
      };
      const options = data.columns.map((column, index) =>
        `<option value="${index}">${escapeHtml(column.name)}${column.unit ? ` (${escapeHtml(column.unit)})` : ""}</option>`
      ).join("");
      for (const id of ["#chart-x", "#chart-y3", "#chart-z3"]) $(id).innerHTML = options;
      $("#chart-x").value = previous.x !== "" && Number(previous.x) < data.columns.length ? previous.x : "0";
      $("#chart-y3").value = previous.y !== "" && Number(previous.y) < data.columns.length
        ? previous.y : String(Math.min(1, data.columns.length - 1));
      $("#chart-z3").value = previous.z !== "" && Number(previous.z) < data.columns.length
        ? previous.z : String(Math.min(2, data.columns.length - 1));
      const xIndex = Number($("#chart-x").value || 0);
      let defaultSeriesCount = 0;
      $("#chart-series").replaceChildren(...data.columns.map((column, index) => {
        const label = document.createElement("label");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = column.name;
        checkbox.checked = index !== xIndex && defaultSeriesCount < 10;
        if (checkbox.checked) defaultSeriesCount += 1;
        checkbox.disabled = index === xIndex;
        label.append(checkbox, document.createTextNode(
          `${column.name}${column.unit ? ` (${column.unit})` : ""}`,
        ));
        return label;
      }));
      $("#chart-series-field").hidden = $("#chart-type").value.endsWith("3d");
      $("#chart-3d-fields").hidden = !$("#chart-type").value.endsWith("3d");
      $("#chart-error").textContent = "";
    }

  function serializeCsv(records) {
      return records.map((row) => row.map((value) => {
        const text = String(value ?? "");
        return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
      }).join(",")).join("\n");
    }

    function invalidateChart() {
      chartResult = null;
      $("#chart-error").textContent = "";
      for (const id of ["#download-chart-svg", "#download-chart-png", "#download-chart-html", "#print-chart"]) {
        $(id).disabled = true;
      }
      $("#chart-preview").innerHTML = "<p>Render the updated table and options to preview a chart.</p>";
    }

  function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
      })[char]);
    }

  async function renderChart() {
      $("#chart-error").textContent = "";
      try {
        const parsed = parseCsv($("#chart-csv").value);
        const type = $("#chart-type").value;
        const columnIndex = (id) => {
          const index = Number($(id).value);
          if (!Number.isInteger(index) || !parsed.columns[index]) throw new Error("Select a valid table column.");
          return parsed.columns[index].name;
        };
        const requestData = {
          table: parsed,
          type,
          x: columnIndex("#chart-x"),
          y: [...$("#chart-series").querySelectorAll("input:checked")].map((input) => input.value),
        };
        if (type.endsWith("3d")) requestData.axes = [requestData.x, columnIndex("#chart-y3"), columnIndex("#chart-z3")];
        const result = await request("/api/chart", requestData);
        chartResult = { ...result, type };
        $("#download-chart-svg").disabled = !result.svg;
        $("#download-chart-png").disabled = !result.svg;
        $("#download-chart-html").disabled = false;
        $("#print-chart").disabled = false;
        const preview = $("#chart-preview");
        preview.replaceChildren();
        if (type.endsWith("3d")) {
          const frame = document.createElement("iframe");
          frame.title = "Interactive three-dimensional chart";
          frame.setAttribute("sandbox", "allow-scripts");
          frame.src = result.previewUrl;
          preview.append(frame);
        } else {
          preview.innerHTML = result.svg;
          chartResult.svg = result.svg;
        }
      } catch (error) {
        chartResult = null;
        $("#download-chart-svg").disabled = true;
        $("#download-chart-png").disabled = true;
        $("#download-chart-html").disabled = true;
        $("#print-chart").disabled = true;
        $("#chart-preview").innerHTML = "<p>Chart could not be rendered.</p>";
        $("#chart-error").textContent = error.message;
      }
    }

  function downloadChart(filename, content, mimeType) {
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([content], { type: mimeType }));
      link.download = filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    }

  function chartHtml() {
      if (!chartResult) throw new Error("Render a chart before exporting.");
      return chartResult.output;
    }

  async function downloadChartPng() {
      if (!chartResult || !chartResult.svg) throw new Error("PNG export is available for 2D charts.");
      const image = new Image();
      const source = URL.createObjectURL(new Blob([chartResult.svg], { type: "image/svg+xml" }));
      image.onload = () => {
        try {
          const canvas = document.createElement("canvas");
          canvas.width = 1800;
          canvas.height = 1120;
          const context = canvas.getContext("2d");
          if (!context) throw new Error("Canvas is unavailable for PNG export.");
          context.fillStyle = "#ffffff";
          context.fillRect(0, 0, canvas.width, canvas.height);
          context.drawImage(image, 0, 0, canvas.width, canvas.height);
          canvas.toBlob((blob) => {
            if (blob) downloadChart("f2orge-chart.png", blob, "image/png");
            else $("#chart-error").textContent = "Could not encode chart as PNG.";
            URL.revokeObjectURL(source);
          }, "image/png");
        } catch (error) {
          URL.revokeObjectURL(source);
          $("#chart-error").textContent = error.message;
        }
      };
      image.onerror = () => { URL.revokeObjectURL(source); $("#chart-error").textContent = "Could not render chart as PNG."; };
      image.src = source;
    }
  function pushConsole(text, kind = "") {
    const welcome = consoleLog.querySelector(".console-welcome");
    if (welcome) welcome.remove();
    const line = document.createElement("div");
    line.className = `console-line ${kind}`;
    line.textContent = text;
    consoleLog.append(line);
    consoleLog.scrollTop = consoleLog.scrollHeight;
  }

  function appendOutput(text, success = true) {
    output.textContent = text || (success ? "Program completed without printed output." : "Execution failed.");
    output.classList.toggle("error", !success);
  }

  function setBusy(value) {
    busy = value;
    for (const button of [$("#run-script"), $("#trace-script"), $("#profile-script"),
                          $("#run-graph"), $("#export-script"), $(".command-submit")]) {
      button.disabled = value;
    }
    $("#run-script").innerHTML = value ? "Running…" : '<span class="play-icon">▶</span> Run <kbd>Ctrl ↵</kbd>';
  }

  async function debugScript(path, label) {
    // The IDE's Trace and Profile buttons: the same reports `forge trace` and `forge profile` give.
    if (busy) return;
    setBusy(true);
    pushConsole(label, "command");
    try {
      const result = await request(path, { source: editor.value });
      appendOutput(result.output, result.success);
    } catch (error) {
      appendOutput(error.message, false);
    } finally {
      setBusy(false);
    }
  }

  async function request(path, body) {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.output || `Request failed (${response.status})`);
    return data;
  }

  function renderWorkspace(data) {
    const list = $("#workspace-list");
    list.replaceChildren();
    renderWorksheets(data.worksheets || []);
    for (const [label, items, valueFor] of [
      ["VARIABLES", data.variables || [], (item) => item.value],
      ["EQUATIONS", data.equations || [], (item) => item.signature],
      ["OBJECTS", data.objects || [], (item) =>
        (item.properties || []).map((p) => `${p.name}${p.required ? "" : " = " + p.default}`).join(" · ")],
    ]) {
      if (!items.length) continue;
      const group = document.createElement("section");
      group.className = "workspace-group";
      const heading = document.createElement("div");
      heading.className = "workspace-group-title";
      heading.textContent = label;
      group.append(heading);
      for (const item of items) {
        const row = document.createElement("div");
        row.className = "workspace-item";
        const mark = document.createElement("span");
        mark.className = "value-mark";
        mark.textContent = label === "VARIABLES" ? "x" : label === "OBJECTS" ? "◆" : "ƒ";
        const detail = document.createElement("div");
        const name = document.createElement("strong");
        name.textContent = item.name;
        const value = document.createElement("small");
        value.textContent = valueFor(item);
        detail.append(name, value);
        row.append(mark, detail);
        group.append(row);
      }
      list.append(group);
    }
    if (!list.childElementCount) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "Run a program to see its variables here.";
      list.append(empty);
    }
  }

  function renderWorksheets(worksheets) {
    const list = $("#worksheet-list");
    list.replaceChildren();
    if (!worksheets.length) {
      const empty = document.createElement("p");
      empty.className = "worksheet-empty";
      empty.innerHTML = 'Add a <code>worksheet</code> definition to your Forge script and press Run.';
      list.append(empty);
      return;
    }

    for (const worksheet of worksheets) {
      const card = document.createElement("article");
      card.className = "worksheet-card";
      card.dataset.worksheet = worksheet.name;
      const title = document.createElement("h2");
      title.textContent = worksheet.name;
      card.append(title);
      if (worksheet.description) {
        const description = document.createElement("p");
        description.className = "worksheet-description";
        description.textContent = worksheet.description;
        card.append(description);
      }

      const inputs = document.createElement("div");
      inputs.className = "worksheet-inputs";
      for (const item of worksheet.inputs) {
        const field = document.createElement("label");
        field.className = "worksheet-field";
        const caption = document.createElement("span");
        caption.textContent = item.name;
        const value = document.createElement("div");
        value.className = "worksheet-value";
        const input = document.createElement("input");
        input.type = "number";
        input.step = "any";
        input.value = item.default;
        input.dataset.input = item.name;
        input.setAttribute("aria-label", `${item.name} (${item.unit || "dimensionless"})`);
        const unit = document.createElement("span");
        unit.textContent = item.unit;
        value.append(input, unit);
        field.append(caption, value);
        if (item.description) {
          const note = document.createElement("small");
          note.textContent = item.description;
          field.append(note);
        }
        inputs.append(field);
      }
      card.append(inputs);

      const results = document.createElement("div");
      results.className = "worksheet-results";
      card.append(results);
      const graphs = document.createElement("div");
      graphs.className = "worksheet-graphs";
      card.append(graphs);
      const error = document.createElement("div");
      error.className = "worksheet-error";
      error.setAttribute("role", "status");
      card.append(error);
      inputs.addEventListener("input", () => {
        clearTimeout(card.worksheetTimer);
        card.worksheetTimer = setTimeout(() => updateWorksheet(card), 180);
      });
      list.append(card);
      updateWorksheet(card);
    }
  }

  async function updateWorksheet(card) {
    card.worksheetRequestId = (card.worksheetRequestId || 0) + 1;
    const requestId = card.worksheetRequestId;
    const inputs = {};
    card.querySelectorAll("[data-input]").forEach((input) => {
      inputs[input.dataset.input] = input.value;
    });
    const error = card.querySelector(".worksheet-error");
    error.textContent = "";
    try {
      const result = await request("/api/worksheet", {
        name: card.dataset.worksheet,
        inputs,
      });
      if (requestId !== card.worksheetRequestId) return;
      const outputs = card.querySelector(".worksheet-results");
      outputs.replaceChildren();
      for (const item of result.outputs) {
        const value = document.createElement("div");
        value.className = "worksheet-result";
        const name = document.createElement("small");
        name.textContent = item.name;
        const amount = document.createElement("strong");
        amount.textContent = item.value;
        value.append(name, amount);
        outputs.append(value);
      }
      const graphs = card.querySelector(".worksheet-graphs");
      graphs.replaceChildren();
      for (const graph of result.graphs) {
        const figure = document.createElement("div");
        figure.className = "worksheet-graph";
        figure.innerHTML = graph.svg;
        graphs.append(figure);
      }
    } catch (requestError) {
      if (requestId !== card.worksheetRequestId) return;
      error.textContent = requestError.message;
    }
  }

  async function runSource(source, label) {
    if (busy) return null;
    setBusy(true);
    try {
      const result = await request("/api/execute", { source });
      appendOutput(result.output, result.success);
      renderWorkspace(result);
      if (label) pushConsole(label, "command");
      if (result.output) pushConsole(result.output, result.success ? "" : "error");
      $("#server-status").textContent = result.success ? "Local kernel ready" : "Execution error";
      if (result.success && Array.isArray(result.plots) && result.plots.length) {
        const plot = result.plots[result.plots.length - 1];
        const svg = await request("/api/plot-svg", { points: plot.points, title: plot.title,
          xLabel: plot.xLabel, yLabel: plot.yLabel });
        openPlot(plot.title, svg.svg);
        pushConsole(`Opened plot: ${plot.title}`);
      }
      return result;
    } catch (error) {
      appendOutput(error.message, false);
      pushConsole(error.message, "error");
      $("#server-status").textContent = "Local kernel unavailable";
      return null;
    } finally {
      setBusy(false);
    }
  }

  function updateDirty() {
    $("#dirty-mark").textContent = currentFile?.dirty ? " •" : "";
    $("#project-name").textContent = currentFile?.name || "Untitled.forge";
  }

  function saveScript() {
    const name = currentFile?.name || "Untitled.forge";
    download(name, editor.value, "text/plain;charset=utf-8");
    if (currentFile) currentFile.dirty = false;
    else currentFile = { name, dirty: false };
    updateDirty();
  }

  function download(name, contents, type) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([contents], { type }));
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  function downloadBinary(name, base64) {
    const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
    download(name, bytes, "application/octet-stream");
  }

  function setPanel(panelId) {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.panel === panelId));
    document.querySelectorAll(".panel").forEach((panel) => panel.classList.toggle("active", panel.id === panelId));
  }

  function showGraphDialog({ title, copy, confirm = "Continue", cancel = "Cancel", value = "", multiline = false }) {
    const dialog = $("#graph-dialog");
    const textarea = $("#graph-dialog-value");
    $("#graph-dialog-title").textContent = title;
    $("#graph-dialog-copy").textContent = copy;
    $("#graph-dialog-confirm").textContent = confirm;
    $("#graph-dialog-cancel").textContent = cancel;
    textarea.hidden = !multiline;
    textarea.value = value;
    dialog.showModal();
    if (multiline) textarea.focus();
    return new Promise((resolve) => {
      dialog.addEventListener("close", () => {
        resolve({
          confirmed: dialog.returnValue === "confirm",
          value: textarea.value,
        });
      }, { once: true });
    });
  }

  function hasSharedName(kind, value) {
    return nodes.some((node) =>
      node.value === value &&
      ((kind === "Input" && node.kind === "Output") ||
       (kind === "Output" && node.kind === "Input")),
    );
  }

  async function addNode(kind, value, x, y) {
    if (value === undefined) {
      const defaults = {
        Input: ["Variable name", "mass"],
        Constant: ["F²ORGE expression", "9.81 m/s^2"],
        Function: [`Function (${supportedFunctions.join(", ")})`, "sqrt"],
        Call: ["Function or equation to call (area, Force, solveODE)", "area"],
        Compare: ["Comparison (<, <=, >, >=, ==, !=)", "<="],
        Output: ["Output variable name", "result"],
        Output2: ["Names to unpack, separated by commas", "time, velocity"],
      };
      if (defaults[kind]) {
        value = window.prompt(defaults[kind][0], defaults[kind][1]);
        if (value === null || !value.trim()) return;
      } else if (kind === "Script") {
        const result = await showGraphDialog({
          title: "Add F²ORGE script",
          copy: "Write any valid F²ORGE statements here: equations, imports, solves, conversions, assignments, prints, or expressions. Script nodes run before connected output nodes.",
          confirm: "Add script",
          value: "# F²ORGE statements\n",
          multiline: true,
        });
        if (!result.confirmed || !result.value.trim()) return;
        value = result.value;
      } else {
        value = "";
      }
    }
    value = String(value).trim();
    if (["Input", "Output"].includes(kind) &&
        (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(value) || reservedNames.has(value))) {
      setStatus(`'${value}' is not a valid ${kind.toLowerCase()} name`);
      return;
    }
    if (kind === "Output2") {
      const names = value.split(",").map((part) => part.trim());
      if (names.length < 2 ||
          names.some((name) => !/^[A-Za-z_][A-Za-z0-9_]*$/.test(name) || reservedNames.has(name))) {
        setStatus("A two-output node needs at least two valid names, separated by commas");
        return;
      }
      value = names.join(", ");
    }
    if (kind === "Call" && !/^[A-Za-z_][A-Za-z0-9_]*$/.test(value)) {
      setStatus(`'${value}' is not a function or equation name`);
      return;
    }
    if (kind === "Compare") {
      const chosen = comparisons[value.toLowerCase().replace(/\s/g, "")];
      if (!chosen) {
        setStatus("Use <, <=, >, >=, ==, != for like kinds, or mag<, mag<=, mag>, mag>= for sizes");
        return;
      }
      value = chosen;
    }
    if (["Input", "Output"].includes(kind) && hasSharedName(kind, value)) {
      const produces = kind === "Output";
      const decision = await showGraphDialog({
        title: "Share this variable?",
        copy: produces
          ? `An Input node already uses “${value}”. This Output will assign that same F²ORGE variable, so connected computations can read its value. F²ORGE will order the output before dependent outputs.`
          : `An Output node already assigns “${value}”. This Input will read that shared value, and the graph compiler will run the matching output first.`,
        confirm: "Share variable",
      });
      if (!decision.confirmed) {
        setStatus("Shared variable cancelled");
        return;
      }
    }
    const node = {
      id: nextId++, kind, value: String(value).trim(),
      x: x ?? Math.max(35, graphCanvas.scrollLeft + 100 + (nodes.length % 4) * 225),
      y: y ?? Math.max(35, graphCanvas.scrollTop + 85 + Math.floor(nodes.length / 4) * 145),
      w: 190,
      h: kind === "Script" ? 190 : Math.max(88, 62 + nodeInputs[kind] * 22),
    };
    nodes.push(node);
    $("#canvas-hint").hidden = true;
    renderGraph();
    selectNode(node.id);
    setStatus(`${kind} node added`);
  }

  function selectNode(id) {
    selectedId = id;
    nodeLayer.querySelectorAll(".node-card").forEach((card) => {
      card.classList.toggle("selected", Number(card.dataset.id) === id);
    });
  }

  function addSvgPath(className, path, color) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", "path");
    element.setAttribute("d", path);
    element.setAttribute("class", className);
    if (color) element.setAttribute("stroke", color);
    wireLayer.append(element);
  }

  function nodeById(id) {
    return nodes.find((node) => node.id === id);
  }

  function resizeCanvasToNodes() {
    graphCanvas.style.width = `${Math.max(2400, ...nodes.map((node) => node.x + node.w + 110))}px`;
    graphCanvas.style.height = `${Math.max(1600, ...nodes.map((node) => node.y + node.h + 110))}px`;
  }

  function drawWires() {
    wireLayer.replaceChildren();
    wireLayer.setAttribute("viewBox", `0 0 ${graphCanvas.scrollWidth} ${graphCanvas.scrollHeight}`);
    for (const [key, sourceId] of Object.entries(links)) {
      const [targetId, inputIndex] = key.split(":").map(Number);
      const source = nodeById(sourceId);
      const target = nodeById(targetId);
      if (!source || !target) continue;
      const sx = source.x + source.w, sy = source.y + source.h / 2;
      const tx = target.x, ty = target.y + 42 + inputIndex * 22;
      const bend = Math.max(38, Math.abs(tx - sx) * 0.45);
      addSvgPath("wire", `M ${sx} ${sy} C ${sx + bend} ${sy}, ${tx - bend} ${ty}, ${tx} ${ty}`);
    }
    if (wireSource !== null && pointerPosition) {
      const source = nodeById(wireSource);
      if (source) {
        const sx = source.x + source.w, sy = source.y + source.h / 2;
        const bend = Math.max(38, Math.abs(pointerPosition.x - sx) * 0.45);
        addSvgPath("wire pending", `M ${sx} ${sy} C ${sx + bend} ${sy}, ${pointerPosition.x - bend} ${pointerPosition.y}, ${pointerPosition.x} ${pointerPosition.y}`);
      }
    }
  }

  let pointerPosition = null;

  function renderGraph() {
    resizeCanvasToNodes();
    nodeLayer.replaceChildren();
    for (const node of nodes) {
      const card = document.createElement("article");
      card.className = `node-card${selectedId === node.id ? " selected" : ""}`;
      card.dataset.id = node.id;
      card.dataset.kind = node.kind;
      card.style.left = `${node.x}px`;
      card.style.top = `${node.y}px`;
      card.style.width = `${node.w}px`;
      card.style.height = `${node.h}px`;

      const header = document.createElement("header");
      header.className = "node-head";
      const title = document.createElement("span");
      title.textContent = node.kind;
      if (["Input", "Output"].includes(node.kind) && hasSharedName(node.kind, node.value)) {
        const shared = document.createElement("span");
        shared.className = "node-shared";
        shared.textContent = "SHARED";
        title.append(shared);
      }
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "node-remove";
      remove.title = "Delete node";
      remove.textContent = "×";
      remove.style.cssText = "border:0;background:transparent;color:inherit;opacity:.72;font-size:16px;cursor:pointer;padding:0 2px;";
      remove.addEventListener("pointerdown", (event) => event.stopPropagation());
      remove.addEventListener("click", (event) => {
        event.stopPropagation();
        removeNode(node.id);
      });
      header.append(title, remove);
      header.addEventListener("pointerdown", (event) => startDrag(event, node, card));

      const body = document.createElement("div");
      body.className = "node-body";
      if (node.kind === "Script") {
        const code = document.createElement("textarea");
        code.className = "node-code";
        code.value = node.value;
        code.setAttribute("aria-label", "F²ORGE script node");
        code.addEventListener("input", () => { node.value = code.value; });
        code.addEventListener("pointerdown", (event) => event.stopPropagation());
        body.append(code);
      } else {
        body.textContent = node.value || (symbols[node.kind] || "connect inputs");
      }
      card.append(header, body);
      for (let index = 0; index < nodeInputs[node.kind]; index += 1) {
        // A Call node grows an extra pin each time its last one is filled.
        if (node.kind === "Call" && index > 0 && links[`${node.id}:${index - 1}`] === undefined) break;
        const input = document.createElement("button");
        input.type = "button";
        input.className = "node-in";
        input.title = `Input ${index + 1}`;
        input.style.top = `${35 + index * 22}px`;
        input.addEventListener("pointerdown", (event) => event.stopPropagation());
        input.addEventListener("click", (event) => {
          event.stopPropagation();
          if (wireSource === null) {
            setStatus("Choose an output pin first");
            return;
          }
          if (wireSource === node.id) {
            setStatus("A node cannot connect to itself");
            wireSource = null;
            renderGraph();
            return;
          }
          links[`${node.id}:${index}`] = wireSource;
          wireSource = null;
          pointerPosition = null;
          renderGraph();
          setStatus("Nodes connected");
        });
        card.append(input);
      }
      if (node.kind !== "Output" && node.kind !== "Script") {
        const pin = document.createElement("button");
        pin.type = "button";
        pin.className = `node-out${wireSource === node.id ? " active" : ""}`;
        pin.title = "Connect to an input";
        pin.addEventListener("pointerdown", (event) => event.stopPropagation());
        pin.style.top = `${node.h / 2 - 6}px`;
        pin.addEventListener("click", (event) => {
          event.stopPropagation();
          wireSource = node.id;
          pointerPosition = { x: node.x + node.w + 50, y: node.y + node.h / 2 };
          renderGraph();
          setStatus("Choose an input pin");
        });
        card.append(pin);
      }
      const resize = document.createElement("button");
      resize.type = "button";
      resize.className = "node-resize";
      resize.title = "Resize node";
      resize.setAttribute("aria-label", "Resize node");
      resize.addEventListener("pointerdown", (event) => startResize(event, node, card));
      card.append(resize);
      card.addEventListener("pointerdown", () => selectNode(node.id));
      nodeLayer.append(card);
    }
    $("#canvas-hint").hidden = nodes.length > 0;
    drawWires();
  }

  function startDrag(event, node, card) {
    if (event.target.closest(".node-remove")) return;
    event.preventDefault();
    selectNode(node.id);
    const startX = event.clientX;
    const startY = event.clientY;
    const originX = node.x;
    const originY = node.y;
    const move = (moveEvent) => {
      node.x = Math.max(0, originX + moveEvent.clientX - startX);
      node.y = Math.max(0, originY + moveEvent.clientY - startY);
      card.style.left = `${node.x}px`;
      card.style.top = `${node.y}px`;
      resizeCanvasToNodes();
      drawWires();
    };
    const stop = () => {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", stop);
    };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", stop, { once: true });
  }

  function startResize(event, node, card) {
    event.preventDefault();
    event.stopPropagation();
    selectNode(node.id);
    const startX = event.clientX;
    const startY = event.clientY;
    const initialWidth = node.w;
    const initialHeight = node.h;
    const move = (moveEvent) => {
      node.w = Math.min(900, Math.max(150, initialWidth + moveEvent.clientX - startX));
      node.h = Math.min(900, Math.max(88, initialHeight + moveEvent.clientY - startY,
        62 + nodeInputs[node.kind] * 22));
      card.style.width = `${node.w}px`;
      card.style.height = `${node.h}px`;
      const output = card.querySelector(".node-out");
      if (output) output.style.top = `${node.h / 2 - 6}px`;
      resizeCanvasToNodes();
      drawWires();
    };
    const stop = () => {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", stop);
    };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", stop, { once: true });
  }

  function removeNode(id) {
    const index = nodes.findIndex((node) => node.id === id);
    if (index < 0) return;
    nodes.splice(index, 1);
    for (const key of Object.keys(links)) {
      const [targetId] = key.split(":").map(Number);
      if (targetId === id || links[key] === id) delete links[key];
    }
    if (selectedId === id) selectedId = null;
    if (wireSource === id) wireSource = null;
    renderGraph();
    setStatus("Node deleted");
  }

  function compileGraph() {
    const outputs = nodes.filter((node) => node.kind === "Output" || node.kind === "Output2");
    const scripts = nodes.filter((node) => node.kind === "Script" && node.value.trim());
    if (!outputs.length && !scripts.length) throw new Error("Add an Output node or an F²ORGE Script node.");
    const memo = new Map();
    const visiting = new Set();
    function expression(id) {
      if (memo.has(id)) return memo.get(id);
      if (visiting.has(id)) throw new Error("The graph contains a cycle.");
      const node = nodeById(id);
      if (!node) throw new Error("A connected node no longer exists.");
      visiting.add(id);
      let result;
      if (node.kind === "Input") {
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(node.value) || reservedNames.has(node.value)) {
          throw new Error(`Invalid input variable name: ${node.value}`);
        }
        result = node.value;
      } else if (node.kind === "Constant") result = node.value;
      else if (node.kind === "Function") {
        if (!supportedFunctions.includes(node.value)) throw new Error(`Unsupported function: ${node.value || "(empty)"}`);
        const source = links[`${id}:0`];
        if (source === undefined) throw new Error(`${node.value} node ${id} needs an input connected.`);
        result = `${node.value}(${expression(source)})`;
      } else if (node.kind === "Call") {
        // One input pin per argument: area(r) uses one, cross(a, b) two.
        const args = [];
        for (let index = 0; links[`${id}:${index}`] !== undefined; index += 1) {
          args.push(expression(links[`${id}:${index}`]));
        }
        if (!args.length) throw new Error(`Call node ${id} needs at least one argument connected.`);
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(node.value)) {
          throw new Error(`Invalid function or equation name: ${node.value || "(empty)"}`);
        }
        result = `${node.value}(${args.join(", ")})`;
      } else if (symbols[node.kind]) {
        const left = links[`${id}:0`], right = links[`${id}:1`];
        if (left === undefined || right === undefined) throw new Error(`${node.kind} node ${id} needs both inputs connected.`);
        if (node.kind === "Compare") {
          const chosen = comparisons[node.value] || symbols.Compare;
          const call = magnitudeCalls[chosen];
          result = call
            ? `${call}(${expression(left)}, ${expression(right)})`
            : `(${expression(left)} ${chosen} ${expression(right)})`;
        } else {
          result = `(${expression(left)} ${symbols[node.kind]} ${expression(right)})`;
        }
      } else {
        throw new Error("Output nodes cannot be used as input values.");
      }
      visiting.delete(id);
      memo.set(id, result);
      return result;
    }
    function collectInputs(id, found = new Set(), visited = new Set()) {
      if (visited.has(id)) return found;
      visited.add(id);
      const node = nodeById(id);
      if (!node) throw new Error("A connected node no longer exists.");
      if (node.kind === "Input") {
        found.add(node.value);
        return found;
      }
      if (node.kind === "Function") {
        const source = links[`${id}:0`];
        if (source !== undefined) collectInputs(source, found, visited);
      } else if (node.kind === "Call") {
        for (let index = 0; links[`${id}:${index}`] !== undefined; index += 1) {
          collectInputs(links[`${id}:${index}`], found, visited);
        }
      } else if (symbols[node.kind]) {
        for (let index = 0; index < 2; index += 1) {
          const source = links[`${id}:${index}`];
          if (source !== undefined) collectInputs(source, found, visited);
        }
      }
      return found;
    }

    const names = new Set();
    const outputsByName = new Map();
    for (const node of outputs) {
      const parts = node.kind === "Output2" ? node.value.split(",").map((part) => part.trim()) : [node.value];
      for (const part of parts) {
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(part) || reservedNames.has(part)) {
          throw new Error(`Invalid output variable name: ${part}`);
        }
        if (names.has(part)) throw new Error(`Output variable '${part}' is used more than once.`);
        names.add(part);
        outputsByName.set(part, node);
      }
    }
    const ordered = [];
    const visited = new Set();
    const visitingOutputs = new Set();
    function orderOutput(node) {
      if (visited.has(node.id)) return;
      if (visitingOutputs.has(node.id)) {
        throw new Error(`Shared variables create a circular dependency involving '${node.value}'.`);
      }
      const source = links[`${node.id}:0`];
      if (source === undefined) throw new Error(`Output node ${node.id} needs an input connected.`);
      visitingOutputs.add(node.id);
      for (const inputName of collectInputs(source)) {
        const dependency = outputsByName.get(inputName);
        if (dependency) orderOutput(dependency);
      }
      visitingOutputs.delete(node.id);
      visited.add(node.id);
      ordered.push(node);
    }
    outputs.forEach(orderOutput);

    const lines = scripts.map((node) => node.value.trim());
    for (const node of ordered) {
      const source = links[`${node.id}:0`];
      if (node.kind === "Output2") {
        // Unpack a function that returns several parts: [t, v] = solveODE(...).
        const parts = node.value.split(",").map((part) => part.trim());
        lines.push(`[${parts.join(", ")}] = ${expression(source)}`, ...parts);
        continue;
      }
      lines.push(`${node.value} = ${expression(source)}`, node.value);
    }
    return lines.filter(Boolean).join("\n");
  }

  function saveGraph() {
    const data = {
      version: 2,
      nodes: nodes.map(({ id, kind, value, x, y, w, h }) => ({
        id, kind, value, x, y, width: w, height: h,
      })),
      connections: Object.entries(links).map(([key, source]) => {
        const [target, input] = key.split(":").map(Number);
        return { source, target, input };
      }),
    };
    download("Untitled.fgraph", JSON.stringify(data, null, 2), "application/json");
    setStatus("Graph downloaded");
  }

  function openGraph(data) {
    if (!data || ![1, 2].includes(data.version) ||
        !Array.isArray(data.nodes) || !Array.isArray(data.connections)) {
      throw new Error("This is not a supported F²ORGE graph file.");
    }
    const ids = new Set();
    const restored = data.nodes.map((item) => {
      if (!item || !Number.isInteger(item.id) || item.id <= 0 || ids.has(item.id) ||
          !Object.prototype.hasOwnProperty.call(nodeInputs, item.kind) || typeof item.value !== "string" ||
          !Number.isFinite(item.x) || !Number.isFinite(item.y) ||
          Math.abs(item.x) > 100000 || Math.abs(item.y) > 100000) {
        throw new Error("Graph contains an invalid node.");
      }
      ids.add(item.id);
      const width = item.width ?? 190;
      const height = item.height ?? (item.kind === "Script" ? 190 : Math.max(88, 62 + nodeInputs[item.kind] * 22));
      if (!Number.isFinite(width) || !Number.isFinite(height) ||
          width < 150 || width > 900 || height < 88 || height > 900) {
        throw new Error("Graph contains an invalid node size.");
      }
      return { id: item.id, kind: item.kind, value: item.value, x: item.x, y: item.y, w: width, h: height };
    });
    const restoredLinks = {};
    for (const connection of data.connections) {
      const target = restored.find((node) => node.id === connection.target);
      const source = restored.find((node) => node.id === connection.source);
      const key = `${connection.target}:${connection.input}`;
      if (!ids.has(connection.source) || !ids.has(connection.target) ||
          !source || source.kind === "Output" || source.kind === "Output2" ||
          source.kind === "Script" ||
          !target ||
          !Number.isInteger(connection.input) || connection.input < 0 ||
          (target.kind !== "Call" && connection.input >= nodeInputs[target.kind]) ||
          Object.prototype.hasOwnProperty.call(restoredLinks, key)) {
        throw new Error("Graph contains an invalid connection.");
      }
      restoredLinks[key] = connection.source;
    }
    nodes.splice(0, nodes.length, ...restored);
    Object.keys(links).forEach((key) => delete links[key]);
    Object.assign(links, restoredLinks);
    nextId = Math.max(0, ...nodes.map((node) => node.id)) + 1;
    selectedId = null;
    wireSource = null;
    renderGraph();
    setStatus("Graph loaded");
    setPanel("blueprint-panel");
  }

  async function refreshState() {
    try {
      renderWorkspace(await request("/api/state"));
      $("#server-status").textContent = "Connected to local kernel";
    } catch (error) {
      $("#server-status").textContent = error.message;
    }
  }

  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => setPanel(tab.dataset.panel)));
  $("#refresh-worksheets").addEventListener("click", refreshState);
  document.querySelectorAll(".node-add").forEach((button) => button.addEventListener("click", () => addNode(button.dataset.node)));
  $("#run-script").addEventListener("click", () => runSource(editor.value));
  $("#trace-script").addEventListener("click", () => debugScript("/api/trace", "Trace"));
  $("#profile-script").addEventListener("click", () => debugScript("/api/profile", "Profile"));
  $("#run-graph").addEventListener("click", () => {
    try { runSource(compileGraph()); }
    catch (error) { setStatus(error.message); appendOutput(error.message, false); }
  });
  $("#save-file").addEventListener("click", saveScript);
  $("#export-script").addEventListener("click", convertScript);
  $("#download-transpiled").addEventListener("click", () => {
    const sourceName = currentFile?.name || "Untitled.forge";
    const baseName = sourceName.replace(/\.forge$/i, "").replace(/\.eq$/i, "");
    if (generatedTarget === "ti-basic" && generatedBinary) {
      downloadBinary(`${baseName}.8xp`, generatedBinary);
      return;
    }
    const extension = {
      cpp: "cpp",
      "ti-basic": "ti.txt",
      micropython: "py",
      python: "py",
    }[generatedTarget];
    const mime = generatedTarget === "cpp" ? "text/x-c++src" : "text/plain";
    download(`${baseName}.${extension}`, $("#transpile-output").value, `${mime};charset=utf-8`);
  });
  $("#copy-transpiled").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("#transpile-output").value);
      pushConsole("Generated code copied to clipboard");
    } catch (error) {
      pushConsole(`Could not copy generated code: ${error.message}`, "error");
    }
  });
  $("#open-file").addEventListener("click", () => {
    if (currentFile?.dirty && !window.confirm("Discard unsaved changes and open another file?")) return;
    $("#file-picker").click();
  });
  $("#file-picker").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      editor.value = text;
      currentFile = { name: file.name, dirty: false };
      updateDirty();
      $("#line-count").textContent = `${text.split("\n").length} ${text.split("\n").length === 1 ? "line" : "lines"}`;
      setPanel("script-panel");
    } catch (error) {
      appendOutput(`Could not open file: ${error.message}`, false);
    } finally {
      event.target.value = "";
    }
  });
  $("#graph-picker").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try { openGraph(JSON.parse(await file.text())); }
    catch (error) { appendOutput(`Could not open graph: ${error.message}`, false); }
    finally { event.target.value = ""; }
  });
  $("#save-graph").addEventListener("click", saveGraph);
  $("#open-graph").addEventListener("click", () => $("#graph-picker").click());
  $("#delete-node").addEventListener("click", () => {
    if (selectedId === null) setStatus("Select a node to delete");
    else removeNode(selectedId);
  });
  $("#chart-csv").addEventListener("input", () => {
    invalidateChart();
    try { refreshChartSelectors(); }
    catch (error) { $("#chart-error").textContent = error.message; }
  });
  $("#chart-type").addEventListener("change", () => {
    invalidateChart();
    try { refreshChartSelectors(); }
    catch (error) { $("#chart-error").textContent = error.message; }
  });
  $("#chart-x").addEventListener("change", () => {
    invalidateChart();
    try { refreshChartSelectors(); }
    catch (error) { $("#chart-error").textContent = error.message; }
  });
  $("#chart-series").addEventListener("change", (event) => {
    const selected = $("#chart-series").querySelectorAll("input:checked").length;
    const overLimit = selected > 10;
    if (overLimit) event.target.checked = false;
    invalidateChart();
    if (overLimit) $("#chart-error").textContent = "Select no more than 10 value series.";
  });
  $("#chart-y3").addEventListener("change", invalidateChart);
  $("#chart-z3").addEventListener("change", invalidateChart);
  $("#add-chart-row").addEventListener("click", () => {
    invalidateChart();
    try {
      const parsed = parseCsv($("#chart-csv").value);
      parsed.rows.push(parsed.columns.map(() => ""));
      $("#chart-csv").value = serializeCsv([
        parsed.columns.map((column) => column.name + (column.unit ? ` [${column.unit}]` : "")),
        ...parsed.rows,
      ]);
      refreshChartSelectors();
    } catch (error) { $("#chart-error").textContent = error.message; }
  });
  $("#add-chart-column").addEventListener("click", () => {
    invalidateChart();
    try {
      const parsed = parseCsv($("#chart-csv").value);
      let name = "column";
      let suffix = 2;
      while (parsed.columns.some((column) => column.name === name)) name = `column${suffix++}`;
      parsed.columns.push({ name, unit: "" });
      parsed.rows.forEach((row) => row.push(""));
      $("#chart-csv").value = serializeCsv([
        parsed.columns.map((column) => column.name + (column.unit ? ` [${column.unit}]` : "")),
        ...parsed.rows,
      ]);
      refreshChartSelectors();
    } catch (error) { $("#chart-error").textContent = error.message; }
  });
  $("#import-csv").addEventListener("click", () => $("#csv-picker").click());
  $("#csv-picker").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      invalidateChart();
      $("#chart-csv").value = await file.text();
      refreshChartSelectors();
    } catch (error) { $("#chart-error").textContent = `Could not import CSV: ${error.message}`; }
    finally { event.target.value = ""; }
  });
  $("#render-chart").addEventListener("click", renderChart);
  $("#download-chart-svg").addEventListener("click", () => {
    try {
      if (!chartResult?.svg) throw new Error("SVG export is available for 2D charts.");
      downloadChart("f2orge-chart.svg", chartResult.svg, "image/svg+xml");
    } catch (error) { $("#chart-error").textContent = error.message; }
  });
  $("#download-chart-html").addEventListener("click", () => {
    try { downloadChart("f2orge-chart.html", chartHtml(), "text/html"); }
    catch (error) { $("#chart-error").textContent = error.message; }
  });
  $("#download-chart-png").addEventListener("click", () => {
    downloadChartPng().catch((error) => { $("#chart-error").textContent = error.message; });
  });
  $("#print-chart").addEventListener("click", () => {
    try {
      const url = URL.createObjectURL(new Blob([chartHtml()], { type: "text/html" }));
      const printWindow = window.open(url, "_blank");
      if (!printWindow) throw new Error("Allow pop-ups to print or save this chart as PDF.");
      printWindow.addEventListener("load", () => printWindow.print(), { once: true });
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) { $("#chart-error").textContent = error.message; }
  });
  $("#theme-toggle").addEventListener("click", () => {
    document.body.classList.toggle("dark");
    localStorage.setItem("f2orge-theme", document.body.classList.contains("dark") ? "dark" : "light");
  });
  $("#refresh-workspace").addEventListener("click", refreshState);
  $("#clear-output").addEventListener("click", () => { output.textContent = ""; output.classList.remove("error"); });
  $("#clear-workspace").addEventListener("click", async () => {
    try {
      const data = await request("/api/clear", {});
      renderWorkspace(data);
      appendOutput("", true);
      pushConsole("Workspace cleared");
    } catch (error) { pushConsole(error.message, "error"); }
  });
  $("#command-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("#command-input");
    const command = input.value.trim();
    if (!command || busy) return;
    input.value = "";
    commandHistory.push(command);
    historyIndex = commandHistory.length;
    if (/^plot(?:\s|\()/i.test(command)) {
      await showPlot(command, `› ${command}`);
      return;
    }
    await runSource(command, `› ${command}`);
  });
  $("#close-plot").addEventListener("click", () => $("#plot-dialog").close());
  editor.addEventListener("input", () => {
    if (currentFile) currentFile.dirty = true;
    updateDirty();
    const count = editor.value.split("\n").length;
    $("#line-count").textContent = `${count} ${count === 1 ? "line" : "lines"}`;
  });
  editor.addEventListener("keydown", (event) => {
    if (event.key === "Tab") {
      event.preventDefault();
      const start = editor.selectionStart;
      editor.setRangeText("    ", start, editor.selectionEnd, "end");
      editor.dispatchEvent(new Event("input"));
    }
  });
  $("#command-input").addEventListener("keydown", (event) => {
    if (event.key === "ArrowUp") {
      event.preventDefault();
      historyIndex = Math.max(0, historyIndex - 1);
      event.currentTarget.value = commandHistory[historyIndex] || "";
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      historyIndex = Math.min(commandHistory.length, historyIndex + 1);
      event.currentTarget.value = commandHistory[historyIndex] || "";
    }
  });
  graphCanvas.addEventListener("pointermove", (event) => {
    if (wireSource === null) return;
    const bounds = graphCanvas.getBoundingClientRect();
    pointerPosition = {
      x: event.clientX - bounds.left + graphCanvas.scrollLeft,
      y: event.clientY - bounds.top + graphCanvas.scrollTop,
    };
    drawWires();
  });
  graphCanvas.addEventListener("click", (event) => {
    if (event.target === graphCanvas || event.target === nodeLayer) {
      selectedId = null;
      nodeLayer.querySelectorAll(".node-card").forEach((card) => card.classList.remove("selected"));
    }
  });
  graphCanvas.addEventListener("keydown", (event) => {
    if ((event.key === "Delete" || event.key === "Backspace") && selectedId !== null) {
      event.preventDefault();
      removeNode(selectedId);
    }
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      runSource(editor.value);
    }
  });
  if (localStorage.getItem("f2orge-theme") === "dark") document.body.classList.add("dark");
  const initialLineCount = editor.value.split("\n").length;
  $("#line-count").textContent = `${initialLineCount} ${initialLineCount === 1 ? "line" : "lines"}`;
  updateDirty();
  renderGraph();
  try { refreshChartSelectors(); } catch (error) { $("#chart-error").textContent = error.message; }
  refreshState();
})();
