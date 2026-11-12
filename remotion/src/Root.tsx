import React from "react";
import { Composition } from "remotion";
import { Page, PageProps } from "./Page";

// 페이지 하나 = 컴포지션 하나. 길이·크기는 타임라인(props)에서 정한다.
const sample: PageProps = { page: "sample", duration: 3, width: 1280, height: 720, background: [], layers: [], audio: [] };

export const Root: React.FC = () => (
  <Composition
    id="Page"
    component={Page}
    fps={30}
    width={1280}
    height={720}
    durationInFrames={90}
    defaultProps={sample}
    calculateMetadata={({ props }) => ({
      durationInFrames: Math.max(1, Math.round((props.duration || 3) * 30)),
      width: props.width || 1280,
      height: props.height || 720,
    })}
  />
);
