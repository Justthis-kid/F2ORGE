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

  const nodeInputs = {
    Input: 0, Constant: 0, Script: 0, Function: 1, Add: 2, Subtract: 2,
    Multiply: 2, Divide: 2, Power: 2, Output: 1,
  };
  const symbols = { Add: "+", Subtract: "-", Multiply: "*", Divide: "/", Power: "^" };
  const supportedFunctions = ["sin", "cos", "tan", "asin", "acos", "atan", "exp", "ln", "log", "sqrt", "abs"];
  const reservedNames = new Set(["eq", "import", "export", "solve", "convert", "print", "for"]);

  function setStatus(message) {
    $("#graph-message").textContent = message;
  }

  async function convertScript() {
    if (busy) return;
    const target = $("#export-target").value;
    $("#export-script").disabled = true;
    try {
      const result = await request("/api/transpile", { source: editor.value, target });
      generatedTarget = target;
      $("#transpile-title").textContent = `Generated ${target === "cpp" ? "C++" : "Python"}`;
      $("#transpile-output").value = result.output;
      $("#transpile-dialog").showModal();
    } catch (error) {
      pushConsole(error.message, "error");
      $("#server-status").textContent = "Code conversion failed";
    } finally {
      $("#export-script").disabled = false;
    }
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
    for (const button of [$("#run-script"), $("#run-graph"), $("#export-script"), $(".command-submit")]) {
      button.disabled = value;
    }
    $("#run-script").innerHTML = value ? "Running…" : '<span class="play-icon">▶</span> Run <kbd>Ctrl ↵</kbd>';
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
    for (const [label, items, valueFor] of [
      ["VARIABLES", data.variables || [], (item) => item.value],
      ["EQUATIONS", data.equations || [], (item) => item.signature],
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
        mark.textContent = label === "VARIABLES" ? "x" : "ƒ";
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
        Output: ["Output variable name", "result"],
      };
      if (defaults[kind]) {
        value = window.prompt(defaults[kind][0], defaults[kind][1]);
        if (value === null || !value.trim()) return;
      } else if (kind === "Script") {
        const result = await showGraphDialog({
          title: "Add F²ORGE script",
          copy: "Write any valid F²ORGE statements here: equations, imports, solves, conversions, loops, prints, or expressions. Script nodes run before connected output nodes.",
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
    const outputs = nodes.filter((node) => node.kind === "Output");
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
      } else if (symbols[node.kind]) {
        const left = links[`${id}:0`], right = links[`${id}:1`];
        if (left === undefined || right === undefined) throw new Error(`${node.kind} node ${id} needs both inputs connected.`);
        result = `(${expression(left)} ${symbols[node.kind]} ${expression(right)})`;
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
      if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(node.value) || reservedNames.has(node.value)) {
        throw new Error(`Invalid output variable name: ${node.value}`);
      }
      if (names.has(node.value)) throw new Error(`Output variable '${node.value}' is used more than once.`);
      names.add(node.value);
      outputsByName.set(node.value, node);
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
          !source || source.kind === "Output" || source.kind === "Script" ||
          !target ||
          !Number.isInteger(connection.input) || connection.input < 0 ||
          connection.input >= nodeInputs[target.kind] ||
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
  document.querySelectorAll(".node-add").forEach((button) => button.addEventListener("click", () => addNode(button.dataset.node)));
  $("#run-script").addEventListener("click", () => runSource(editor.value));
  $("#run-graph").addEventListener("click", () => {
    try { runSource(compileGraph()); }
    catch (error) { setStatus(error.message); appendOutput(error.message, false); }
  });
  $("#save-file").addEventListener("click", saveScript);
  $("#export-script").addEventListener("click", convertScript);
  $("#download-transpiled").addEventListener("click", () => {
    const sourceName = currentFile?.name || "Untitled.forge";
    const baseName = sourceName.replace(/\.forge$/i, "").replace(/\.eq$/i, "");
    const extension = generatedTarget === "cpp" ? "cpp" : "py";
    const mime = generatedTarget === "cpp" ? "text/x-c++src" : "text/x-python";
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
    await runSource(command, `› ${command}`);
  });
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
  refreshState();
})();
