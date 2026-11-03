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

const CARD_BOX = {x: 64, y: 64, w: 1152, h: 592};

function TextBlock({b, order, card}) {
  const lines = (b.data && b.data.lines) || [];
  const box = card ? {...b, box: CARD_BOX} : b;
  const font = fitTextFont(box);
  return (
    <div
      style={{
        ...boxStyle(card ? {...b, box: CARD_BOX} : b, order),
        fontSize: font,
        textAlign: card ? "center" : b.align || "left",
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

// Text-only cuts: the boxes the planner wrote are ignored and every
// text block is stacked in one centered column that fills the safe
// area (the "card" layout), largest readable font for the whole
// stack. Blocks keep their order and appear_s fades. This replaces
// the corner-scattered small boxes of a plan that had no image.
const CARD_GAP = 28;
const cardFont = (textBlocks) => {
  const allLines = textBlocks.flatMap((b) => (b.data && b.data.lines) || []);
  const longest = Math.max(1, ...allLines.map((t) => String(t).length));
  const n = Math.max(1, allLines.length);
  const byW = CARD_BOX.w / (longest * 0.55);
  const byH =
    (CARD_BOX.h - CARD_GAP * Math.max(0, textBlocks.length - 1)) /
    (n * 1.3);
  return Math.max(
    TEXT_MIN_FONT,
    Math.min(TEXT_MAX_FONT, Math.floor(Math.min(byW, byH))),
  );
};

function CardStack({blocks, frame, fps, heading}) {
  const ordered = blocks.slice().sort((a, b) => (a.order || 0) - (b.order || 0));
  const font = cardFont(ordered);
  return (
    <div
      style={{
        position: "absolute",
        left: CARD_BOX.x,
        top: CARD_BOX.y,
        width: CARD_BOX.w,
        height: CARD_BOX.h,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        gap: CARD_GAP,
        textAlign: "center",
        fontSize: font,
        lineHeight: 1.25,
      }}
    >
      {ordered.map((b, i) =>
        frame >= (b.appear_s || 0) * fps ? (
          <div
            key={i}
            style={{
              ...enterStyle(frame, fps, b.appear_s || 0),
              fontWeight: i === 0 ? heading.fontWeight : undefined,
            }}
          >
            {((b.data && b.data.lines) || []).map((t, j) => (
              <div key={j}>{t}</div>
            ))}
          </div>
        ) : null,
      )}
    </div>
  );
}

// One image plus text only: the planner's boxes are ignored and the
// cut is laid out as a big image on the left (full safe height) with
// the text blocks stacked and centered on the right. Fills the screen
// instead of leaving the lower half empty.
const SIDE_IMAGE_BOX = {x: 64, y: 64, w: 576, h: 592};
const SIDE_TEXT_BOX = {x: 688, y: 64, w: 528, h: 592};
// Largest font whose wrapped rows fit the column: each line wraps into
// ceil(chars * 0.55 * font / width) rows of 1.25 em.
const sideFont = (textBlocks) => {
  const allLines = textBlocks.flatMap((b) => (b.data && b.data.lines) || []);
  const gaps = CARD_GAP * Math.max(0, textBlocks.length - 1);
  for (let font = TEXT_MAX_FONT; font > TEXT_MIN_FONT; font -= 2) {
    const rows = allLines.reduce(
      (n, t) =>
        n + Math.max(1, Math.ceil((String(t).length * 0.55 * font) / SIDE_TEXT_BOX.w)),
      0,
    );
    if (rows * font * 1.25 + gaps <= SIDE_TEXT_BOX.h) return font;
  }
  return TEXT_MIN_FONT;
};

function SideLayout({image, textBlocks, frame, fps, seconds, heading}) {
  const ordered = textBlocks.slice().sort((a, b) => (a.order || 0) - (b.order || 0));
  const font = sideFont(ordered);
  const img = {...image, box: SIDE_IMAGE_BOX};
  return (
    <>
      {frame >= (image.appear_s || 0) * fps ? (
        <div style={enterStyle(frame, fps, image.appear_s || 0)}>
          <ImageBlock b={img} order={0} frame={frame} fps={fps} seconds={seconds} />
        </div>
      ) : null}
      <div
        style={{
          position: "absolute",
          left: SIDE_TEXT_BOX.x,
          top: SIDE_TEXT_BOX.y,
          width: SIDE_TEXT_BOX.w,
          height: SIDE_TEXT_BOX.h,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: CARD_GAP,
          fontSize: font,
          lineHeight: 1.25,
        }}
      >
        {ordered.map((b, i) =>
          frame >= (b.appear_s || 0) * fps ? (
            <div
              key={i}
              style={{
                ...enterStyle(frame, fps, b.appear_s || 0),
                fontWeight: i === 0 ? heading.fontWeight : undefined,
              }}
            >
              {((b.data && b.data.lines) || []).map((t, j) => (
                <div key={j}>{t}</div>
              ))}
            </div>
          ) : null,
        )}
      </div>
    </>
  );
}

function Block({b, frame, fps, guide, seconds, preset}) {
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
  if (b.kind === "text")
    inner = (
      <TextBlock
        b={tinted}
        order={order}
        card={preset === "card" && b.kind === "text"}
      />
    );
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
  // A guide value may carry prose ("#FDF8EE warm paper for trust"):
  // keep only the color token, or the whole slide turns black.
  const cssColor = (v, fallback) => {
    const s = String(v || "");
    const m =
      s.match(/#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b/) ||
      s.match(/rgba?\([^)]*\)/);
    return m ? m[0] : fallback;
  };
  const bg = cssColor(pal.background, "#101418");
  const fg = cssColor(pal.text, "#f5f2ea");
  const accent = cssColor(pal.accent, "#e0a458");
  const body = mapGuideFont(fonts.body, 400);
  const heading = mapGuideFont(fonts.heading, 600);
  const shown = (blocks || []).filter((b) => frame >= b.appear_s * CUT_FPS);
  // A text block owns the words: the bottom line stays silent then.
  const hasTextBlock = (blocks || []).some((b) => b && b.kind === "text");
  const bottomLines = hasTextBlock ? [] : onScreenText || [];
  // No image, table, chart, formula or steps: one centered card.
  const textOnly =
    (blocks || []).length > 0 &&
    (blocks || []).every((b) => b && b.kind === "text");
  const useCard = textOnly || preset === "card";
  // Exactly one image and otherwise only text: side layout.
  const imageBlocks = (blocks || []).filter(
    (b) => b && ["photo", "generated", "source_figure"].includes(b.kind),
  );
  const useSide =
    !useCard &&
    imageBlocks.length === 1 &&
    (blocks || []).every(
      (b) => b && (b.kind === "text" || imageBlocks.includes(b)),
    ) &&
    (blocks || []).some((b) => b && b.kind === "text");
  // One image and nothing else: the image fills the safe area (the
  // bottom line, if any, sits on its band below). A photo in a
  // 340 px planner box on an otherwise empty screen is wasted.
  const useHero =
    !useCard && !useSide && imageBlocks.length === 1 &&
    (blocks || []).length === 1;
  const heroBlocks = useHero ? [{...imageBlocks[0], box: CARD_BOX}] : null;
  // When the bottom line is drawn, the whole block layer shrinks to
  // sit above its band so nothing is covered (general rule, item 12).
  const bandH = bottomLines.length
    ? 24 + bottomLines.length * (onScreenTextFont || 36) * 1.3
    : 0;
  const layerScale = bandH ? (CUT_H - bandH) / CUT_H : 1;
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
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: CUT_W,
          height: CUT_H,
          transformOrigin: "top center",
          transform: layerScale < 1 ? `scale(${layerScale})` : undefined,
        }}
      >
        {useCard ? (
          <CardStack
            blocks={(blocks || []).filter((b) => b && b.kind === "text")}
            frame={frame}
            fps={CUT_FPS}
            heading={heading}
          />
        ) : null}
        {useSide ? (
          <SideLayout
            image={imageBlocks[0]}
            textBlocks={(blocks || []).filter((b) => b && b.kind === "text")}
            frame={frame}
            fps={CUT_FPS}
            seconds={seconds}
            heading={heading}
          />
        ) : null}
        {(useHero ? heroBlocks : shown)
          .slice()
          .filter((b) => !useCard && !useSide)
          .filter((b) => frame >= (b.appear_s || 0) * CUT_FPS)
          .sort((a, b) => (a.order || 0) - (b.order || 0))
          .map((b, i) => (
            <Block
              key={i}
              b={b}
              frame={frame}
              fps={CUT_FPS}
              guide={{palette: {...pal, background: bg, text: fg, accent}}}
              seconds={seconds}
              preset={preset}
            />
          ))}
      </div>
      {bottomLines.length ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: onScreenTextPosition === "top" ? undefined : 0,
            top: onScreenTextPosition === "top" ? 0 : undefined,
            textAlign: "center",
            fontSize: onScreenTextFont || 36,
            fontWeight: heading.fontWeight,
            padding: "12px 80px",
            background: "rgba(0, 0, 0, 0.55)",
            color: "#F7F5F0", // always light on the dark band
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
