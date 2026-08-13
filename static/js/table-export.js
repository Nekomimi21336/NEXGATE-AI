(function () {
  "use strict";

  const TABLE_EXPORT_CSV_ICON =
    '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false"><path fill="currentColor" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2 5 5h-5V4zM8 13h8v2H8v-2zm0 4h8v2H8v-2z"/></svg>';
  const TABLE_EXPORT_PNG_ICON =
    '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false"><path fill="currentColor" d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>';

  function t(key, fallback) {
    if (typeof window.t === "function") return window.t(key);
    return fallback;
  }

  function cssVar(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function tableMatrix(table) {
    const rows = [];
    table.querySelectorAll("tr").forEach((tr) => {
      const cells = [...tr.querySelectorAll("th, td")].map((cell) =>
        (cell.innerText || cell.textContent || "").replace(/\s+/g, " ").trim()
      );
      if (cells.length) rows.push(cells);
    });
    return rows;
  }

  function csvCell(text) {
    const value = String(text ?? "");
    if (/[",\n\r]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
    return value;
  }

  function tableToCsv(table) {
    const matrix = tableMatrix(table);
    const colCount = Math.max(0, ...matrix.map((row) => row.length));
    return matrix
      .map((row) => {
        const padded = [...row];
        while (padded.length < colCount) padded.push("");
        return padded.map(csvCell).join(",");
      })
      .join("\r\n");
  }

  function buildTableFilename(ext) {
    const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "").replace("T", "-");
    return `table-${stamp}.${ext}`;
  }

  function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function rowIsHeader(tr) {
    return Boolean(tr.querySelector("th"));
  }

  async function tableToPngBlob(table) {
    const matrix = tableMatrix(table);
    if (!matrix.length) throw new Error("empty table");

    const sampleCell = table.querySelector("th, td");
    const cellStyle = sampleCell ? getComputedStyle(sampleCell) : getComputedStyle(table);
    const padX = 10;
    const padY = 6;
    const borderWidth = 1;
    const scale = Math.min(3, Math.max(2, window.devicePixelRatio || 1));

    const font = `${cellStyle.fontWeight} ${cellStyle.fontSize} ${cellStyle.fontFamily}`;
    const headerFont = (() => {
      const th = table.querySelector("th");
      if (!th) return font;
      const thStyle = getComputedStyle(th);
      return `${thStyle.fontWeight} ${thStyle.fontSize} ${thStyle.fontFamily}`;
    })();

    const measureCanvas = document.createElement("canvas");
    const measureCtx = measureCanvas.getContext("2d");
    if (!measureCtx) throw new Error("canvas unsupported");

    const colCount = Math.max(...matrix.map((row) => row.length));
    const colWidths = new Array(colCount).fill(48);
    const rowHeights = matrix.map(() => 32);
    const lineHeight = parseFloat(cellStyle.lineHeight) || parseFloat(cellStyle.fontSize) * 1.4 || 18;

    const trList = [...table.querySelectorAll("tr")];
    matrix.forEach((row, rowIndex) => {
      measureCtx.font = trList[rowIndex] && rowIsHeader(trList[rowIndex]) ? headerFont : font;
      row.forEach((cell, colIndex) => {
        const width = Math.ceil(measureCtx.measureText(cell || " ").width) + padX * 2;
        colWidths[colIndex] = Math.max(colWidths[colIndex], width);
      });
      rowHeights[rowIndex] = Math.max(rowHeights[rowIndex], Math.ceil(lineHeight + padY * 2));
    });

    const outerPad = 16;
    const logicalW = colWidths.reduce((sum, w) => sum + w, 0) + borderWidth * (colCount + 1) + outerPad * 2;
    const logicalH = rowHeights.reduce((sum, h) => sum + h, 0) + borderWidth * (matrix.length + 1) + outerPad * 2;

    const canvas = document.createElement("canvas");
    canvas.width = Math.ceil(logicalW * scale);
    canvas.height = Math.ceil(logicalH * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("canvas unsupported");
    ctx.scale(scale, scale);

    const bg = cssVar("--bg-secondary", "#ffffff");
    const headerBg = cssVar("--bg-input", "#f3f4f6");
    const borderColor = cssVar("--border", "#d1d5db");
    const textColor = cssVar("--text-primary", "#111827");

    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, logicalW, logicalH);

    let y = outerPad;
    matrix.forEach((row, rowIndex) => {
      const tr = trList[rowIndex];
      const isHeader = tr && rowIsHeader(tr);
      let x = outerPad;
      const rowHeight = rowHeights[rowIndex];

      row.forEach((cell, colIndex) => {
        const colWidth = colWidths[colIndex];
        ctx.fillStyle = isHeader ? headerBg : bg;
        ctx.fillRect(x, y, colWidth + borderWidth, rowHeight + borderWidth);
        ctx.strokeStyle = borderColor;
        ctx.lineWidth = borderWidth;
        ctx.strokeRect(x + borderWidth / 2, y + borderWidth / 2, colWidth, rowHeight);

        ctx.fillStyle = textColor;
        ctx.font = isHeader ? headerFont : font;
        ctx.textBaseline = "middle";
        ctx.textAlign = "left";
        ctx.fillText(cell || "", x + borderWidth + padX, y + borderWidth + rowHeight / 2);

        x += colWidth + borderWidth;
      });

      y += rowHeight + borderWidth;
    });

    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error("png encode failed"));
      }, "image/png");
    });
  }

  function setButtonBusy(btn, busy) {
    if (!btn) return;
    btn.disabled = busy;
    btn.classList.toggle("is-busy", busy);
  }

  async function downloadTableCsv(table, btn) {
    setButtonBusy(btn, true);
    try {
      const csv = tableToCsv(table);
      const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });
      triggerDownload(blob, buildTableFilename("csv"));
    } catch (err) {
      console.warn("table csv export failed", err);
    } finally {
      setButtonBusy(btn, false);
    }
  }

  async function downloadTablePng(table, btn) {
    setButtonBusy(btn, true);
    try {
      const blob = await tableToPngBlob(table);
      triggerDownload(blob, buildTableFilename("png"));
    } catch (err) {
      console.warn("table png export failed", err);
    } finally {
      setButtonBusy(btn, false);
    }
  }

  function createExportButton(className, iconHtml, i18nKey, fallbackLabel, onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `md-table-export-btn ${className}`;
    btn.dataset.i18nAria = i18nKey;
    btn.innerHTML = iconHtml;
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      void onClick(btn);
    });
    return btn;
  }

  function refreshTableExportLabels(bar) {
    bar.querySelectorAll(".md-table-export-btn").forEach((btn) => {
      const key = btn.dataset.i18nAria;
      const fallback = btn.title || "";
      const label = key ? t(key, fallback) : fallback;
      btn.setAttribute("aria-label", label);
      btn.title = label;
    });
  }

  function ensureTableExportButtons(wrap, table) {
    if (!wrap || !table) return;
    let bar = wrap.querySelector(".md-table-export-bar");
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "md-table-export-bar";
      bar.setAttribute("role", "group");

      const csvBtn = createExportButton(
        "md-table-export-csv",
        TABLE_EXPORT_CSV_ICON,
        "tableExportCsvAria",
        "CSVでダウンロード",
        (btn) => downloadTableCsv(table, btn)
      );
      const pngBtn = createExportButton(
        "md-table-export-png",
        TABLE_EXPORT_PNG_ICON,
        "tableExportPngAria",
        "画像でダウンロード",
        (btn) => downloadTablePng(table, btn)
      );

      bar.appendChild(csvBtn);
      bar.appendChild(pngBtn);
      wrap.appendChild(bar);
    }
    refreshTableExportLabels(bar);
  }

  window.ensureTableExportButtons = ensureTableExportButtons;
  window.refreshTableExportLabels = function refreshAllTableExportLabels(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll(".md-table-export-bar").forEach(refreshTableExportLabels);
  };
})();
