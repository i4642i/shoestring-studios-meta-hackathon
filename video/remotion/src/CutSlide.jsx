import React from "react";
import {
  Img,
  continueRender,
  delayRender,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import {loadFont} from "@remotion/google-fonts/Inter";
import katex from "katex";

// House font (style guide: Inter Regular / Inter SemiBold).
// waitUntilDone resolves when the faces are ready; the render
// waits for it (max 10 s) so slides never fall back to serif.
const {fontFamily: INTER, waitUntilDone: waitForInter} = loadFont(
  "normal",
  {weights: ["400", "500", "600", "700"], subsets: ["latin"]},
);

const FONT_TIMEOUT_MS = 10000;

// "Inter SemiBold" -> {Inter, 600}; anything else -> {Inter, weight}.
export const mapGuideFont = (name, fallbackWeight) => {
  const n = String(name || "");
  const weight = /semibold|600/i.test(n)
    ? 600
    : /\bbold\b|700/i.test(n)
      ? 700
      : /medium|500/i.test(n)
        ? 500
        : 400;
  return {
    fontFamily: INTER,
    fontWeight: /inter/i.test(n) ? weight : fallbackWeight,
  };
};

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

const FADE_S = 0.5; // every block fades + slides in over 0.5 s
const ZOOM_END = 1.06; // image blocks breathe over the cut

const clamp01 = (t) => Math.max(0, Math.min(1, t));

// Opacity + rise for a block that appeared at appear_s.
const enterStyle = (frame, fps, appear_s) => {
  const t = clamp01((frame / fps - appear_s) / FADE_S);
  return {opacity: t, transform: `translateY(${(1 - t) * 24}px)`};
};

// Per-item fade for stepwise reveals (table rows, steps, formulas).
const itemOpacity = (frame, fps, at_s) =>
  clamp01((frame / fps - at_s) / FADE_S);

function ImageBlock({b, order, frame, fps, seconds}) {
  if (!b.file) return null;
  const total = Math.max(1, seconds * fps - 1);
  const zoom = interpolate(frame, [0, total], [1, ZOOM_END], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={boxStyle(b, order)}>
      <Img
        src={staticFile(b.file)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
          transform: `scale(${zoom})`,
        }}
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
            <tr
              key={i}
              style={{
                opacity: itemOpacity(
                  frame,
                  fps,
                  b.appear_s + i * REVEAL_STEP_S.table,
                ),
              }}
            >
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
            style={{
              opacity: itemOpacity(
                frame,
                fps,
                b.appear_s + i * REVEAL_STEP_S.formula,
              ),
            }}
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
        <span
          key={i}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            opacity: itemOpacity(
              frame,
              fps,
              b.appear_s + i * REVEAL_STEP_S.steps,
            ),
          }}
        >
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

const TEXT_MIN_FONT = 32;
const TEXT_MAX_FONT = 72;

// The box decides the size, not the LLM: biggest font that fills
// the box, clamped to readable bounds.
export const fitTextFont = (b) => {
  const lines = (b.data && b.data.lines) || [];
  const box = b.box || {w: 200, h: 40};
  const longest = Math.max(1, ...lines.map((t) => String(t).length));
  const n = Math.max(1, lines.length);
  const byW = box.w / (longest * 0.55);
  const byH = box.h / (n * 1.25);
  return Math.max(
    TEXT_MIN_FONT,
    Math.min(TEXT_MAX_FONT, Math.floor(Math.min(byW, byH))),
  );
};

function TextBlock({b, order}) {
  const lines = (b.data && b.data.lines) || [];
  const font = fitTextFont(b);
  return (
    <div
      style={{
        ...boxStyle(b, order),
        fontSize: font,
        textAlign: b.align || "left",
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

function Block({b, frame, fps, guide, seconds}) {
  const order = b.order || 0;
  if (frame < b.appear_s * fps) return null;
  const tinted = {
    ...b,
    accent: guide.palette.accent,
    text: guide.palette.text,
  };
  let inner = null;
  if (b.kind === "photo" || b.kind === "generated" || b.kind === "source_figure")
    inner = (
      <ImageBlock
        b={tinted}
        order={order}
        frame={frame}
        fps={fps}
        seconds={seconds}
      />
    );
  if (b.kind === "table")
    inner = (
      <TableBlock b={tinted} order={order} frame={frame} fps={fps} />
    );
  if (b.kind === "formula")
    inner = (
      <FormulaBlock b={tinted} order={order} frame={frame} fps={fps} />
    );
  if (b.kind === "chart")
    inner = <ChartBlock b={tinted} order={order} />;
  if (b.kind === "steps")
    inner = (
      <StepsBlock b={tinted} order={order} frame={frame} fps={fps} />
    );
  if (b.kind === "text") inner = <TextBlock b={tinted} order={order} />;
  if (!inner) return null;
  return <div style={enterStyle(frame, fps, b.appear_s)}>{inner}</div>;
}

// One cut slide: data-only props (layout preset, blocks with boxes,
// on-screen text, style guide colors and fonts). No free code.
export const CutSlide = ({cutId, seconds, preset, blocks, onScreenText, guide, onScreenTextFont, onScreenTextPosition}) => {
  const frame = useCurrentFrame();
  const [fontHandle] = React.useState(() => delayRender("inter font"));
  React.useEffect(() => {
    let alive = true;
    const done = () => {
      if (alive) continueRender(fontHandle);
    };
    const timer = setTimeout(done, FONT_TIMEOUT_MS);
    Promise.resolve()
      .then(() => waitForInter())
      .then(done, done);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [fontHandle]);
  const g = guide || {};
  const pal = g.palette || {};
  const fonts = g.fonts || {};
  const bg = pal.background || "#101418";
  const fg = pal.text || "#f5f2ea";
  const accent = pal.accent || "#e0a458";
  const body = mapGuideFont(fonts.body, 400);
  const heading = mapGuideFont(fonts.heading, 600);
  const shown = (blocks || []).filter((b) => frame >= b.appear_s * CUT_FPS);
  // A text block owns the words: the bottom line stays silent then.
  const hasTextBlock = (blocks || []).some((b) => b && b.kind === "text");
  const bottomLines = hasTextBlock ? [] : onScreenText || [];
  return (
    <div
      style={{
        width: CUT_W,
        height: CUT_H,
        background: bg,
        color: fg,
        fontFamily: `${body.fontFamily}, sans-serif`,
        fontWeight: body.fontWeight,
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div style={{position: "absolute", left: 0, top: 0, width: CUT_W, height: 14, background: accent}} />
      {shown
        .slice()
        .sort((a, b) => (a.order || 0) - (b.order || 0))
        .map((b, i) => (
          <Block
            key={i}
            b={b}
            frame={frame}
            fps={CUT_FPS}
            guide={{palette: pal}}
            seconds={seconds}
          />
        ))}
      {bottomLines.length ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: onScreenTextPosition === "top" ? undefined : 24,
            top: onScreenTextPosition === "top" ? 24 : undefined,
            textAlign: "center",
            fontSize: onScreenTextFont || 36,
            fontWeight: heading.fontWeight,
            padding: "0 80px",
          }}
        >
          {bottomLines.map((t, i) => (
            <div key={i}>{t}</div>
          ))}
        </div>
      ) : null}
    </div>
  );
};
