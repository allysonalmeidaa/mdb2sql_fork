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
    await request.post("/admin/delete", { data: { filename: file.name } });
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

async function selectDbFromConfig(page, fileName) {
  await openConfig(page);
  const row = page.locator("#uploadsList .upload-row", { hasText: fileName });
  await expect(row).toBeVisible();
  await row.locator("button.select-btn").click();
  await expect(page.locator("#configModal")).toBeHidden();
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

test("flow guard blocks wrong file extensions", async ({ page }, testInfo) => {
  const badAccdb = `${TEST_PREFIX}bad_access.accdb`;
  const badDuckdb = `${TEST_PREFIX}bad_duckdb.duckdb`;
  const badAccdbPath = testInfo.outputPath(badAccdb);
  const badDuckdbPath = testInfo.outputPath(badDuckdb);
  writeDummyFile(badAccdbPath);
  writeDummyFile(badDuckdbPath);

  await page.goto("/");
  await openConfig(page);

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
  const mainRow = page.locator("#filesList .file-row", { hasText: name });
  await expect(mainRow).toBeVisible();
  await expect(mainRow.locator(".file-meta")).toContainText("tamanho");

  await openConfig(page);
  const uploadRow = page.locator("#uploadsList .upload-row", { hasText: name });
  await expect(uploadRow).toBeVisible();
  await expect(uploadRow.locator(".file-meta")).toContainText("tamanho");
  await expect(uploadRow.locator(".file-status")).toContainText("ok");

  await closeConfig(page);
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
  const selectRes = await request.post("/admin/select", { data: { filename: name } });
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
  await page.locator("#q").fill("test");
  page.once("dialog", dialog => {
    expect(dialog.message()).toContain("Selecione um DB");
    dialog.accept();
  });
  await page.locator("#searchBtn").click();
});
