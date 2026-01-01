/* exported normalizeFlow, isAccessFile, isDuckdbFile, getFlowFromName, isSupportedFileName */
/* exported getFileStem, buildAccessStemSet, isConvertedDuckdb, isFileAllowedForFlow */
/* exported formatBytes, formatDate */
function normalizeFlow(flow) {
  return flow === "access" ? "access" : "duckdb";
}

function isAccessFile(name) {
  var lower = (name || "").toLowerCase();
  return lower.endsWith(".mdb") || lower.endsWith(".accdb");
}

function isDuckdbFile(name) {
  var lower = (name || "").toLowerCase();
  return (
    lower.endsWith(".duckdb") ||
    lower.endsWith(".db") ||
    lower.endsWith(".sqlite") ||
    lower.endsWith(".sqlite3")
  );
}

function getFlowFromName(name) {
  if (isAccessFile(name)) return "access";
  if (isDuckdbFile(name)) return "duckdb";
  return "";
}

function isSupportedFileName(name) {
  return isAccessFile(name) || isDuckdbFile(name);
}

function getFileStem(name) {
  var lower = (name || "").toLowerCase();
  return lower
    .replace(/\.(mdb|accdb)$/, "")
    .replace(/\.(duckdb|db|sqlite|sqlite3)$/, "");
}

function buildAccessStemSet(list) {
  var stems = new Set();
  (list || []).forEach(function (f) {
    if (!f || !f.name) return;
    if (isAccessFile(f.name)) stems.add(getFileStem(f.name));
  });
  return stems;
}

function isConvertedDuckdb(name, accessStems) {
  if (!isDuckdbFile(name)) return false;
  if (!accessStems || !accessStems.has) return false;
  return accessStems.has(getFileStem(name));
}

function isFileAllowedForFlow(fileName, flow) {
  if (normalizeFlow(flow) === "access") return isAccessFile(fileName);
  return isDuckdbFile(fileName);
}

function formatBytes(size) {
  var num = Number(size);
  if (!Number.isFinite(num) || num < 0) return "0 B";
  if (num < 1024) return num + " B";
  var kb = num / 1024;
  if (kb < 1024) return kb.toFixed(1) + " KB";
  var mb = kb / 1024;
  if (mb < 1024) return mb.toFixed(1) + " MB";
  var gb = mb / 1024;
  return gb.toFixed(1) + " GB";
}

function formatDate(isoText) {
  if (!isoText) return "";
  var d = new Date(isoText);
  if (!Number.isFinite(d.getTime())) return "";
  var yyyy = d.getFullYear();
  var mm = String(d.getMonth() + 1).padStart(2, "0");
  var dd = String(d.getDate()).padStart(2, "0");
  var hh = String(d.getHours()).padStart(2, "0");
  var min = String(d.getMinutes()).padStart(2, "0");
  return yyyy + "-" + mm + "-" + dd + " " + hh + ":" + min;
}
