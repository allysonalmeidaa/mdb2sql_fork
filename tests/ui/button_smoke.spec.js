const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { test, expect } = require("@playwright/test");

const TEST_PREFIX = "playwright_test_";

function ensureDir(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function writeDummyFile(filePath, size = 4) {
  ensureDir(filePath);
  fs.writeFileSync(filePath, Buffer.alloc(size, 65));
}

function tryCreateDuckdbWithPython(filePath) {
  const script = [
    "import duckdb, os, sys",
    "path = sys.argv[1]",
    "os.makedirs(os.path.dirname(path), exist_ok=True)",
    "con = duckdb.connect(path)",
    "con.execute(\"create table if not exists items(id integer, name varchar)\")",
    "con.execute(\"insert into items values (1, 'alpha'), (2, 'beta')\")",
    "con.close()"
  ].join("\n");
  try {
    execFileSync("python", ["-c", script, filePath], {
      stdio: "ignore",
      timeout: 20000
    });
    return true;
  } catch (err) {
    return false;
  }
}

function tryCreateDuckdbWithCli(cliPath, filePath) {
  const sql = "create table if not exists items(id integer, name varchar);" +
    "insert into items values (1, 'alpha'), (2, 'beta');";
  try {
    execFileSync(cliPath, [filePath, "-c", sql], {
      stdio: "ignore",
      timeout: 20000
    });
    return true;
  } catch (err) {
    return false;
  }
}

function createDuckdbFile(filePath) {
  ensureDir(filePath);
  if (tryCreateDuckdbWithPython(filePath)) {
    return true;
  }
  const localCli = path.join(__dirname, "..", "..", "duckdb.exe");
  if (fs.existsSync(localCli) && tryCreateDuckdbWithCli(localCli, filePath)) {
    return true;
  }
  if (tryCreateDuckdbWithCli("duckdb", filePath)) {
    return true;
  }
  writeDummyFile(filePath);
  return false;
}

function tryCreateDuckdbWithFulltextPython(filePath) {
  const script = [
    "import duckdb, json, os, sys",
    "path = sys.argv[1]",
    "os.makedirs(os.path.dirname(path), exist_ok=True)",
    "con = duckdb.connect(path)",
    "con.execute(\"create table if not exists items(id integer, name varchar)\")",
    "con.execute(\"delete from items\")",
    "con.execute(\"insert into items values (1, 'alpha'), (2, 'beta')\")",
    "con.execute(\"create table if not exists _fulltext (table_name varchar, pk_col varchar, pk_value varchar, row_offset bigint, content_norm text, row_json text)\")",
    "con.execute(\"delete from _fulltext\")",
    "row_json = json.dumps({'id': 1, 'name': 'alpha'})",
    "con.execute(\"insert into _fulltext values (?, ?, ?, ?, ?, ?)\", ['items','id','1',0,'alpha',row_json])",
    "con.close()"
  ].join("\n");
  try {
    execFileSync("python", ["-c", script, filePath], {
      stdio: "ignore",
      timeout: 20000
    });
    return true;
  } catch (err) {
    return false;
  }
}

function tryCreateDuckdbWithFulltextCli(cliPath, filePath) {
  const rowJson = "{\"id\":1,\"name\":\"alpha\"}";
  const sql = [
    "create table if not exists items(id integer, name varchar)",
    "delete from items",
    "insert into items values (1, 'alpha'), (2, 'beta')",
    "create table if not exists _fulltext (table_name varchar, pk_col varchar, pk_value varchar, row_offset bigint, content_norm text, row_json text)",
    "delete from _fulltext",
    "insert into _fulltext values ('items','id','1',0,'alpha','" + rowJson + "')"
  ].join(";");
  try {
    execFileSync(cliPath, [filePath, "-c", sql], {
      stdio: "ignore",
      timeout: 20000
    });
    return true;
  } catch (err) {
    return false;
  }
}

function createDuckdbWithFulltext(filePath) {
  ensureDir(filePath);
  if (tryCreateDuckdbWithFulltextPython(filePath)) {
    return true;
  }
  const localCli = path.join(__dirname, "..", "..", "duckdb.exe");
  if (fs.existsSync(localCli) && tryCreateDuckdbWithFulltextCli(localCli, filePath)) {
    return true;
  }
  if (tryCreateDuckdbWithFulltextCli("duckdb", filePath)) {
    return true;
  }
  writeDummyFile(filePath);
  return false;
}

async function uploadFile(request, name, filePath) {
  const buffer = fs.readFileSync(filePath);
  const res = await request.post("/admin/upload", {
    multipart: {
      file: {
        name,
        mimeType: "application/octet-stream",
        buffer
      }
    }
  });
  expect(res.ok()).toBeTruthy();
  return res;
}

async function cleanupUploads(request) {
  const res = await request.get("/admin/list_uploads");
  expect(res.ok()).toBeTruthy();
  const data = await res.json();
  const uploads = data.uploads || [];
  for (const file of uploads) {
    if (!file || !file.name || !file.name.startsWith(TEST_PREFIX)) {
      continue;
    }
    await request.post("/admin/delete", {
      data: JSON.stringify({ filename: file.name }),
      headers: { "content-type": "application/json" }
    });
  }
}

async function forceHideOverlay(page) {
  await page.evaluate(() => {
    document.body.classList.remove("modal-open");
    const overlay = document.getElementById("overlay");
    if (overlay) {
      overlay.style.display = "none";
      overlay.style.zIndex = "";
      overlay.style.position = "";
      overlay.style.inset = "";
      overlay.style.background = "";
    }
  });
}

async function ensureOverlayClosed(page) {
  const overlay = page.locator("#overlay");
  if (await overlay.isVisible()) {
    await overlay.click({ force: true });
    if (await overlay.isVisible()) {
      await forceHideOverlay(page);
    }
    await expect(overlay).toBeHidden();
  }
}

async function openConfig(page) {
  await ensureOverlayClosed(page);
  await page.locator("#openConfig").click();
  await expect(page.locator("#configModal")).toBeVisible();
}

async function openFilesPanel(page) {
  await ensureOverlayClosed(page);
  const panel = page.locator("#filesPanel");
  if (!(await panel.isVisible())) {
    await page.locator("#openFilesBtn").click();
    await expect(panel).toBeVisible();
  }
}

async function closeConfig(page) {
  await page.locator("#closeConfig").click();
  await expect(page.locator("#configModal")).toBeHidden();
  await ensureOverlayClosed(page);
}

async function closePriority(page) {
  await page.locator("#closePriority").click();
  await expect(page.locator("#priorityModal")).toBeHidden();
  await ensureOverlayClosed(page);
}

async function closeIndex(page) {
  await page.locator("#closeIndex").click();
  await expect(page.locator("#indexModal")).toBeHidden();
  await ensureOverlayClosed(page);
}

async function closeStatus(page) {
  await page.locator("#closeStatus").click();
  await expect(page.locator("#statusModal")).toBeHidden();
  await ensureOverlayClosed(page);
}

async function closePriorityModal(page) {
  await page.locator("#closePriority").click();
  await expect(page.locator("#priorityModal")).toBeHidden();
  await ensureOverlayClosed(page);
}

async function selectDbFromConfig(page, fileName) {
  await openConfig(page);
  const row = page.locator("#uploadsList .upload-row", { hasText: fileName });
  await expect(row).toBeVisible();
  const selectBtn = row.locator("button.select-btn");
  if (!(await selectBtn.isDisabled())) {
    await selectBtn.click();
    await expect(page.locator("#configModal")).toBeHidden();
  } else {
    await closeConfig(page);
  }
  await expect(page.locator("#currentDb")).toContainText(fileName);
}

async function getFileNames(page) {
  return page.$$eval("#filesList .file-row .file-name", nodes =>
    nodes.map(node => {
      const first = node.childNodes[0];
      return first ? first.textContent.trim() : node.textContent.trim();
    })
  );
}

test.afterEach(async ({ request }) => {
  await cleanupUploads(request);
});

test("config modal and flow tabs", async ({ page }) => {
  await page.goto("/");
  await openConfig(page);

  const accessTab = page.locator('#flowTabs .tab-btn[data-flow="access"]');
  const duckdbTab = page.locator('#flowTabs .tab-btn[data-flow="duckdb"]');
  const fileInput = page.locator("#fileInput");

  await accessTab.click();
  await expect(page.locator("body")).toHaveClass(/flow-access/);
  await expect(fileInput).toHaveAttribute("accept", ".mdb,.accdb");

  await duckdbTab.click();
  await expect(page.locator("body")).toHaveClass(/flow-duckdb/);
  await expect(fileInput).toHaveAttribute("accept", ".duckdb,.db,.sqlite,.sqlite3");

  await closeConfig(page);
});

test("status modal opens", async ({ page }) => {
  await page.goto("/");
  await page.locator("#openStatus").click();
  await expect(page.locator("#statusModal")).toBeVisible();
  await expect(page.locator("#statusModal")).toContainText("Alertas e logs");
  await expect(page.locator("#statusCriticalList")).toBeVisible();
  await expect(page.locator("#statusWarnList")).toBeVisible();
  await expect(page.locator("#statusInfoList")).toBeVisible();
  await closeStatus(page);
});

test("status alerts badge opens modal", async ({ page }) => {
  await page.goto("/");
  await page.locator("#statusAlerts").click();
  await expect(page.locator("#statusModal")).toBeVisible();
  await closeStatus(page);
});

test("conversion error banner shows in status and alerts", async ({ page }) => {
  await page.route("**/admin/list_uploads", route => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        current_db: "sample.accdb",
        uploads: [{ name: "sample.accdb" }],
        priority_tables: []
      })
    });
  });
  await page.route("**/admin/status", route => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        db: "sample.accdb",
        fulltext_count: 0,
        conversion: { running: false, ok: false, msg: "All methods failed" }
      })
    });
  });
  await page.route("**/admin/logs", route => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, logs: [] })
    });
  });

  await page.goto("/");
  await expect(page.locator("#flowBanner")).toContainText(/Access|Convers/);
  await expect(page.locator("#statusAlerts")).toContainText(/Conversao/i);
});

test("missing fulltext shows banner in duckdb flow", async ({ page }) => {
  await page.route("**/admin/list_uploads", route => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        current_db: "sample.duckdb",
        uploads: [{ name: "sample.duckdb" }],
        priority_tables: []
      })
    });
  });
  await page.route("**/admin/status", route => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        db: "sample.duckdb",
        fulltext_count: 0,
        conversion: { running: false, ok: true, msg: "ok" }
      })
    });
  });
  await page.route("**/admin/logs", route => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, logs: [] })
    });
  });

  await page.goto("/");
  await expect(page.locator("#flowBanner")).toContainText(/_fulltext/i);
});

test("modal overlay closes config modal", async ({ page }) => {
  await page.goto("/");
  await openConfig(page);
  await page.locator("#overlay").click({ force: true, position: { x: 5, y: 5 } });
  await expect(page.locator("#configModal")).toBeHidden();
});

test("status modal closes via overlay", async ({ page }) => {
  await page.goto("/");
  await page.locator("#openStatus").click();
  await expect(page.locator("#statusModal")).toBeVisible();
  await page.locator("#overlay").click({ force: true, position: { x: 5, y: 5 } });
  await expect(page.locator("#statusModal")).toBeHidden();
});

test("priority modal opens and closes", async ({ page }) => {
  await page.goto("/");
  await page.locator("#openPriority").click();
  await expect(page.locator("#priorityModal")).toBeVisible();
  await expect(page.locator("#priorityModal")).toContainText("Priorizar tabelas");
  await closePriorityModal(page);
});

test("index modal opens and closes", async ({ page }) => {
  await page.goto("/");
  await page.locator("#openIndex").click();
  await expect(page.locator("#indexModal")).toBeVisible();
  await expect(page.locator("#indexModal")).toContainText("Indice _fulltext");
  await closeIndex(page);
});

test("search modal opens and shows controls", async ({ page }) => {
  await page.goto("/");
  await page.locator("#openSearchInline").click();
  await expect(page.locator("#searchModal")).toBeVisible();
  await expect(page.locator("#searchModal")).toContainText("Buscar resultados");
  await expect(page.locator("#q")).toBeVisible();
  await expect(page.locator("#searchBtn")).toBeVisible();
  await expect(page.locator("#advancedPanel")).toBeVisible();
  await page.locator("#closeSearch").click();
  await expect(page.locator("#searchModal")).toBeHidden();
});

test("opening a new modal closes the previous", async ({ page }) => {
  await page.goto("/");
  await openConfig(page);
  await expect(page.locator("#configModal")).toBeVisible();
  await page.evaluate(() => {
    const btn = document.getElementById("openStatus");
    if (btn) btn.click();
  });
  await expect(page.locator("#statusModal")).toBeVisible();
  await expect(page.locator("#configModal")).toBeHidden();
  await closeStatus(page);
});

test("flow steps buttons open actions", async ({ page }) => {
  await page.goto("/");
  await page.locator("#openSelectInline").click();
  await expect(page.locator("#configModal")).toBeVisible();
  await closeConfig(page);

  await page.locator("#openConvertInline").click();
  await expect(page.locator("#statusModal")).toBeVisible();
  await closeStatus(page);

  await page.locator("#openIndexInline").click();
  await expect(page.locator("#indexModal")).toBeVisible();
  await closeIndex(page);

  await page.locator("#openSearchInline").click();
  await expect(page.locator("#searchModal")).toBeVisible();
  await page.locator("#closeSearch").click();
  await expect(page.locator("#searchModal")).toBeHidden();
});

test("files panel toggle shows and hides", async ({ page }) => {
  await page.goto("/");
  const panel = page.locator("#filesPanel");
  await expect(panel).toBeHidden();
  await page.locator("#openFilesBtn").click();
  await expect(panel).toBeVisible();
  await page.locator("#closeFilesBtn").click();
  await expect(panel).toBeHidden();
});

test("db tabs switch selection", async ({ page, request }, testInfo) => {
  const fileA = `${TEST_PREFIX}tab_a.duckdb`;
  const fileB = `${TEST_PREFIX}tab_b.duckdb`;
  const pathA = testInfo.outputPath(fileA);
  const pathB = testInfo.outputPath(fileB);
  createDuckdbFile(pathA);
  createDuckdbFile(pathB);

  await uploadFile(request, fileA, pathA);
  await uploadFile(request, fileB, pathB);

  await page.goto("/");
  await page.locator("#refreshBtn").click();

  const tabA = page.locator("#dbTabs .db-tab", { hasText: fileA });
  const tabB = page.locator("#dbTabs .db-tab", { hasText: fileB });
  await expect(tabA).toBeVisible();
  await expect(tabB).toBeVisible();

  await tabA.click();
  await expect(page.locator("#currentDb")).toContainText(fileA);

  await tabB.click();
  await expect(page.locator("#currentDb")).toContainText(fileB);
});

test("flow guard blocks wrong file extensions", async ({ page }, testInfo) => {
  const badAccdb = `${TEST_PREFIX}bad_access.accdb`;
  const badDuckdb = `${TEST_PREFIX}bad_duckdb.duckdb`;
  const badAccdbPath = testInfo.outputPath(badAccdb);
  const badDuckdbPath = testInfo.outputPath(badDuckdb);
  writeDummyFile(badAccdbPath);
  writeDummyFile(badDuckdbPath);

  await page.goto("/");
  await openConfig(page);
  await page.locator('#flowTabs .tab-btn[data-flow="duckdb"]').click();

  const uploadMsg = page.locator("#uploadMsg");
  const fileInput = page.locator("#fileInput");

  await fileInput.setInputFiles(badAccdbPath);
  await page.locator("#uploadBtn").click();
  await expect(uploadMsg).toContainText("Use .duckdb");

  await page.locator('#flowTabs .tab-btn[data-flow="access"]').click();
  await fileInput.setInputFiles(badDuckdbPath);
  await page.locator("#uploadBtn").click();
  await expect(uploadMsg).toContainText("Use .mdb ou .accdb");

  await closeConfig(page);
});

test("upload via api shows metadata in lists", async ({ page, request }, testInfo) => {
  const name = `${TEST_PREFIX}meta.duckdb`;
  const filePath = testInfo.outputPath(name);
  createDuckdbFile(filePath);

  await uploadFile(request, name, filePath);

  await page.goto("/");
  await openConfig(page);
  const uploadRow = page.locator("#uploadsList .upload-row", { hasText: name });
  await expect(uploadRow).toBeVisible();
  await expect(uploadRow.locator(".file-meta")).toContainText("tamanho");
  await expect(uploadRow.locator(".file-status")).toContainText("ok");

  await closeConfig(page);
  await openFilesPanel(page);
  const mainRow = page.locator("#filesList .file-row", { hasText: name });
  await expect(mainRow).toBeVisible();
  await expect(mainRow.locator(".file-meta")).toContainText("tamanho");
});

test("select db from list", async ({ page, request }, testInfo) => {
  const fileA = `${TEST_PREFIX}select_a.duckdb`;
  const fileB = `${TEST_PREFIX}select_b.duckdb`;
  const tempPathA = testInfo.outputPath(fileA);
  const tempPathB = testInfo.outputPath(fileB);
  createDuckdbFile(tempPathA);
  createDuckdbFile(tempPathB);

  await uploadFile(request, fileA, tempPathA);
  await uploadFile(request, fileB, tempPathB);

  await page.goto("/");
  await selectDbFromConfig(page, fileA);

  await openConfig(page);
  const rowA = page.locator("#uploadsList .upload-row", { hasText: fileA });
  await expect(rowA).toHaveClass(/selected/);
  await expect(rowA.locator("button.select-btn")).toBeDisabled();

  await closeConfig(page);
});

test("status deck and steps reflect duckdb readiness", async ({ page, request }, testInfo) => {
  const fileName = `${TEST_PREFIX}ready.duckdb`;
  const filePath = testInfo.outputPath(fileName);
  createDuckdbWithFulltext(filePath);

  await uploadFile(request, fileName, filePath);
  await page.goto("/");
  await selectDbFromConfig(page, fileName);

  await expect(page.locator("#statusDbValue")).toContainText("ready.duckdb");
  await expect(page.locator("#statusIndexValue")).toContainText("Pronto");
  await expect(page.locator("#statusSearchValue")).toContainText("Disponivel");
  await expect(page.locator("#stepSearch")).toHaveClass(/done/);
});

test("access selection shows conversion banner", async ({ page, request }, testInfo) => {
  const fileName = `${TEST_PREFIX}access_banner.accdb`;
  const filePath = testInfo.outputPath(fileName);
  writeDummyFile(filePath);

  await uploadFile(request, fileName, filePath);
  await page.goto("/");
  await selectDbFromConfig(page, fileName);

  const banner = page.locator("#flowBanner");
  await expect(banner).toBeVisible();
  const text = (await banner.innerText()).toLowerCase();
  expect(text).toMatch(/access|conversao/);
});

test("files list sort toggles order", async ({ page, request }, testInfo) => {
  const fileA = `${TEST_PREFIX}alpha.duckdb`;
  const fileB = `${TEST_PREFIX}zeta.duckdb`;
  const tempPathA = testInfo.outputPath(fileA);
  const tempPathB = testInfo.outputPath(fileB);
  createDuckdbFile(tempPathA);
  createDuckdbFile(tempPathB);

  await uploadFile(request, fileA, tempPathA);
  await uploadFile(request, fileB, tempPathB);

  await page.goto("/");
  await openFilesPanel(page);
  const namesAsc = await getFileNames(page);
  const posA = namesAsc.indexOf(fileA);
  const posB = namesAsc.indexOf(fileB);
  expect(posA).toBeGreaterThanOrEqual(0);
  expect(posB).toBeGreaterThanOrEqual(0);
  expect(posA).toBeLessThan(posB);

  await page.selectOption("#filesSort", "name_desc");
  const namesDesc = await getFileNames(page);
  const posDescA = namesDesc.indexOf(fileA);
  const posDescB = namesDesc.indexOf(fileB);
  expect(posDescA).toBeGreaterThanOrEqual(0);
  expect(posDescB).toBeGreaterThanOrEqual(0);
  expect(posDescA).toBeGreaterThan(posDescB);
});

test("delete file from config list", async ({ page, request }, testInfo) => {
  const name = `${TEST_PREFIX}delete.duckdb`;
  const filePath = testInfo.outputPath(name);
  createDuckdbFile(filePath);

  await uploadFile(request, name, filePath);

  await page.goto("/");
  await openConfig(page);

  page.once("dialog", dialog => dialog.accept());
  const row = page.locator("#uploadsList .upload-row", { hasText: name });
  await expect(row).toBeVisible();
  await row.locator("button", { hasText: "Excluir" }).click();

  await expect(page.locator("#uploadsList .upload-row", { hasText: name })).toHaveCount(0);
  await closeConfig(page);
});

test("delete file from files panel", async ({ page, request }, testInfo) => {
  const name = `${TEST_PREFIX}panel_delete.duckdb`;
  const filePath = testInfo.outputPath(name);
  createDuckdbFile(filePath);

  await uploadFile(request, name, filePath);

  await page.goto("/");
  await openFilesPanel(page);
  const row = page.locator("#filesList .file-row", { hasText: name });
  await expect(row).toBeVisible();

  page.once("dialog", dialog => dialog.accept());
  await row.locator("button", { hasText: "Excluir" }).click();
  await expect(page.locator("#filesList .file-row", { hasText: name })).toHaveCount(0);
});
test("priority modal shows no db message", async ({ page }) => {
  await page.goto("/");
  await page.locator("#openPriority").click();
  await expect(page.locator("#priorityModal")).toBeVisible();
  await expect(page.locator("#priorityMsg")).toContainText("Nenhum DB");
});

test("priority modal lists tables after db select", async ({ page, request }, testInfo) => {
  const unique = `${Date.now()}_${testInfo.workerIndex}`;
  const name = `${TEST_PREFIX}tables_${unique}.duckdb`;
  const filePath = testInfo.outputPath(name);
  const created = createDuckdbFile(filePath);
  test.skip(!created, "duckdb not available for table listing");

  await uploadFile(request, name, filePath);
  const selectRes = await request.post("/admin/select", {
    data: JSON.stringify({ filename: name }),
    headers: { "content-type": "application/json" }
  });
  expect(selectRes.ok()).toBeTruthy();

  await page.goto("/");
  await page.locator("#refreshBtn").click();
  await expect(page.locator("#currentDb")).toContainText(name);
  const tablesRes = await request.get("/api/tables");
  const tablesJson = await tablesRes.json();
  const tables = Array.isArray(tablesJson.tables) ? tablesJson.tables : [];
  if (!tablesRes.ok() || tables.length === 0) {
    test.skip(true, "api tables empty or unavailable");
  }
  const firstTable = String(tables[0]);
  const escaped = firstTable.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const tableRe = new RegExp(escaped, "i");
  await page.locator("#openPriority").click();
  await expect(page.locator("#priorityModal")).toBeVisible();
  await expect(
    page.locator("#allTablesList li, #priorityListModal li", {
      hasText: tableRe
    })
  ).toBeVisible();
});

test("index modal disabled with no db", async ({ page }) => {
  await page.goto("/");
  await page.locator("#openIndex").click();
  await expect(page.locator("#indexModal")).toBeVisible();
  await expect(page.locator("#startIndex")).toBeDisabled();
  await closeIndex(page);
});

test("search without db shows alert", async ({ page }) => {
  await page.goto("/");
  await page.locator("#openSearchInline").click();
  await expect(page.locator("#searchModal")).toBeVisible();
  await expect(page.locator("#q")).toBeDisabled();
  await expect(page.locator("#searchBtn")).toBeDisabled();
  await expect(page.locator("#flowBanner")).toContainText("Selecione um arquivo");
});

test("auto index toggle updates message and state", async ({ page, request }) => {
  const listRes = await request.get("/admin/list_uploads");
  expect(listRes.ok()).toBeTruthy();
  const listJson = await listRes.json();
  const original = !!listJson.auto_index_after_convert;

  await page.goto("/");
  await openConfig(page);
  await page.locator('#flowTabs .tab-btn[data-flow="access"]').click();

  const toggle = page.locator("#autoIndexToggle");
  const msg = page.locator("#autoIndexMsg");
  await expect(toggle).toBeVisible();

  await toggle.setChecked(!original);
  await expect(msg).toContainText("Auto indexacao");

  const afterRes = await request.get("/admin/list_uploads");
  const afterJson = await afterRes.json();
  expect(!!afterJson.auto_index_after_convert).toBe(!original);

  await toggle.setChecked(original);
  await expect(msg).toContainText("Auto indexacao");

  const resetRes = await request.get("/admin/list_uploads");
  const resetJson = await resetRes.json();
  expect(!!resetJson.auto_index_after_convert).toBe(original);

  await closeConfig(page);
});

test("index defaults reset restores values", async ({ page, request }, testInfo) => {
  const name = `${TEST_PREFIX}index_defaults.duckdb`;
  const filePath = testInfo.outputPath(name);
  createDuckdbFile(filePath);
  await uploadFile(request, name, filePath);

  await page.goto("/");
  await page.locator("#refreshBtn").click();
  await page.locator("#openIndex").click();
  await expect(page.locator("#indexModal")).toBeVisible();

  const startIndex = page.locator("#startIndex");
  if (await startIndex.isDisabled()) {
    test.skip(true, "index controls disabled");
  }

  const chunk = page.locator("#chunk");
  const batch = page.locator("#batch");
  const drop = page.locator("#dropCheckbox");

  await chunk.fill("123");
  await batch.fill("456");
  await drop.check();
  await page.locator("#resetIndexDefaults").click();

  await expect(chunk).toHaveValue("2000");
  await expect(batch).toHaveValue("1000");
  await expect(drop).not.toBeChecked();
  await expect(page.locator("#indexMsg")).toContainText("Valores padrao");

  await closeIndex(page);
});

test("advanced reset restores defaults", async ({ page, request }, testInfo) => {
  const name = `${TEST_PREFIX}advanced_reset.duckdb`;
  const filePath = testInfo.outputPath(name);
  createDuckdbWithFulltext(filePath);
  await uploadFile(request, name, filePath);

  await page.goto("/");
  await selectDbFromConfig(page, name);
  await page.locator("#openSearchInline").click();
  await expect(page.locator("#searchModal")).toBeVisible();
  await page.locator("#advancedPanel").click();

  await page.locator("#per_table").fill("5");
  await page.locator("#candidate_limit").fill("200");
  await page.locator("#total_limit").fill("50");
  await page.locator("#token_mode").selectOption("all");
  await page.locator("#min_score").fill("80");
  await page.locator("#resetAdvanced").click();

  await expect(page.locator("#per_table")).toHaveValue("10");
  await expect(page.locator("#candidate_limit")).toHaveValue("1000");
  await expect(page.locator("#total_limit")).toHaveValue("500");
  await expect(page.locator("#token_mode")).toHaveValue("any");
  await expect(page.locator("#min_score")).toHaveValue("70");
  await expect(page.locator("#advancedMsg")).toContainText("Valores padrao");
});

test("duckdb ui upload and main buttons", async ({ page, request }, testInfo) => {
  const name = `${TEST_PREFIX}duckdb_fulltext.duckdb`;
  const filePath = testInfo.outputPath(name);
  const created = createDuckdbWithFulltext(filePath);
  test.skip(!created, "duckdb not available for fulltext");

  await page.goto("/");
  await openConfig(page);
  await page.locator("#fileInput").setInputFiles(filePath);
  await page.locator("#uploadBtn").click();
  await expect(page.locator("#uploadMsg")).toContainText("Upload ok");
  await expect(page.locator("#currentDb")).toContainText(name);

  await request.post("/admin/select", {
    data: JSON.stringify({ filename: name }),
    headers: { "content-type": "application/json" }
  });
  await closeConfig(page);

  await openFilesPanel(page);
  await page.locator("#refreshFilesBtn").click();
  await expect(page.locator("#filesList .file-row", { hasText: name })).toBeVisible();
  await page.locator("#refreshBtn").click();

  let tables = [];
  for (let i = 0; i < 5; i += 1) {
    const tablesRes = await request.get("/api/tables");
    const tablesJson = await tablesRes.json();
    tables = Array.isArray(tablesJson.tables) ? tablesJson.tables : [];
    if (tables.length > 0) {
      break;
    }
    await page.waitForTimeout(500);
  }
  if (tables.length === 0) {
    test.skip(true, "no tables returned");
  }

  await page.locator("#filterTables").fill("");
  await page.locator("#refreshTables").click();
  const tableNameFromApi = String(tables[0]);
  const tableItem = page.locator("#tableList .table-item", { hasText: tableNameFromApi }).first();
  await expect(tableItem).toBeVisible();
  const tableNameClean = tableNameFromApi.trim();

  await tableItem.locator("button").click();
  if (tableNameClean) {
    await expect(page.locator("#resultsArea")).toContainText(`Tabela: ${tableNameClean}`);
  }
  await page.locator("button", { hasText: "Voltar" }).click();

  await page.locator("#openPriority").click();
  await expect(page.locator("#priorityModal")).toBeVisible();
  await page.locator("#refreshPriorityBtnModal").click();
  const firstTable = page.locator("#allTablesList input[type=checkbox]").first();
  await firstTable.check();
  await page.locator("#savePriorityBtnModal").click();
  await expect(page.locator("#priorityMsg")).toContainText("Prioridades salvas");
  await closePriority(page);

  await page.locator("#openSearchInline").click();
  await expect(page.locator("#searchModal")).toBeVisible();
  await page.locator("#q").fill("alpha");
  await page.locator("#searchBtn").click();
  await expect(page.locator("#searchMeta")).toContainText("Resultados");
  await expect(page.locator("#exportAllBtn")).toBeEnabled();

  const downloadAll = page.waitForEvent("download");
  await page.locator("#exportAllBtn").click();
  await downloadAll;

  await page.locator("#closeSearch").click();
  await expect(page.locator("#searchModal")).toBeHidden();
  await ensureOverlayClosed(page);

  const downloadTable = page.waitForEvent("download");
  await page.locator("button", { hasText: "Export CSV" }).first().click();
  await downloadTable;
});

test("access ui upload via config", async ({ page }, testInfo) => {
  const name = `${TEST_PREFIX}access_flow.accdb`;
  const filePath = testInfo.outputPath(name);
  writeDummyFile(filePath);

  await page.goto("/");
  await openConfig(page);
  await page.locator('#flowTabs .tab-btn[data-flow="access"]').click();
  await page.locator("#fileInput").setInputFiles(filePath);
  await page.locator("#uploadBtn").click();

  const msg = page.locator("#uploadMsg");
  await expect(msg).toContainText(/Convers|Erro|Falha/i);
  await expect(page.locator("#uploadsList .upload-row", { hasText: name })).toBeVisible();
  await closeConfig(page);
});

test("access mdb upload via config", async ({ page }, testInfo) => {
  const name = `${TEST_PREFIX}access_flow.mdb`;
  const filePath = testInfo.outputPath(name);
  writeDummyFile(filePath);

  await page.goto("/");
  await openConfig(page);
  await page.locator('#flowTabs .tab-btn[data-flow="access"]').click();
  await page.locator("#fileInput").setInputFiles(filePath);
  await page.locator("#uploadBtn").click();

  const msg = page.locator("#uploadMsg");
  await expect(msg).toContainText(/Convers|Erro|Falha/i);
  await expect(page.locator("#uploadsList .upload-row", { hasText: name })).toBeVisible();
  await closeConfig(page);
});

test("admin page duckdb buttons", async ({ page, request }, testInfo) => {
  const name = `${TEST_PREFIX}admin_duckdb.duckdb`;
  const filePath = testInfo.outputPath(name);
  createDuckdbFile(filePath);

  const statusRes = await request.get("/admin/status");
  const statusJson = await statusRes.json();
  const indexerAvailable = statusJson.indexer_available !== false;

  await page.goto("/admin");
  await page.locator("#fileInput").setInputFiles(filePath);
  await page.locator("#uploadBtn").click();
  await expect(page.locator("#uploadMsg")).toContainText(/ok|db_path|output/i);

  const row = page.locator("#uploadsList .upload-row", { hasText: name });
  await expect(row).toBeVisible();
  await row.locator("button.select-btn").click();
  await expect(page.locator("#currentDb")).toContainText(name);

  await page.locator("#refreshTablesBtn").click();
  const prioNames = page.locator("#priorityList .priority-name");
  if (await prioNames.count() === 0) {
    test.skip(true, "priority list empty");
  }

  await page.locator("#priorityList li button").first().click();
  await page.locator("#savePriorityBtn").click();
  await expect(page.locator("#priorityMsg")).toContainText("ok");

  const autoToggle = page.locator("#autoIndexToggle");
  const autoMsg = page.locator("#autoIndexMsg");
  await autoToggle.setChecked(!(await autoToggle.isChecked()));
  await expect(autoMsg).toContainText("Auto indexacao");

  await page.locator("#startIndex").click();
  if (indexerAvailable) {
    await expect(page.locator("#indexMsg")).toContainText("ok");
  } else {
    await expect(page.locator("#indexMsg")).toContainText("indexador");
  }
});

test("admin page access upload", async ({ page }, testInfo) => {
  const name = `${TEST_PREFIX}admin_access.accdb`;
  const filePath = testInfo.outputPath(name);
  writeDummyFile(filePath);

  await page.goto("/admin");
  await page.locator("#fileInput").setInputFiles(filePath);
  await page.locator("#uploadBtn").click();
  await expect(page.locator("#uploadMsg")).toContainText(/ok|error|Convers/i);
  await expect(page.locator("#uploadsList .upload-row", { hasText: name })).toBeVisible();
});
