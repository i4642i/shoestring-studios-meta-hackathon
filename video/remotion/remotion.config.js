// Remotion config: stills render as PNG, overwrite without asking.
const {Config} = require("@remotion/cli/config");

Config.setVideoImageFormat("png");
Config.setOverwriteOutput(true);
