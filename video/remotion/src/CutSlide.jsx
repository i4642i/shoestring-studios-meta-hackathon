import React from "react";
import {Img, staticFile, useCurrentFrame} from "remotion";
import katex from "katex";

export const CUT_W = 1280;
export const CUT_H = 720;
export const CUT_FPS = 30;
export const CUT_MAX_S = 30;

// Reveal steps (seconds per item) — mirrored in
// agents/_frame/schemas.py (REVEAL_STEP_S); keep in sync.
export const REVEAL_STEP_S = {table: 0.5, formula: 1.0, steps: 0.8};

const boxStyle = (b, order) => ({
  position: "absolute",
  left: b.box.x,
  top: b.box.y,
  width: b.box.w,
  height: b.box.h,
  zIndex: order,
  overflow: "hidden",
});

function ImageBlock({b, order}) {
  if (!b.file) return null;
  return (
    <div style={boxStyle(b, order)}>
      <Img
        src={staticFile(b.file)}
        style={{width: "100%", height: "100%", objectFit: "contain"}}
      />
    </div>
  );
}

function TableBlock({b, order, frame, fps}) {
  const data = b.data || {};
  const headers = data.headers || [];
  const rows = data.rows || [];
  const reveal = data.reveal === "rows" ? "rows" : "all";
  const font = b.font_size || 24;
  const shown = rows.filter(
    (_, i) => reveal === "all" || frame >= (b.appear_s + i * REVEAL_STEP_S.table) * fps,
  );
  return (
    <div style={{...boxStyle(b, order), fontSize: font}}>
      <table
        style={{borderCollapse: "collapse", width: "100%"}}
        cellPadding={6}
      >
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th
                key={i}
                style={{borderBottom: "2px solid currentColor", textAlign: "left"}}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j} style={{borderBottom: "1px solid currentColor"}}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FormulaBlock({b, order, frame, fps}) {
  const lines = (b.data && b.data.lines) || [];
  const font = b.font_size || 30;
  return (
    <div
      style={{
        ...boxStyle(b, order),
        fontSize: font,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 8,
      }}
    >
      {lines.map((tex, i) =>
        frame >= (b.appear_s + i * REVEAL_STEP_S.formula) * fps ? (
          <div
            key={i}
            dangerouslySetInnerHTML={{
              __html: katex.renderToString(tex, {
                throwOnError: false,
                displayMode: true,
              }),
            }}
          />
        ) : null,
      )}
    </div>
  );
}

function ChartBlock({b, order}) {
  const data = b.data || {};
  const labels = data.labels || [];
  const values = data.values || [];
  const max = Math.max(1, ...values.map(Number));
  const W = b.box.w;
  const H = b.box.h - 28;
  const n = Math.max(1, values.length);
  const slot = W / n;
  const accent = (b.accent || "#e0a458");
  const text = (b.text || "#f5f2ea");
  return (
    <div style={boxStyle(b, order)}>
      <svg width={W} height={b.box.h}>
        {data.subtype === "line" ? (
          <g>
            <polyline
              fill="none"
              stroke={accent}
              strokeWidth={4}
              points={values
                .map((v, i) => {
                  const x = slot * i + slot / 2;
                  const y = H - (Number(v) / max) * (H - 10);
                  return `${x},${y}`;
                })
                .join(" ")}
            />
            {values.map((v, i) => {
              const x = slot * i + slot / 2;
              const y = H - (Number(v) / max) * (H - 10);
              return <circle key={i} cx={x} cy={y} r={6} fill={accent} />;
            })}
          </g>
        ) : (
          <g>
            {values.map((v, i) => {
              const bw = Math.min(80, slot * 0.6);
              const x = slot * i + (slot - bw) / 2;
              const bh = (Number(v) / max) * (H - 10);
              return (
                <rect
                  key={i}
                  x={x}
                  y={H - bh}
                  width={bw}
                  height={bh}
                  fill={accent}
                />
              );
            })}
          </g>
        )}
        {labels.map((lb, i) => (
          <text
            key={i}
            x={slot * i + slot / 2}
            y={b.box.h - 6}
            textAnchor="middle"
            fontSize={18}
            fill={text}
          >
            {String(lb).slice(0, 12)}
          </text>
        ))}
      </svg>
    </div>
  );
}

function StepsBlock({b, order, frame, fps}) {
  const items = (b.data && b.data.items) || [];
  const font = b.font_size || 26;
  const shown = items.filter(
    (_, i) => frame >= (b.appear_s + i * REVEAL_STEP_S.steps) * fps,
  );
  return (
    <div
      style={{
        ...boxStyle(b, order),
        fontSize: font,
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 10,
      }}
    >
      {shown.map((s, i) => (
        <span key={i} style={{display: "flex", alignItems: "center", gap: 10}}>
          {i > 0 ? <span>{"\u2192"}</span> : null}
          <span
            style={{
              border: "2px solid currentColor",
              borderRadius: 10,
              padding: "6px 12px",
            }}
          >
            {s}
          </span>
        </span>
      ))}
    </div>
  );
}

function TextBlock({b, order}) {
  const lines = (b.data && b.data.lines) || [];
  const font = b.font_size || 44;
  return (
    <div
      style={{
        ...boxStyle(b, order),
        fontSize: font,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 6,
      }}
    >
      {lines.map((t, i) => (
        <div key={i}>{t}</div>
      ))}
    </div>
  );
}

function Block({b, frame, fps, guide}) {
  const order = b.order || 0;
  if (frame < b.appear_s * fps) return null;
  const tinted = {
    ...b,
    accent: guide.palette.accent,
    text: guide.palette.text,
  };
  if (b.kind === "photo" || b.kind === "generated" || b.kind === "source_figure")
    return <ImageBlock b={tinted} order={order} />;
  if (b.kind === "table") return <TableBlock b={tinted} order={order} frame={frame} fps={fps} />;
  if (b.kind === "formula") return <FormulaBlock b={tinted} order={order} frame={frame} fps={fps} />;
  if (b.kind === "chart") return <ChartBlock b={tinted} order={order} />;
  if (b.kind === "steps") return <StepsBlock b={tinted} order={order} frame={frame} fps={fps} />;
  if (b.kind === "text") return <TextBlock b={tinted} order={order} />;
  return null;
}

// One cut slide: data-only props (layout preset, blocks with boxes,
// on-screen text, style guide colors and fonts). No free code.
export const CutSlide = ({cutId, seconds, preset, blocks, onScreenText, guide}) => {
  const frame = useCurrentFrame();
  const g = guide || {};
  const pal = g.palette || {};
  const fonts = g.fonts || {};
  const bg = pal.background || "#101418";
  const fg = pal.text || "#f5f2ea";
  const accent = pal.accent || "#e0a458";
  const body = fonts.body || "sans-serif";
  const shown = (blocks || []).filter((b) => frame >= b.appear_s * CUT_FPS);
  return (
    <div
      style={{
        width: CUT_W,
        height: CUT_H,
        background: bg,
        color: fg,
        fontFamily: body,
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div style={{position: "absolute", left: 0, top: 0, width: CUT_W, height: 14, background: accent}} />
      {shown
        .slice()
        .sort((a, b) => (a.order || 0) - (b.order || 0))
        .map((b, i) => (
          <Block key={i} b={b} frame={frame} fps={CUT_FPS} guide={{palette: pal}} />
        ))}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 24,
          textAlign: "center",
          fontSize: 30,
          padding: "0 80px",
        }}
      >
        {(onScreenText || []).map((t, i) => (
          <div key={i}>{t}</div>
        ))}
      </div>
      <div
        style={{
          position: "absolute",
          left: 48,
          top: 40,
          fontSize: 24,
          color: accent,
          fontFamily: fonts.heading || body,
        }}
      >
        {cutId} {preset ? `· ${preset}` : ""}
      </div>
    </div>
  );
};
