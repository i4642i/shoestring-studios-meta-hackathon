import {Composition, registerRoot} from "remotion";
import {CutSlide, CUT_FPS, CUT_W, CUT_H, CUT_MAX_S} from "./CutSlide";
import "katex/dist/katex.min.css";

const EMPTY_GUIDE = {
  palette: {background: "#101418", text: "#f5f2ea", accent: "#e0a458"},
  fonts: {heading: "Inter SemiBold", body: "Inter Regular"},
};

export const RemotionRoot = () => {
  return (
    <>
      <Composition
        id="CutSlide"
        component={CutSlide}
        durationInFrames={CUT_MAX_S * CUT_FPS}
        fps={CUT_FPS}
        width={CUT_W}
        height={CUT_H}
        defaultProps={{
          cutId: "preview",
          seconds: 20,
          preset: "full",
          blocks: [],
          onScreenText: ["Preview"],
          guide: EMPTY_GUIDE,
        }}
      />
    </>
  );
};

registerRoot(RemotionRoot);
